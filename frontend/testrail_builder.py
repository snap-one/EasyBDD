"""Easy BDD TestRail Test Builder — backend.

A focused web app for authoring TestRail test cases visually:

  * Create Var:, Shared:, Setup:, Teardown: and Feature: cases from guided
    forms — no YAML syntax or action-name spelling to get wrong.
  * The step palette is generated from frontend/action_definitions.py merged
    with easybdd.core.validator.ACTION_SCHEMA, so every action the runner
    supports is available.
  * The Preconditions body is generated server-side in the flush-left
    dot-notation format the runner expects, then round-trip validated with
    the exact same parser the runner uses (fix_step_list_indent +
    parse_yaml_lenient).
  * Cases publish straight into a TestRail suite/section, and runs can be
    assembled from published cases (EASY_BDD: prefix) ready for
    `python -m easybdd testrail-run`.

Start with:  python frontend/start_testrail_builder.py   (default port 8091)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import httpx
import requests
import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from easybdd.core.parser import fix_step_list_indent, parse_yaml_lenient, strip_html_to_text  # noqa: E402
from easybdd.services.jenkins_service import JenkinsError, JenkinsService  # noqa: E402
from easybdd.services.testrail_service import (  # noqa: E402
    TestRailError,
    TestRailService,
)

from builder_core import (  # noqa: E402
    CASE_PREFIXES,
    CATALOG,
    ImportRecordingRequest,
    RECORDING_FORMATS,
    StepNode,
    VarRow,
    CaseModel,
    _ROLE_BY_PREFIX,
    _classify_role,
    _dict_to_node,
    _sanitize_node,
    _schema_for,
    case_title,
    convert_recording_text,
    parse_case_to_model,
    serialize_case_body,
    validate_case,
)

app = FastAPI(
    title="Easy BDD TestRail Test Builder",
    description="Author Var/Shared/Setup/Teardown/Feature cases visually and publish to TestRail",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class PublishRequest(BaseModel):
    model: CaseModel
    project_id: int
    suite_id: Optional[int] = None
    section_id: Optional[int] = None
    case_id: Optional[int] = None  # update existing case when set


class SectionRequest(BaseModel):
    project_id: int
    suite_id: Optional[int] = None
    name: str
    parent_id: Optional[int] = None


class RunRequest(BaseModel):
    project_id: int
    suite_id: Optional[int] = None
    name: str
    case_ids: List[int]
    description: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCaseContext(BaseModel):
    """The case currently open in the builder editor, sent with every chat
    turn so the assistant doesn't need the user to paste a case ID it can
    already see on screen."""
    case_id: Optional[int] = None
    title: Optional[str] = None
    body: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    case_context: Optional[ChatCaseContext] = None


# --------------------------------------------------------------------------- #
# TestRail client                                                               #
# --------------------------------------------------------------------------- #

_tr_service: Optional[TestRailService] = None


def _tr() -> TestRailService:
    global _tr_service
    if _tr_service is None:
        try:
            _tr_service = TestRailService()
        except TestRailError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return _tr_service


def _tr_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except TestRailError as exc:
        raise HTTPException(status_code=502, detail=f"TestRail error: {exc}")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"TestRail request failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected TestRail client error: {exc}")


_jenkins_service: Optional[JenkinsService] = None

# TestRail project id -> the exact PROJECT_ID choice string declared in
# Jenkinsfile.manual's `choice(name: 'PROJECT_ID', choices: [...])` block.
# Jenkins rejects any value that isn't a verbatim match for one of those
# choices, so these two lists must be kept in sync.
_JENKINS_PROJECT_CHOICES: Dict[int, str] = {
    59: "59 - JDM Automation",
    74: "74 - Audio",
    76: "76 - Routers",
    77: "77 - Power",
    78: "78 - Surveillance",
    79: "79 - Switches",
    80: "80 - Access Points",
    81: "81 - Media Distribution",
}


def _jenkins() -> JenkinsService:
    global _jenkins_service
    if _jenkins_service is None:
        try:
            _jenkins_service = JenkinsService()
        except JenkinsError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return _jenkins_service


def _jenkins_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except JenkinsError as exc:
        raise HTTPException(status_code=502, detail=f"Jenkins error: {exc}")
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Jenkins request failed: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected Jenkins client error: {exc}")


def _allowed_project_ids() -> Optional[set]:
    raw = os.getenv("TESTRAIL_ALLOWED_PROJECT_IDS", "").strip()
    if not raw:
        return None
    return {int(part) for part in raw.split(",") if part.strip()}


def _case_link(case_id: int) -> str:
    base = os.getenv("TESTRAIL_URL", "").rstrip("/")
    return f"{base}/index.php?/cases/view/{case_id}" if base else ""


def _run_link(run_id: int) -> str:
    base = os.getenv("TESTRAIL_URL", "").rstrip("/")
    return f"{base}/index.php?/runs/view/{run_id}" if base else ""


# --------------------------------------------------------------------------- #
# Routes                                                                        #
# --------------------------------------------------------------------------- #

@app.get("/")
async def index():
    page = STATIC_DIR / "testrail_builder.html"
    if not page.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Builder UI file is missing: {page}. "
                "Ensure frontend/static/testrail_builder.html is deployed on the host."
            ),
        )
    return FileResponse(page)


@app.get("/api/catalog")
async def get_catalog():
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for action_id, definition in sorted(CATALOG.items()):
        categories.setdefault(definition["category"], []).append(
            {"id": action_id, **definition}
        )
    return {"categories": categories, "case_types": CASE_PREFIXES}


# Section headers (verbatim, minus the "## " markdown prefix) to keep from
# docs/writing-test-cases.md. The full doc runs ~2500 words; on the CPU-only
# Ollama host this app talks to (~20 tok/s prompt processing, ~5.5 tok/s
# generation — measured, no GPU), that alone would cost 2+ minutes of prompt
# processing before the model can even start replying. These sections cover
# the naming/format/assertion rules that are wrong most often; the full
# per-action browser table is skipped in favor of the compact CATALOG-derived
# list below, which already gives per-action required params.
_FRAMEWORK_DOC_SECTIONS = (
    "1. Case Naming",
    "2. Var: Cases",
    "3. Preconditions Field Format",
    "6. Assertions",
    "10. Selector Strategies",
)


def _load_framework_doc() -> str:
    try:
        text = (ROOT / "docs" / "writing-test-cases.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    kept = [
        "## " + section
        for section in text.split("\n## ")[1:]
        if section.startswith(_FRAMEWORK_DOC_SECTIONS)
    ]
    return "\n\n".join(kept).strip()


def _action_reference_markdown() -> str:
    """Compact action list (id + required params only, no descriptions) grouped
    by category, generated from the same CATALOG the builder's step palette
    uses — keeps the assistant's knowledge of available actions in sync with
    what the UI actually offers, without spending tokens on prose."""
    by_category: Dict[str, List[str]] = {}
    for action_id, definition in sorted(CATALOG.items()):
        params = definition.get("parameters") or {}
        required = [name for name, cfg in params.items() if cfg.get("required")]
        entry = f"- `{action_id}`"
        if required:
            entry += f" (required: {', '.join(required)})"
        by_category.setdefault(definition.get("category", "Other"), []).append(entry)

    lines: List[str] = []
    for category in sorted(by_category):
        lines.append(f"### {category}")
        lines.extend(by_category[category])
    return "\n".join(lines)


CHAT_SYSTEM_PROMPT = (
    "You are the AI assistant embedded in the Easy BDD TestRail Test Builder. "
    "You help the user author BDD-style TestRail test cases (Var:, Shared:, Setup:, "
    "Teardown:, Feature:), pick the right builder actions, and troubleshoot the "
    "Preconditions YAML the app generates. Use the framework reference and action "
    "list below as ground truth — don't invent actions or syntax that aren't in them. "
    "This model runs on CPU with no GPU, so keep answers short (a few sentences or "
    "a short snippet) — long answers take a long time to generate.\n\n"
    "If the user has a case open in the builder, its title, Preconditions YAML, and "
    "current validation errors/warnings are provided in a separate 'Currently open "
    "test case' message on every turn — treat that as ground truth about what they're "
    "looking at, and don't ask them to paste a case ID that's already given there. "
    "When TestRail access is configured you also have tools: `get_testrail_case` to "
    "read any other case by ID, and `update_testrail_case` to write a title/Preconditions "
    "change directly to TestRail. Only call `update_testrail_case` when the user has "
    "explicitly asked you to save, apply, or publish a change — never write proactively.\n\n"
    "# Framework syntax reference\n\n" + _load_framework_doc() + "\n\n"
    "# Available builder actions (id and required params)\n\n" + _action_reference_markdown()
)

# Tool schema handed to Ollama for models with function-calling support (qwen2.5-coder
# does). Kept to exactly the two operations the builder UI itself performs on a case
# (read one, write title/Preconditions) — same TestRailService + .env credentials the
# rest of this app and frontend/mcp_server.py's TestRail tools use, so the assistant's
# read/write reach matches what the human already has through this app.
TESTRAIL_CHAT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_testrail_case",
            "description": (
                "Look up any TestRail case by numeric ID and return its title and "
                "Preconditions body. Use this for cases other than the one currently "
                "open in the builder (that one is already given as context)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {
                        "type": "integer",
                        "description": "Numeric TestRail case ID, e.g. 18761858 for C18761858",
                    }
                },
                "required": ["case_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_testrail_case",
            "description": (
                "Write a title and/or Preconditions change directly to a TestRail case. "
                "This is a real write to the shared TestRail instance — only call it when "
                "the user has explicitly asked you to save, apply, or publish a change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "integer", "description": "Numeric TestRail case ID to update"},
                    "title": {"type": "string", "description": "New case title (omit to leave unchanged)"},
                    "preconditions": {
                        "type": "string",
                        "description": "New full Preconditions field YAML body (omit to leave unchanged)",
                    },
                },
                "required": ["case_id"],
            },
        },
    },
]

MAX_CHAT_TOOL_ROUNDS = 4


def _testrail_configured() -> bool:
    return bool(
        os.getenv("TESTRAIL_URL") and os.getenv("TESTRAIL_USERNAME") and os.getenv("TESTRAIL_API_KEY")
    )


def _run_chat_tool(name: str, args: Dict[str, Any]) -> str:
    """Execute a tool call the chat model requested, returning a JSON string
    (never raises — errors are reported back to the model as tool output)."""
    try:
        if name == "get_testrail_case":
            case_id = int(args["case_id"])
            case = _tr().get_case(case_id)
            body = strip_html_to_text(str(case.get("custom_preconds") or ""))
            return json.dumps({"case_id": case_id, "title": case.get("title", ""), "preconditions": body})
        if name == "update_testrail_case":
            case_id = int(args["case_id"])
            payload: Dict[str, Any] = {}
            if args.get("title") is not None:
                payload["title"] = args["title"]
            if args.get("preconditions") is not None:
                payload["custom_preconds"] = args["preconditions"]
            if not payload:
                return json.dumps({"error": "Nothing to update — provide title and/or preconditions."})
            case = _tr().update_case(case_id, **payload)
            return json.dumps({"ok": True, "case_id": case_id, "title": case.get("title", "")})
        return json.dumps({"error": f"Unknown tool '{name}'"})
    except TestRailError as exc:
        return json.dumps({"error": f"TestRail error: {exc}"})
    except Exception as exc:  # noqa: BLE001 - reported to the model, not raised
        return json.dumps({"error": str(exc)})


_TESTRAIL_TOOL_NAMES = {t["function"]["name"] for t in TESTRAIL_CHAT_TOOLS}


def _parse_pseudo_tool_call(content: str) -> Optional[tuple]:
    """qwen2.5-coder:7b (unlike larger tool-tuned models) doesn't reliably
    populate Ollama's structured `message.tool_calls` — it often writes the
    call as plain JSON text instead, e.g. {"name": "get_testrail_case",
    "arguments": {"case_id": 123}}. Detect that shape as a fallback so tool
    calling still works with this model."""
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get("name")
    if name not in _TESTRAIL_TOOL_NAMES:
        return None
    args = obj.get("arguments", {})
    if not isinstance(args, dict):
        return None
    return name, args


# The base system prompt (framework doc + action list) already runs ~3.5k
# tokens on its own — see the num_ctx comment below. A case with a large
# Preconditions body or dozens of validation issues (e.g. many duplicate-key
# warnings) can otherwise inflate the per-turn prompt past what this CPU-only
# host can process inside one request's timeout, so everything past this
# cap is dropped rather than sent to the model.
MAX_CASE_CONTEXT_ISSUES = 8
MAX_CASE_CONTEXT_BODY_CHARS = 3000


def _case_context_message(ctx: Optional[ChatCaseContext]) -> Optional[Dict[str, str]]:
    if not ctx or not (ctx.case_id or ctx.title or ctx.body):
        return None
    lines = ["# Currently open test case in the builder",
             "(unpublished edits — may not match TestRail yet)"]
    if ctx.case_id:
        lines.append(f"TestRail case ID: C{ctx.case_id}")
    if ctx.title:
        lines.append(f"Title: {ctx.title}")
    if ctx.errors:
        shown = ctx.errors[:MAX_CASE_CONTEXT_ISSUES]
        suffix = f"\n- ...and {len(ctx.errors) - len(shown)} more" if len(ctx.errors) > len(shown) else ""
        lines.append("Validation errors:\n" + "\n".join(f"- {e}" for e in shown) + suffix)
    if ctx.warnings:
        shown = ctx.warnings[:MAX_CASE_CONTEXT_ISSUES]
        suffix = f"\n- ...and {len(ctx.warnings) - len(shown)} more" if len(ctx.warnings) > len(shown) else ""
        lines.append("Validation warnings:\n" + "\n".join(f"- {w}" for w in shown) + suffix)
    if ctx.body:
        body = ctx.body
        if len(body) > MAX_CASE_CONTEXT_BODY_CHARS:
            body = body[:MAX_CASE_CONTEXT_BODY_CHARS] + f"\n... (truncated, {len(ctx.body)} chars total)"
        lines.append("Current Preconditions YAML:\n```yaml\n" + body + "\n```")
    return {"role": "system", "content": "\n\n".join(lines)}


def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def _chat_model() -> str:
    return os.getenv("BUILDER_CHAT_MODEL", "qwen2.5-coder:7b")


def _chat_num_ctx() -> int:
    # The system prompt (framework doc + action list) alone runs ~3.5k tokens,
    # and the "currently open case" context message adds more on top of that —
    # 4096 left almost no headroom and caused real prompts to overflow/stall.
    return int(os.getenv("BUILDER_CHAT_NUM_CTX", "8192"))


def _chat_max_tokens() -> int:
    # Caps worst-case generation time on the CPU-only host (~5.5 tok/s measured).
    return int(os.getenv("BUILDER_CHAT_MAX_TOKENS", "350"))


def _chat_keep_alive() -> str:
    # Keep the model resident between turns so a mid-conversation pause doesn't
    # evict it — that would force reprocessing the whole ~3k-token system
    # prompt from scratch (~2.5 min) instead of the cached-prefix fast path
    # (~10-30s, measured) that later turns in the same conversation get.
    return os.getenv("BUILDER_CHAT_KEEP_ALIVE", "30m")


@app.get("/api/chat/status")
async def chat_status():
    base = _ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
    except httpx.HTTPError:
        return {"configured": False, "model": _chat_model()}
    except Exception:
        return {"configured": False, "model": _chat_model()}
    return {"configured": True, "model": _chat_model()}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    base = _ollama_base_url()
    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    case_msg = _case_context_message(req.case_context)
    if case_msg:
        messages.append(case_msg)
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    use_tools = _testrail_configured()
    payload: Dict[str, Any] = {
        "model": _chat_model(),
        "stream": False,
        "keep_alive": _chat_keep_alive(),
        "options": {
            "num_ctx": _chat_num_ctx(),
            "num_predict": _chat_max_tokens(),
        },
    }
    if use_tools:
        payload["tools"] = TESTRAIL_CHAT_TOOLS

    try:
        # A single round with a full case-context prompt (~4.5k tokens) has been
        # measured at ~130s on this CPU-only host; 240s cut it close for the
        # heaviest real cases (many validation issues + a large body), so this
        # leaves more headroom. Each round in the tool-call loop gets its own
        # budget — a multi-round turn can legitimately take several minutes.
        async with httpx.AsyncClient(timeout=300) as client:
            for _ in range(MAX_CHAT_TOOL_ROUNDS):
                resp = await client.post(f"{base}/api/chat", json={**payload, "messages": messages})
                resp.raise_for_status()
                data = resp.json()
                message = data.get("message", {}) or {}
                tool_calls = list(message.get("tool_calls") or [])
                pseudo_call = None
                if not tool_calls and use_tools:
                    pseudo_call = _parse_pseudo_tool_call(message.get("content", ""))
                if not tool_calls and not pseudo_call:
                    return {"reply": message.get("content", "")}

                messages.append(message)
                if pseudo_call:
                    name, args = pseudo_call
                    result = _run_chat_tool(name, args)
                    messages.append({"role": "tool", "content": result})
                else:
                    for call in tool_calls:
                        fn = call.get("function", {}) or {}
                        name = fn.get("name", "")
                        args = fn.get("arguments") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except ValueError:
                                args = {}
                        result = _run_chat_tool(name, args)
                        messages.append({"role": "tool", "content": result})
            # Ran out of tool-call rounds — ask once more without tools so the
            # model has to answer in plain text instead of looping forever.
            final_payload = {k: v for k, v in payload.items() if k != "tools"}
            resp = await client.post(f"{base}/api/chat", json={**final_payload, "messages": messages})
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Ollama request timed out — the prompt may be too large for this CPU-only "
                   "host, or the model is busy. Try again, or ask a shorter question.",
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc}")
    return {"reply": data.get("message", {}).get("content", "")}


@app.get("/api/testrail/status")
async def testrail_status():
    url = os.getenv("TESTRAIL_URL", "")
    user = os.getenv("TESTRAIL_USERNAME", "")
    configured = bool(url and user and os.getenv("TESTRAIL_API_KEY"))
    return {"configured": configured, "url": url, "username": user}


@app.get("/api/testrail/projects")
async def testrail_projects():
    projects = _tr_call(_tr().get_projects)
    allowed = _allowed_project_ids()
    return [
        {"id": p["id"], "name": p["name"], "suite_mode": p.get("suite_mode")}
        for p in projects
        if not p.get("is_completed") and (allowed is None or p["id"] in allowed)
    ]


@app.get("/api/testrail/suites")
async def testrail_suites(project_id: int = Query(...)):
    suites = _tr_call(_tr().get_suites, project_id)
    return [{"id": s["id"], "name": s["name"]} for s in suites]


@app.get("/api/testrail/sections")
async def testrail_sections(project_id: int = Query(...), suite_id: Optional[int] = Query(None)):
    sections = _tr_call(_tr().get_sections, project_id, suite_id)
    return [
        {"id": s["id"], "name": s["name"], "parent_id": s.get("parent_id"), "depth": s.get("depth", 0)}
        for s in sections
    ]



def _var_keys_from_body(text: str) -> List[str]:
    """Extract variable keys from a Var: case body (YAML or line-based)."""
    if not text:
        return []
    try:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            return [str(k).lstrip("$") for k in parsed.keys()]
    except yaml.YAMLError:
        pass
    keys = []
    for line in text.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith(("#", "-")):
            k = line.partition(":")[0].strip().strip('"').lstrip("$")
            if k:
                keys.append(k)
    return keys


def _step_var_outputs(text: str) -> List[str]:
    """Variables a step-based Var: case defines (store_as / eval.set keys)."""
    out: List[str] = []
    try:
        parsed = parse_yaml_lenient(fix_step_list_indent(text))
    except Exception:
        return out
    if not isinstance(parsed, list):
        return out

    def walk(steps: List[Any]) -> None:
        for s in steps:
            if not isinstance(s, dict):
                continue
            for key, val in s.items():
                if isinstance(val, dict):
                    if isinstance(val.get("store_as"), str):
                        out.append(val["store_as"].strip())
                    if key == "eval.set" and isinstance(val.get("key"), str):
                        out.append(val["key"].strip())
            for sub in ("steps", "then", "else", "try", "except", "finally"):
                if isinstance(s.get(sub), list):
                    walk(s[sub])
            if isinstance(s.get("store_as"), str):  # action-key format
                out.append(s["store_as"].strip())

    walk(parsed)
    return out


def _suite_context(cases: List[Dict[str, Any]]) -> tuple:
    """Collect (var keys, shared names) defined across a suite's cases."""
    known_vars: List[str] = []
    known_shared: List[str] = []
    for c in cases:
        title = c.get("title", "") or ""
        role = _classify_role(title)
        if role == "var":
            body = strip_html_to_text(str(c.get("custom_preconds") or ""))
            if body.lstrip().startswith("-"):
                known_vars.extend(_step_var_outputs(body))
            else:
                known_vars.extend(_var_keys_from_body(body))
        elif role == "shared":
            known_shared.append(title[len("Shared:"):].strip())
    return sorted(set(known_vars)), sorted(set(known_shared))


