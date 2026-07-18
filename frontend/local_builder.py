"""Easy BDD Local Test Builder — backend.

A local-filesystem-backed sibling of frontend/testrail_builder.py: the same
case/step model, action catalog, and validation/serialization logic (shared
via frontend/builder_core.py), but cases, shared steps, and variables are
stored as plain YAML files under LOCAL_BUILDER_TESTS_DIR instead of being
pushed to TestRail. Serves the same frontend/static/testrail_builder.html —
the page detects which backend it's talking to via /api/local/status vs
/api/testrail/status.

Hierarchy mapping (TestRail Project > Suite > Section > Case):
  * Project  -> top-level folder under LOCAL_BUILDER_TESTS_DIR ("workspace")
  * Section  -> one level of subfolder under a workspace
  * Case     -> one .yaml file, tagged with an advisory `role:` key
                (feature | setup | teardown)
  * Var:/Shared: cases don't become case files — they're entries in a
    workspace-scoped vars.yaml / shared_steps.yaml, the same file format
    easybdd.core.parser.YAMLParser already reads at execution time.

Execution runs straight through easybdd.core.runner.TestRunner — the same
engine every other entry point (CLI, MCP server, TestRail runner) uses.

Start with:  python frontend/start_local_builder.py   (default port 9093)
"""

from __future__ import annotations

import os
import re
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

import yaml
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from easybdd.core.parser import fix_step_list_indent, parse_yaml_lenient, strip_html_to_text  # noqa: E402

from local_runner import (  # noqa: E402
    LocalRunStore,
    execute_run,
    new_run_id,
    report_context,
    run_summary,
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
    _slug as _shared_slug,
    case_title,
    convert_recording_text,
    parse_case_to_model,
    serialize_case_body,
    validate_case,
)

app = FastAPI(
    title="Easy BDD Local Test Builder",
    description="Author Feature/Setup/Teardown/Var/Shared cases visually, stored as local YAML files",
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

TESTS_DIR = Path(os.getenv("LOCAL_BUILDER_TESTS_DIR", str(ROOT / "tests" / "cases"))).resolve()
TESTS_DIR.mkdir(parents=True, exist_ok=True)

RUNS_DIR = Path(os.getenv("LOCAL_BUILDER_RUNS_DIR", str(ROOT / "reports" / "local_runs"))).resolve()
RUN_STORE = LocalRunStore(RUNS_DIR)

# Case files carry a `role:` key limited to these — Var:/Shared: never
# materialize as case files (see module docstring).
_LOCAL_CASE_ROLES = {"feature", "setup", "teardown"}
_RESERVED_FILENAMES = {"shared_steps.yaml", "vars.yaml"}

_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _assert_safe_name(value: str, label: str = "name") -> None:
    """Reject any path segment that isn't a simple word (no slashes, dots, ..)."""
    if not _SAFE_NAME_RE.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}: must match [A-Za-z0-9_-]+")


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_").lower()
    return s or "case"


def _workspace_dir(project_id: str) -> Path:
    _assert_safe_name(project_id, "project_id")
    return TESTS_DIR / project_id


def _section_dir(project_id: str, section_id: Optional[str]) -> Path:
    base = _workspace_dir(project_id)
    if not section_id:
        return base
    _assert_safe_name(section_id, "section_id")
    return base / section_id


def _case_file_id(path: Path) -> str:
    """Relative-to-TESTS_DIR posix path — the case's opaque id."""
    return path.resolve().relative_to(TESTS_DIR).as_posix()


def _case_path_from_id(case_id: str) -> Path:
    candidate = TESTS_DIR / case_id
    resolved = candidate.resolve()
    if TESTS_DIR not in resolved.parents:
        raise HTTPException(status_code=400, detail="Invalid case id")
    return resolved


def _iter_case_files(base: Path):
    if not base.exists():
        return
    for f in sorted(base.glob("*.yaml")):
        if f.name in _RESERVED_FILENAMES:
            continue
        yield f


