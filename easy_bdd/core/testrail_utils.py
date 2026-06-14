"""Shared utilities for building TestRail case content."""


def _flatten_steps(steps: list) -> list:
    """Flatten one level of list/tuple nesting that bdd_migrator sometimes produces.

    parse_step_block can return steps grouped by old-format step number, so each
    item may be a list/tuple of step dicts rather than a single step dict.
    """
    flat = []
    for item in steps:
        if isinstance(item, (list, tuple)):
            flat.extend(item)
        else:
            flat.append(item)
    return flat


def build_testrail_preconditions(steps: list) -> str:
    """Build a TestRail preconditions string from a list of easy_bdd step dicts.

    Each step gets a numbered YAML comment (# N. action) so steps are easy to
    identify in TestRail without affecting parsing or execution.  Params are
    written flush-left so _fix_step_list_indent can recover indentation.
    """
    lines = ["steps:"]
    step_num = 0
    for step in _flatten_steps(steps):
        if isinstance(step, dict) and len(step) == 1:
            action_key, params = next(iter(step.items()))
            # test.log entries are annotations, not numbered test steps
            if action_key == "test.log":
                continue
            step_num += 1
            label = action_key
            if isinstance(params, dict):
                for hint_key in ("name", "label", "text", "url"):
                    if hint_key in params:
                        label = f"{action_key} ({params[hint_key]})"
                        break
            lines.append(f"# {step_num}. {label}")
            lines.append(f"- {action_key}:")
            if isinstance(params, dict):
                for k, v in params.items():
                    if isinstance(v, str) and any(c in v for c in ('"', "'", '[', ']', '{', '}', ':')):
                        # Quote values containing YAML-unsafe characters
                        safe = v.replace("'", "''")
                        lines.append(f"{k}: '{safe}'")
                    elif isinstance(v, dict):
                        lines.append(f"{k}:")
                        for dk, dv in v.items():
                            lines.append(f"  {dk}: {dv}")
                    else:
                        lines.append(f"{k}: {v}")
        else:
            step_num += 1
            lines.append(f"# {step_num}. step")
            lines.append(f"- {step}")
    return "\n".join(lines)