@app.get("/api/testrail/cases")
async def testrail_cases(project_id: int = Query(...), suite_id: Optional[int] = Query(None)):
    cases = _tr_call(_tr().get_cases, project_id, suite_id)
    out = []
    for c in cases:
        title = c.get("title", "")
        role = _classify_role(title)
        item = {"id": c["id"], "title": title, "section_id": c.get("section_id"), "role": role}
        if role == "var":
            body = strip_html_to_text(str(c.get("custom_preconds") or ""))
            item["var_keys"] = (
                _step_var_outputs(body) if body.lstrip().startswith("-")
                else _var_keys_from_body(body)
            )
        out.append(item)
    return out


@app.get("/api/testrail/case/{case_id}")
async def testrail_case(case_id: int):
    case = _tr_call(_tr().get_case, case_id)
    result = parse_case_to_model(case)
    result["case_id"] = case_id
    result["section_id"] = case.get("section_id")
    result["link"] = _case_link(case_id)
    return result


# ---------------------------------------------------------------------------
# Import recorded steps (clipboard paste)
# ---------------------------------------------------------------------------


@app.post("/api/import/recording")
async def import_recording(req: ImportRecordingRequest):
    """Convert clipboard-pasted recorder output into builder step nodes."""
    try:
        result = convert_recording_text(req.text, req.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    raw_steps = [s for s in result.get("steps") or [] if isinstance(s, dict)]
    if not req.include_logs:
        # The recorder pipeline interleaves a test.log narration step before
        # each browser step — noise as separate rows in the builder.
        raw_steps = [s for s in raw_steps if set(s) != {"test.log"}]

    nodes = [_dict_to_node(s) for s in raw_steps]
    warnings: List[str] = []
    for i, node in enumerate(nodes, 1):
        _sanitize_node(node)
        if node.kind == "action" and not _schema_for(node.action or ""):
            warnings.append(f"Step {i}: action '{node.action}' is not in the runner's action registry.")
        elif node.kind == "raw":
            warnings.append(f"Step {i} could not be mapped to a form — kept as raw YAML.")
    if not nodes:
        raise HTTPException(
            status_code=400,
            detail=f"Recognized the recording as {result['format']}, but found no convertible steps in it.",
        )

    variables = [
        {"key": str(k), "value": v}
        for k, v in (result.get("variables") or {}).items()
    ]
    return {
        "format": result["format"],
        "name": result.get("name") or "",
        "steps": [n.model_dump() for n in nodes],
        "variables": variables,
        "warnings": warnings,
    }


@app.post("/api/preview")
async def preview(model: CaseModel):
    try:
        body = serialize_case_body(model)
    except (ValueError, yaml.YAMLError) as exc:
        return {"title": "", "body": "", "error": str(exc)}
    try:
        title = case_title(model)
    except ValueError as exc:
        return {"title": "", "body": body, "error": str(exc)}
    return {"title": title, "body": body, "error": None}


class ValidateRequest(BaseModel):
    model: CaseModel
    known_vars: Optional[List[str]] = None
    known_shared: Optional[List[str]] = None


@app.post("/api/validate")
async def validate(req: ValidateRequest):
    return validate_case(req.model, known_vars=req.known_vars, known_shared=req.known_shared)


class LintRequest(BaseModel):
    project_id: int
    suite_id: Optional[int] = None


@app.post("/api/testrail/lint")
async def lint_suite(req: LintRequest):
    """Health-check every case in a suite with the builder's validation.

    Catches damage from hand-edits in TestRail's rich-text field: broken
    YAML, misspelled actions, missing required params, unknown ${variables},
    dangling shared-step references, legacy-format bodies.
    """
    cases = _tr_call(_tr().get_cases, req.project_id, req.suite_id)
    known_vars, known_shared = _suite_context(cases)
    results = []
    counts = {"checked": 0, "clean": 0, "errors": 0, "warnings": 0}
    for c in cases:
        title = c.get("title", "") or ""
        role = _classify_role(title)
        counts["checked"] += 1
        errors: List[str] = []
        warnings: List[str] = []
        if role == "other":
            warnings.append(
                "Title has no recognized prefix (Feature:/Var:/Shared:/Setup:/Teardown:/Test:) — the runner will skip this case."
            )
        elif role == "test":
            pass  # pointer cases route to local YAML; nothing to lint here
        else:
            parsed = parse_case_to_model(c)
            for note in parsed.get("notes", []):
                # purely informational notes aren't suite-health problems
                if not note.startswith("Step-based Var:"):
                    warnings.append(note)
            try:
                model = CaseModel(**parsed["model"])
                v = validate_case(model, known_vars=known_vars, known_shared=known_shared)
                errors.extend(v["errors"])
                warnings.extend(v["warnings"])
            except Exception as exc:
                errors.append(f"Could not validate: {exc}")
        if errors or warnings:
            results.append({
                "case_id": c["id"], "title": title, "role": role,
                "section_id": c.get("section_id"),
                "errors": errors, "warnings": warnings,
                "link": _case_link(c["id"]),
            })
            counts["errors" if errors else "warnings"] += 1
        else:
            counts["clean"] += 1
    return {"counts": counts, "issues": results}


@app.get("/api/migrate/candidates")
async def migrate_candidates(project_id: int = Query(...), suite_id: Optional[int] = Query(None)):
    """Scan a suite for cases whose body looks like un-migrated legacy
    (pipe-delimited mybdd) content, for the migration UI's case picker.
    Reuses parse_case_to_model's own "legacy format?" detection — the same
    signal /api/testrail/lint already surfaces per-case — rather than a
    second, possibly-divergent heuristic."""
    cases = _tr_call(_tr().get_cases, project_id, suite_id)
    candidates = []
    for c in cases:
        title = c.get("title", "") or ""
        role = _classify_role(title)
        if role in ("other", "test"):
            continue
        parsed = parse_case_to_model(c)
        notes = parsed.get("notes", [])
        is_legacy = any(
            "legacy format" in n or "Could not parse existing body" in n
            for n in notes
        )
        if is_legacy:
            candidates.append({
                "case_id": c["id"], "title": title, "role": role,
                "section_id": c.get("section_id"),
            })
    return {"candidates": candidates}


class MigratePreviewRequest(BaseModel):
    case_id: Optional[int] = None
    # Paste mode — used when a case's live body has already been clobbered
    # by a bad migration and the original legacy source only exists outside
    # TestRail (the caller supplies it directly instead of case_id).
    content: Optional[str] = None
    name: Optional[str] = None
    case_type: Optional[str] = None


@app.post("/api/migrate/preview")
async def migrate_preview(req: MigratePreviewRequest):
    """Run the BDD migrator against either a live case's current body
    (case_id) or pasted legacy content, and return the resulting Easy BDD
    model + preview body — without publishing anything. Hand the returned
    "model" straight to /api/testrail/publish to actually apply it."""
    import bdd_migrator

    old_body = None
    if req.case_id:
        case = _tr_call(_tr().get_case, req.case_id)
        title = case.get("title", "") or ""
        role = _classify_role(title)
        if role in ("other", "test"):
            raise HTTPException(status_code=400, detail=f"Case C{req.case_id} isn't a migratable case type (role={role!r})")
        name = title
        for prefix, r in _ROLE_BY_PREFIX.items():
            if title.startswith(prefix):
                name = title[len(prefix):].strip()
                break
        old_body = strip_html_to_text(str(case.get("custom_preconds") or ""))
        # A case_id + pasted content together means: use this case's known
        # title/type, but migrate the pasted text instead of the live body —
        # for cases whose body was already overwritten by a bad migration,
        # where the original legacy source only exists outside TestRail.
        legacy_source = req.content if req.content else old_body
    else:
        if not req.content or not req.name or not req.case_type:
            raise HTTPException(
                status_code=400,
                detail="content, name, and case_type are required when case_id is not given",
            )
        legacy_source = req.content
        name = req.name
        role = req.case_type

    if not legacy_source.strip():
        raise HTTPException(status_code=400, detail="Nothing to migrate — source content is empty")

    try:
        result = bdd_migrator.migrate(legacy_source)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Migration failed: {exc}")

    migrator_warnings = list(result.get("warnings", []))
    if not result.get("tests"):
        raise HTTPException(status_code=422, detail="Migrator produced no steps — check the source content.")

    parsed_yaml = yaml.safe_load(result["tests"][0]["yaml"]) or {}
    raw_steps = parsed_yaml.get("steps") or []
    nodes = [_dict_to_node(s) for s in raw_steps if isinstance(s, dict)]
    data_rows = None
    if parsed_yaml.get("data"):
        data_rows = yaml.safe_dump(parsed_yaml["data"], default_flow_style=False, width=100000).rstrip()

    model = CaseModel(
        case_type=role,
        name=name,
        variables=[],
        data_rows=data_rows,
        steps=[n.model_dump() for n in nodes],
    )

    v = validate_case(model)
    try:
        title = case_title(model)
    except ValueError:
        title = name

    return {
        "case_id": req.case_id,
        "title": title,
        "model": model.model_dump(),
        "old_body": old_body,
        "new_body": v["body"],
        "valid": v["valid"],
        "errors": v["errors"],
        "warnings": v["warnings"],
        "migrator_warnings": migrator_warnings,
    }


@app.post("/api/testrail/section")
async def create_section(req: SectionRequest):
    payload: Dict[str, Any] = {"name": req.name}
    if req.suite_id:
        payload["suite_id"] = req.suite_id
    if req.parent_id:
        payload["parent_id"] = req.parent_id
    section = _tr_call(_tr().add_section, req.project_id, **payload)
    return {"id": section["id"], "name": section["name"]}


@app.post("/api/testrail/publish")
async def publish(req: PublishRequest):
    known_vars = known_shared = None
    try:
        suite_cases = _tr().get_cases(req.project_id, req.suite_id)
        known_vars, known_shared = _suite_context(suite_cases)
    except Exception:
        pass  # cross-reference warnings are best-effort; never block publish on them
    result = validate_case(req.model, known_vars=known_vars, known_shared=known_shared)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"]})

    title = case_title(req.model)
    body = result["body"]
    tr = _tr()

    if req.case_id:
        case = _tr_call(tr.update_case, req.case_id, title=title, custom_preconds=body)
        case_id = case.get("id", req.case_id) if isinstance(case, dict) else req.case_id
        action = "updated"
    else:
        if not req.section_id:
            raise HTTPException(status_code=422, detail="section_id is required to create a case")
        # custom_automation_status is required in some projects but not all —
        # retry without it if the project rejects it.
        try:
            case = tr.add_case(
                req.section_id, title=title, custom_preconds=body, custom_automation_status=5
            )
        except TestRailError:
            case = _tr_call(tr.add_case, req.section_id, title=title, custom_preconds=body)
        if not isinstance(case, dict) or "id" not in case:
            raise HTTPException(status_code=502, detail=f"add_case returned unexpected response: {case!r}")
        case_id = case["id"]
        action = "created"

    return {
        "case_id": case_id,
        "title": title,
        "action": action,
        "link": _case_link(case_id),
        "warnings": result["warnings"],
    }


@app.post("/api/testrail/run")
async def create_run(req: RunRequest):
    if not req.case_ids:
        raise HTTPException(status_code=422, detail="Select at least one case for the run")
    prefix = os.getenv("TESTRAIL_RUN_PREFIX", "EASY_BDD:")
    name = req.name.strip()
    if not name.startswith(prefix):
        name = f"{prefix} {name}"
    payload: Dict[str, Any] = {
        "name": name,
        "include_all": False,
        "case_ids": req.case_ids,
    }
    if req.suite_id:
        payload["suite_id"] = req.suite_id
    if req.description:
        payload["description"] = req.description
    run = _tr_call(_tr().add_run, req.project_id, **payload)
    return {"run_id": run["id"], "name": run["name"], "link": _run_link(run["id"])}


# --------------------------------------------------------------------------- #
# Run monitoring — browse runs, drill into tests, push results                  #
# --------------------------------------------------------------------------- #

# TestRail built-in result statuses. 3 (Untested) is the initial state and
# cannot be set via the API.
_BASE_STATUSES = {1: "Passed", 2: "Blocked", 3: "Untested", 4: "Retest", 5: "Failed"}
_status_cache: Optional[Dict[int, str]] = None


def _status_map() -> Dict[int, str]:
    """id -> label for result statuses; instance custom statuses included."""
    global _status_cache
    if _status_cache is None:
        statuses = dict(_BASE_STATUSES)
        try:
            for s in _tr().get_statuses():
                label = s.get("label") or s.get("name") or ""
                if s.get("id") and label:
                    statuses[int(s["id"])] = label
        except Exception:
            pass  # offline / older instance — the built-ins still apply
        _status_cache = statuses
    return _status_cache


def _run_summary(r: Dict[str, Any]) -> Dict[str, Any]:
    counts = {
        k: int(r.get(f"{k}_count") or 0)
        for k in ("passed", "blocked", "untested", "retest", "failed")
    }
    run_vars = TestRailService.parse_run_vars(r.get("description"))
    return {
        "id": r["id"],
        "name": r.get("name", ""),
        "project_id": r.get("project_id"),
        "is_completed": bool(r.get("is_completed")),
        "created_on": r.get("created_on"),
        "completed_on": r.get("completed_on"),
        "counts": counts,
        "total": sum(counts.values()),
        "url": _run_link(r["id"]),
        "jenkins_job": run_vars.jenkins_job,
        "jenkins_build_url": run_vars.jenkins_build_url,
        "jenkins_build_number": run_vars.jenkins_build_number,
        "jenkins_available": r.get("project_id") in _JENKINS_PROJECT_CHOICES,
    }


@app.get("/api/testrail/runs")
async def testrail_runs(project_id: int = Query(...), limit: int = Query(50)):
    runs = _tr_call(_tr().get_runs, project_id)
    runs.sort(key=lambda r: r.get("created_on") or 0, reverse=True)
    return [_run_summary(r) for r in runs[: max(1, min(limit, 200))]]


@app.get("/api/testrail/run/{run_id}/tests")
async def testrail_run_tests(run_id: int):
    run = _tr_call(_tr().get_run, run_id)
    tests = _tr_call(_tr().get_tests, run_id)
    smap = _status_map()
    return {
        "run": _run_summary(run),
        "statuses": [{"id": sid, "label": label} for sid, label in sorted(smap.items())],
        "tests": [
            {
                "id": t["id"],
                "case_id": t.get("case_id"),
                "title": t.get("title", ""),
                "status_id": t.get("status_id"),
                "status": smap.get(t.get("status_id"), f"status {t.get('status_id')}"),
            }
            for t in tests
        ],
    }


class RunResultsRequest(BaseModel):
    case_ids: List[int]
    status_id: int = 4  # Retest
    comment: str = ""


@app.post("/api/testrail/run/{run_id}/results")
async def testrail_run_results(run_id: int, req: RunResultsRequest):
    """Set a result (default: Retest) on the selected cases in a run."""
    if not req.case_ids:
        raise HTTPException(status_code=422, detail="Select at least one test.")
    if req.status_id == 3:
        raise HTTPException(status_code=422, detail="Untested is TestRail's initial state and cannot be set via the API.")
    if req.status_id not in _status_map():
        raise HTTPException(status_code=422, detail=f"Unknown status_id {req.status_id}.")
    results = []
    for cid in req.case_ids:
        entry: Dict[str, Any] = {"case_id": cid, "status_id": req.status_id}
        if req.comment.strip():
            entry["comment"] = req.comment.strip()
        results.append(entry)
    _tr_call(_tr().add_results_for_cases, run_id, results)
    return {
        "updated": len(results),
        "status_id": req.status_id,
        "status": _status_map().get(req.status_id, ""),
        "run_url": _run_link(run_id),
    }


class JenkinsTriggerRequest(BaseModel):
    find_only: bool = False


@app.post("/api/jenkins/run/{run_id}/trigger")
async def jenkins_trigger_run(run_id: int, req: JenkinsTriggerRequest):
    """Kick off the Jenkins job that executes this TestRail run right now,
    instead of waiting for the next cron poll, and link the resulting build
    back onto the run."""
    run = _tr_call(_tr().get_run, run_id)
    project_id = run.get("project_id")
    project_choice = _JENKINS_PROJECT_CHOICES.get(project_id)
    if not project_choice:
        raise HTTPException(
            status_code=422,
            detail=f"No Jenkins job is mapped to TestRail project {project_id}.",
        )

    job_name = os.getenv("JENKINS_MANUAL_JOB", "EasyBDD - Manual Run")
    params = {
        "PROJECT_ID": project_choice,
        "RUN_ID": str(run_id),
        "RUN_PREFIX": os.getenv("TESTRAIL_RUN_PREFIX", "EASYBDD:"),
        "FIND_ONLY": "true" if req.find_only else "false",
    }
    queue_url = _jenkins_call(_jenkins().trigger_build, job_name, params)
    build = _jenkins_call(_jenkins().resolve_queue_item, queue_url)

    run_vars = TestRailService.parse_run_vars(run.get("description"))
    run_vars.jenkins_job = job_name
    run_vars.jenkins_build_url = build["url"] if build else None
    run_vars.jenkins_build_number = build["number"] if build else None
    _tr_call(_tr().update_run, run_id, description=json.dumps(run_vars.to_dict()))

    return {
        "job": job_name,
        "queue_url": queue_url,
        "queued": build is None,
        "build_url": build["url"] if build else None,
        "build_number": build["number"] if build else None,
        "run_url": _run_link(run_id),
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("BUILDER_PORT", "8091"))
    uvicorn.run(app, host="0.0.0.0", port=port)