# --------------------------------------------------------------------------- #
# Scope resolution — shared by shared-steps and vars CRUD                     #
# --------------------------------------------------------------------------- #

def _scope_dir(scope: str) -> Path:
    """Resolve a scope name ('global', 'workspace', or 'workspace/section') to
    the directory its shared_steps.yaml / vars.yaml lives in."""
    if scope == "global":
        return TESTS_DIR
    parts = scope.split("/")
    if len(parts) > 2 or not all(parts):
        raise HTTPException(
            status_code=400,
            detail="Scope must be 'global', a workspace name, or 'workspace/section'",
        )
    for p in parts:
        _assert_safe_name(p, "scope segment")
    candidate = TESTS_DIR.joinpath(*parts)
    resolved = candidate.resolve()
    if TESTS_DIR not in resolved.parents and resolved != TESTS_DIR:
        raise HTTPException(status_code=400, detail="Invalid scope")
    return resolved


def _shared_steps_path(scope: str) -> Path:
    return _scope_dir(scope) / "shared_steps.yaml"


def _vars_path(scope: str) -> Path:
    return _scope_dir(scope) / "vars.yaml"


def _load_yaml_dict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_yaml_dict(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100000)


def _all_scopes() -> List[str]:
    scopes = ["global"]
    if not TESTS_DIR.exists():
        return scopes
    for d in sorted(TESTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        if (d / "shared_steps.yaml").exists() or (d / "vars.yaml").exists():
            scopes.append(d.name)
        for sub in sorted(d.iterdir()):
            if sub.is_dir() and ((sub / "shared_steps.yaml").exists() or (sub / "vars.yaml").exists()):
                scopes.append(f"{d.name}/{sub.name}")
    return scopes


def _workspace_context(project_id: str) -> tuple:
    """Collect (known var names, known shared-step names) visible to a
    workspace — global scope, the workspace itself, and its sections — for
    validate_case's best-effort cross-reference warnings."""
    scopes = ["global", project_id]
    base = _workspace_dir(project_id)
    if base.exists():
        for d in sorted(base.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                scopes.append(f"{project_id}/{d.name}")

    known_vars: List[str] = []
    known_shared: List[str] = []
    for scope in scopes:
        for var_set in _load_yaml_dict(_vars_path(scope)).values():
            if isinstance(var_set, dict):
                known_vars.extend(str(k) for k in var_set.keys())
        known_shared.extend(_load_yaml_dict(_shared_steps_path(scope)).keys())
    return sorted(set(known_vars)), sorted(set(known_shared))


# --------------------------------------------------------------------------- #
# Case file <-> model                                                         #
# --------------------------------------------------------------------------- #

def _local_case_to_model(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a parsed local case-file dict to a builder model."""
    role = data.get("role") or "feature"
    if role not in _LOCAL_CASE_ROLES:
        role = "feature"
    name = data.get("name", "") or ""
    model: Dict[str, Any] = {
        "case_type": role,
        "name": name,
        "variables": [{"key": str(k), "value": v} for k, v in (data.get("variables") or {}).items()],
        "data_rows": (
            yaml.safe_dump(data["data"], default_flow_style=False, width=100000).rstrip()
            if data.get("data") else None
        ),
        "steps": [],
    }
    steps = data.get("steps") or []
    nodes = [_dict_to_node(s) for s in steps if isinstance(s, dict)]
    model["steps"] = [n.model_dump() for n in nodes]
    return {"model": model, "notes": []}


def _model_to_file_dict(model: CaseModel, body: str) -> Dict[str, Any]:
    """Round-trip a validated case body through the runner's own parser
    (fix_step_list_indent + parse_yaml_lenient) to get a proper nested dict
    instead of the flush-left text serialize_case_body produces — that text
    is TestRail-rich-text-flushed, not directly writable to a local file."""
    fixed = fix_step_list_indent(body)
    parsed = parse_yaml_lenient(fixed)
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=500, detail="Generated body did not parse into the expected structure")
    out: Dict[str, Any] = {"name": model.name.strip(), "role": model.case_type}
    out.update(parsed)
    return out


# --------------------------------------------------------------------------- #
# Routes — index / catalog / preview / validate / import (backend-agnostic)   #
# --------------------------------------------------------------------------- #

@app.get("/")
async def index():
    page = STATIC_DIR / "testrail_builder.html"
    if not page.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Builder UI file is missing: {page}. Ensure frontend/static/testrail_builder.html is deployed.",
        )
    return FileResponse(page)


@app.get("/api/catalog")
async def get_catalog():
    categories: Dict[str, List[Dict[str, Any]]] = {}
    for action_id, definition in sorted(CATALOG.items()):
        categories.setdefault(definition["category"], []).append({"id": action_id, **definition})
    return {"categories": categories, "case_types": CASE_PREFIXES}


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


@app.post("/api/import/recording")
async def import_recording(req: ImportRecordingRequest):
    """Convert clipboard-pasted recorder output into builder step nodes."""
    try:
        result = convert_recording_text(req.text, req.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    raw_steps = [s for s in result.get("steps") or [] if isinstance(s, dict)]
    if not req.include_logs:
        raw_steps = [s for s in raw_steps if set(s) != {"test.log"}]

    nodes = [_dict_to_node(s) for s in raw_steps]
    if not nodes:
        raise HTTPException(
            status_code=400,
            detail=f"Recognized the recording as {result['format']}, but found no convertible steps in it.",
        )
    variables = [{"key": str(k), "value": v} for k, v in (result.get("variables") or {}).items()]
    return {
        "format": result["format"],
        "name": result.get("name") or "",
        "steps": [n.model_dump() for n in nodes],
        "variables": variables,
        "warnings": [],
    }


# --------------------------------------------------------------------------- #
# Routes — projects / sections / cases                                        #
# --------------------------------------------------------------------------- #

@app.get("/api/local/status")
async def local_status():
    return {"configured": True, "tests_dir": str(TESTS_DIR), "suite_mode": False}


@app.get("/api/local/projects")
async def list_projects():
    if not TESTS_DIR.exists():
        return []
    return [
        {"id": d.name, "name": d.name, "suite_mode": False}
        for d in sorted(TESTS_DIR.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]


@app.post("/api/local/projects")
async def create_project(name: str = Query(...)):
    slug = _slug(name)
    path = TESTS_DIR / slug
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Workspace '{slug}' already exists")
    path.mkdir(parents=True)
    return {"id": slug, "name": slug}


@app.get("/api/local/sections")
async def list_sections(project_id: str = Query(...)):
    base = _workspace_dir(project_id)
    if not base.exists():
        return []
    return [
        {"id": d.name, "name": d.name, "parent_id": None, "depth": 0}
        for d in sorted(base.iterdir())
        if d.is_dir() and not d.name.startswith(".")
    ]


class LocalSectionRequest(BaseModel):
    project_id: str
    name: str


@app.post("/api/local/section")
async def create_section(req: LocalSectionRequest):
    base = _workspace_dir(req.project_id)
    base.mkdir(parents=True, exist_ok=True)
    slug = _slug(req.name)
    path = base / slug
    if path.exists():
        raise HTTPException(status_code=409, detail=f"Section '{slug}' already exists")
    path.mkdir(parents=True)
    return {"id": slug, "name": slug}


@app.get("/api/local/cases")
async def list_cases(project_id: str = Query(...), section_id: Optional[str] = Query(None)):
    base = _section_dir(project_id, section_id)
    out = []
    for f in _iter_case_files(base):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            out.append({
                "id": _case_file_id(f), "title": f.stem, "section_id": section_id,
                "role": "other", "error": f"Invalid YAML: {exc}",
            })
            continue
        role = data.get("role") or "feature"
        if role not in _LOCAL_CASE_ROLES:
            role = "feature"
        title = f"{CASE_PREFIXES[role]} {data.get('name', f.stem)}"
        out.append({"id": _case_file_id(f), "title": title, "section_id": section_id, "role": role})
    return out


@app.get("/api/local/case/{case_id:path}")
async def get_case(case_id: str):
    path = _case_path_from_id(case_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Case not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Case file is not valid YAML: {exc}")

    result = _local_case_to_model(data)
    parts = Path(case_id).parts
    result["case_id"] = case_id
    result["project_id"] = parts[0] if parts else None
    result["section_id"] = parts[1] if len(parts) == 3 else None
    result["link"] = ""
    return result


@app.delete("/api/local/case/{case_id:path}")
async def delete_case(case_id: str):
    path = _case_path_from_id(case_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Case not found")
    path.unlink()
    return {"case_id": case_id, "status": "deleted"}


class LocalPublishRequest(BaseModel):
    model: CaseModel
    project_id: str
    section_id: Optional[str] = None
    case_id: Optional[str] = None  # existing relative path, to update in place


@app.post("/api/local/publish")
async def publish(req: LocalPublishRequest):
    model = req.model

    if model.case_type == "var":
        if model.steps:
            raise HTTPException(
                status_code=422,
                detail="Step-based Var: cases aren't supported in the local builder yet — "
                       "use plain key/value variables, or author this as a Setup: case instead.",
            )
        variables = {row.key.strip(): row.value for row in model.variables if row.key.strip()}
        if not variables:
            raise HTTPException(status_code=422, detail="Var: case needs at least one key/value pair")
        scope = req.project_id
        path = _vars_path(scope)
        data = _load_yaml_dict(path)
        data[model.name.strip()] = variables
        _save_yaml_dict(path, data)
        return {
            "case_id": f"var:{scope}:{model.name.strip()}", "title": case_title(model),
            "action": "created", "link": "", "warnings": [],
        }

    if model.case_type == "shared":
        result = validate_case(model)
        if not result["valid"]:
            raise HTTPException(status_code=422, detail={"errors": result["errors"]})
        fixed = fix_step_list_indent(result["body"])
        parsed = parse_yaml_lenient(fixed)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("steps"), list):
            raise HTTPException(status_code=500, detail="Generated shared-step body did not parse as expected")
        entry: Dict[str, Any] = {"description": ""}
        params = [row.key.strip() for row in model.variables if row.key.strip()]
        if params:
            entry["parameters"] = params
        entry["steps"] = parsed["steps"]
        scope = req.project_id
        path = _shared_steps_path(scope)
        data = _load_yaml_dict(path)
        data[model.name.strip()] = entry
        _save_yaml_dict(path, data)
        return {
            "case_id": f"shared:{scope}:{model.name.strip()}", "title": case_title(model),
            "action": "created", "link": "", "warnings": result["warnings"],
        }

    if model.case_type not in _LOCAL_CASE_ROLES:
        raise HTTPException(status_code=422, detail=f"Unknown case type '{model.case_type}'")

    known_vars, known_shared = _workspace_context(req.project_id)
    result = validate_case(model, known_vars=known_vars, known_shared=known_shared)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail={"errors": result["errors"]})

    file_data = _model_to_file_dict(model, result["body"])

    if req.case_id:
        path = _case_path_from_id(req.case_id)
        action = "updated"
    else:
        base = _section_dir(req.project_id, req.section_id)
        base.mkdir(parents=True, exist_ok=True)
        stem = _slug(model.name)
        path = base / f"{stem}.yaml"
        suffix = 2
        while path.exists():
            path = base / f"{stem}_{suffix}.yaml"
            suffix += 1
        action = "created"

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(file_data, fh, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100000)

    return {
        "case_id": _case_file_id(path), "title": case_title(model),
        "action": action, "link": "", "warnings": result["warnings"],
    }


class LocalLintRequest(BaseModel):
    project_id: str


@app.post("/api/local/lint")
async def lint_workspace(req: LocalLintRequest):
    """Health-check every case file in a workspace with the builder's validation."""
    base = _workspace_dir(req.project_id)
    known_vars, known_shared = _workspace_context(req.project_id)
    sections: List[Optional[str]] = [None]
    if base.exists():
        sections.extend(
            d.name for d in sorted(base.iterdir()) if d.is_dir() and not d.name.startswith(".")
        )

    results = []
    counts = {"checked": 0, "clean": 0, "errors": 0, "warnings": 0}
    for section in sections:
        for f in _iter_case_files(_section_dir(req.project_id, section)):
            counts["checked"] += 1
            case_id = _case_file_id(f)
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                results.append({
                    "case_id": case_id, "title": f.stem, "role": "other", "section_id": section,
                    "errors": [f"Invalid YAML: {exc}"], "warnings": [], "link": "",
                })
                counts["errors"] += 1
                continue

            parsed = _local_case_to_model(data)
            title = f"{CASE_PREFIXES.get(parsed['model']['case_type'], '')} {parsed['model']['name']}".strip()
            try:
                model = CaseModel(**parsed["model"])
                v = validate_case(model, known_vars=known_vars, known_shared=known_shared)
                errors, warnings = v["errors"], v["warnings"]
            except Exception as exc:
                errors, warnings = [f"Could not validate: {exc}"], []

            if errors or warnings:
                results.append({
                    "case_id": case_id, "title": title, "role": parsed["model"]["case_type"],
                    "section_id": section, "errors": errors, "warnings": warnings, "link": "",
                })
                counts["errors" if errors else "warnings"] += 1
            else:
                counts["clean"] += 1
    return {"counts": counts, "issues": results}


# --------------------------------------------------------------------------- #
# Routes — shared steps CRUD                                                  #
# --------------------------------------------------------------------------- #

class SharedStepModel(BaseModel):
    name: str
    description: str = ""
    scope: str = "global"
    parameters: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]] = Field(default_factory=list)


@app.get("/api/shared-steps")
async def list_shared_steps(scope: Optional[str] = None):
    scopes = [scope] if scope else _all_scopes()
    items = []
    for sc in scopes:
        data = _load_yaml_dict(_shared_steps_path(sc))
        for name, body in data.items():
            if not isinstance(body, dict):
                continue
            items.append({
                "name": name, "description": body.get("description", ""), "scope": sc,
                "parameters": body.get("parameters", []), "steps": body.get("steps", []),
            })
    return {"shared_steps": items, "total": len(items), "scopes": _all_scopes()}


@app.post("/api/shared-steps")
async def create_shared_step(step: SharedStepModel):
    path = _shared_steps_path(step.scope)
    data = _load_yaml_dict(path)
    if step.name in data:
        raise HTTPException(status_code=409, detail=f"Shared step '{step.name}' already exists in scope '{step.scope}'")
    entry: Dict[str, Any] = {"description": step.description}
    if step.parameters:
        entry["parameters"] = step.parameters
    entry["steps"] = step.steps
    data[step.name] = entry
    _save_yaml_dict(path, data)
    return {"name": step.name, "scope": step.scope, "status": "created"}


@app.put("/api/shared-steps/{name}")
async def update_shared_step(name: str, step: SharedStepModel, scope: str = "global"):
    path = _shared_steps_path(scope)
    data = _load_yaml_dict(path)
    entry: Dict[str, Any] = {"description": step.description}
    if step.parameters:
        entry["parameters"] = step.parameters
    entry["steps"] = step.steps
    if step.name != name and name in data:
        del data[name]
    data[step.name] = entry
    _save_yaml_dict(path, data)
    return {"name": step.name, "scope": scope, "status": "updated"}


@app.delete("/api/shared-steps/{name}")
async def delete_shared_step(name: str, scope: str = "global"):
    path = _shared_steps_path(scope)
    data = _load_yaml_dict(path)
    if name not in data:
        raise HTTPException(status_code=404, detail=f"Shared step '{name}' not found in scope '{scope}'")
    del data[name]
    _save_yaml_dict(path, data)
    return {"name": name, "scope": scope, "status": "deleted"}


# --------------------------------------------------------------------------- #
# Routes — vars CRUD                                                          #
# --------------------------------------------------------------------------- #

class VarSetModel(BaseModel):
    name: str
    scope: str = "global"
    variables: Dict[str, Any] = Field(default_factory=dict)


@app.get("/api/vars")
async def list_var_sets(scope: Optional[str] = None):
    scopes = [scope] if scope else _all_scopes()
    items = []
    for sc in scopes:
        data = _load_yaml_dict(_vars_path(sc))
        for name, variables in data.items():
            if isinstance(variables, dict):
                items.append({"name": name, "scope": sc, "variables": variables})
    return {"var_sets": items, "total": len(items), "scopes": _all_scopes()}


@app.post("/api/vars")
async def create_var_set(v: VarSetModel):
    path = _vars_path(v.scope)
    data = _load_yaml_dict(path)
    if v.name in data:
        raise HTTPException(status_code=409, detail=f"Var set '{v.name}' already exists in scope '{v.scope}'")
    data[v.name] = v.variables
    _save_yaml_dict(path, data)
    return {"name": v.name, "scope": v.scope, "status": "created"}


@app.put("/api/vars/{name}")
async def update_var_set(name: str, v: VarSetModel, scope: str = "global"):
    path = _vars_path(scope)
    data = _load_yaml_dict(path)
    if v.name != name and name in data:
        del data[name]
    data[v.name] = v.variables
    _save_yaml_dict(path, data)
    return {"name": v.name, "scope": scope, "status": "updated"}


@app.delete("/api/vars/{name}")
async def delete_var_set(name: str, scope: str = "global"):
    path = _vars_path(scope)
    data = _load_yaml_dict(path)
    if name not in data:
        raise HTTPException(status_code=404, detail=f"Var set '{name}' not found in scope '{scope}'")
    del data[name]
    _save_yaml_dict(path, data)
    return {"name": name, "scope": scope, "status": "deleted"}


# --------------------------------------------------------------------------- #
# Routes — execution + persisted run history                                  #
# --------------------------------------------------------------------------- #

class LocalRunRequest(BaseModel):
    project_id: str
    case_ids: List[str]
    var_scopes: List[str] = Field(default_factory=list)
    name: Optional[str] = None


def _build_run_config(var_scopes: List[str]):
    from easybdd.core.variable_manager import GlobalConfigManager

    config = GlobalConfigManager()
    for scope in var_scopes:
        for var_set in _load_yaml_dict(_vars_path(scope)).values():
            if not isinstance(var_set, dict):
                continue
            for k, v in var_set.items():
                config.set_variable(k, v if isinstance(v, (list, dict)) else str(v), scope="collection_vars")
    return config


@app.post("/api/local/run")
async def run_cases(req: LocalRunRequest, background_tasks: BackgroundTasks):
    if not req.case_ids:
        raise HTTPException(status_code=422, detail="Select at least one case to run")

    case_paths = [_case_path_from_id(cid) for cid in req.case_ids]
    run_id = new_run_id()
    name = req.name or f"Run {run_id}"
    RUN_STORE.create(run_id, name, req.project_id, req.case_ids)

    config = _build_run_config(req.var_scopes)
    background_tasks.add_task(execute_run, RUN_STORE, run_id, config, case_paths)

    return {"run_id": run_id, "name": name, "status": "running"}


@app.get("/api/local/runs")
async def list_runs(project_id: str = Query(...), limit: int = Query(50)):
    return [run_summary(r) for r in RUN_STORE.list(project_id=project_id, limit=limit)]


@app.get("/api/local/run/{run_id}")
async def get_run(run_id: str):
    try:
        return RUN_STORE.get(run_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")


@app.get("/api/local/run/{run_id}/report")
async def get_run_report(run_id: str):
    try:
        record = RUN_STORE.get(run_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    details = record.get("test_details") or []
    if not details:
        return HTMLResponse(f"<p>Run '{run_id}' has no results yet (status: {record.get('status')}).</p>")

    from report_generator import generate_html_report

    return generate_html_report({str(i): report_context(d) for i, d in enumerate(details)})


# --------------------------------------------------------------------------- #
# Routes — Pull from TestRail (one-shot import; TestRail is used only as a    #
# data source here, never at test-run time)                                  #
# --------------------------------------------------------------------------- #

_tr_service = None


def _tr():
    from easybdd.services.testrail_service import TestRailError, TestRailService
    global _tr_service
    if _tr_service is None:
        try:
            _tr_service = TestRailService()
        except TestRailError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
    return _tr_service


def _fetch_testrail_cases(project_id: int, suite_id: Optional[int], section_id: Optional[int]) -> List[Dict[str, Any]]:
    from easybdd.services.testrail_service import TestRailError

    try:
        cases = _tr().get_cases(project_id, suite_id)
    except TestRailError as exc:
        raise HTTPException(status_code=502, detail=f"TestRail error: {exc}")
    if section_id is not None:
        cases = [c for c in cases if c.get("section_id") == section_id]
    return cases


def _clean_title(title: str, role: str) -> str:
    prefix = CASE_PREFIXES.get(role)
    return title[len(prefix):].strip() if prefix else title.strip()


def _normalize_shared_step_refs(steps: List[Any]) -> List[Any]:
    """Rewrite shared_step reference names to the slug format shared_steps.yaml
    keys use — mirrors easybdd.core.testrail_runner._normalize_shared_step_refs."""
    result = []
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("shared_step"), str):
            step = {**step, "shared_step": _shared_slug(step["shared_step"])}
        result.append(step)
    return result


def _parse_shared_case_body(text: str) -> Optional[Dict[str, Any]]:
    """Mirror TestRailRunner._sync_keyword_cases's accepted body shapes:
    full-definition dict, steps-only shorthand list, or a single-step dict."""
    try:
        parsed = parse_yaml_lenient(fix_step_list_indent(text))
    except Exception:
        return None
    if isinstance(parsed, list):
        return {"steps": _normalize_shared_step_refs([s for s in parsed if isinstance(s, dict)])}
    if isinstance(parsed, dict) and "steps" in parsed:
        return {**parsed, "steps": _normalize_shared_step_refs(parsed.get("steps") or [])}
    if isinstance(parsed, dict):
        return {"steps": _normalize_shared_step_refs([parsed])}
    return None


@app.get("/api/local/import/testrail/preview")
async def import_testrail_preview(
    project_id: int = Query(...),
    suite_id: Optional[int] = Query(None),
    section_id: Optional[int] = Query(None),
    workspace: str = Query(...),
):
    _assert_safe_name(workspace, "workspace")
    cases = _fetch_testrail_cases(project_id, suite_id, section_id)
    manifest = []
    for c in cases:
        title = c.get("title", "") or ""
        role = _classify_role(title)
        clean = _clean_title(title, role)
        if role == "shared":
            key = _shared_slug(clean)
            target, exists = f"{workspace}/shared_steps.yaml#{key}", key in _load_yaml_dict(_shared_steps_path(workspace))
        elif role == "var":
            target, exists = f"{workspace}/vars.yaml#{clean}", clean in _load_yaml_dict(_vars_path(workspace))
        elif role in _LOCAL_CASE_ROLES:
            stem = _slug(clean)
            target = f"{workspace}/{stem}.yaml"
            exists = (TESTS_DIR / workspace / f"{stem}.yaml").exists()
        elif role == "test":
            target, exists = "(pointer case — nothing to import)", False
        else:
            target, exists = "(unrecognized title prefix — skipped)", False
        manifest.append({"case_id": c["id"], "title": title, "role": role, "target": target, "exists": exists})
    return {"manifest": manifest, "total": len(manifest)}


class ImportApplyRequest(BaseModel):
    project_id: int
    suite_id: Optional[int] = None
    section_id: Optional[int] = None
    workspace: str
    overwrite: bool = False


@app.post("/api/local/import/testrail")
async def import_testrail_apply(req: ImportApplyRequest):
    _assert_safe_name(req.workspace, "workspace")
    cases = _fetch_testrail_cases(req.project_id, req.suite_id, req.section_id)

    created: List[str] = []
    updated: List[str] = []
    skipped: List[str] = []
    errors: List[str] = []

    for c in cases:
        title = c.get("title", "") or ""
        role = _classify_role(title)
        clean = _clean_title(title, role)

        try:
            if role == "shared":
                name = _shared_slug(clean)
                path = _shared_steps_path(req.workspace)
                data = _load_yaml_dict(path)
                text = strip_html_to_text(str(c.get("custom_preconds") or ""))
                if not text:
                    errors.append(f"Shared: {clean} — empty body")
                    continue
                entry = _parse_shared_case_body(text)
                if entry is None:
                    errors.append(f"Shared: {clean} — could not parse body")
                    continue
                if name in data:
                    if not req.overwrite:
                        skipped.append(f"Shared: {clean}")
                        continue
                    if data[name] == entry:
                        skipped.append(f"Shared: {clean} (unchanged)")
                        continue
                    updated.append(f"Shared: {clean}")
                else:
                    created.append(f"Shared: {clean}")
                data[name] = entry
                _save_yaml_dict(path, data)

            elif role == "var":
                path = _vars_path(req.workspace)
                data = _load_yaml_dict(path)
                if clean in data and not req.overwrite:
                    skipped.append(f"Var: {clean}")
                    continue
                parsed = parse_case_to_model(c)
                if parsed["model"]["steps"]:
                    errors.append(f"Var: {clean} — step-based Var: cases aren't supported in the local builder yet")
                    continue
                variables = {
                    row["key"]: row["value"] for row in parsed["model"]["variables"] if row["key"].strip()
                }
                if not variables:
                    errors.append(f"Var: {clean} — no key/value pairs found")
                    continue
                (updated if clean in data else created).append(f"Var: {clean}")
                data[clean] = variables
                _save_yaml_dict(path, data)

            elif role in _LOCAL_CASE_ROLES:
                parsed = parse_case_to_model(c)
                try:
                    model = CaseModel(**parsed["model"])
                except Exception as exc:
                    errors.append(f"{title} — could not build model: {exc}")
                    continue
                v = validate_case(model)
                if not v["valid"]:
                    errors.append(f"{title} — invalid: {'; '.join(v['errors'])}")
                    continue
                file_data = _model_to_file_dict(model, v["body"])
                stem = _slug(clean)
                out_path = TESTS_DIR / req.workspace / f"{stem}.yaml"
                exists = out_path.exists()
                if exists:
                    if not req.overwrite:
                        skipped.append(title)
                        continue
                    try:
                        existing_data = yaml.safe_load(out_path.read_text(encoding="utf-8")) or {}
                    except Exception:
                        existing_data = None
                    if existing_data == file_data:
                        skipped.append(f"{title} (unchanged)")
                        continue
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as fh:
                    yaml.safe_dump(file_data, fh, sort_keys=False, allow_unicode=True,
                                    default_flow_style=False, width=100000)
                (updated if exists else created).append(title)

            elif role == "test":
                body = strip_html_to_text(str(c.get("custom_preconds") or ""))
                ref_line = next(
                    (ln.strip() for ln in body.splitlines() if ln.strip().startswith(("tag:", "file:"))), None
                )
                if ref_line and ref_line.startswith("file:"):
                    ref_path = (TESTS_DIR / ref_line.split(":", 1)[1].strip()).resolve()
                    if not ref_path.exists():
                        errors.append(f"{title} — referenced file not found: {ref_path}")
                        continue
                skipped.append(f"{title} (pointer case — nothing to import)")

            else:
                skipped.append(f"{title} (unrecognized title prefix)")

        except HTTPException:
            raise
        except Exception as exc:
            errors.append(f"{title} — {exc}")

    return {"created": created, "updated": updated, "skipped_existing": skipped, "errors": errors}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("LOCAL_BUILDER_PORT", "9093"))
    uvicorn.run(app, host="0.0.0.0", port=port)
