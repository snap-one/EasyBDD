"""Shared utilities for building TestRail case content."""


def build_testrail_preconditions(steps: list) -> str:
    """Build a TestRail preconditions string from a list of easy_bdd step dicts.

    Each step gets a numbered YAML comment (# N. action) so steps are easy to
    identify in TestRail without affecting parsing or execution.  Params are
    written flush-left so _fix_step_list_indent can recover indentation.
    """
    lines = ["steps:"]
    step_num = 0
    for step in steps:
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
                    lines.append(f"{k}: {v}")
        else:
            step_num += 1
            lines.append(f"# {step_num}. step")
            lines.append(f"- {step}")
    return "\n".join(lines)
