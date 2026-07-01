"""Shared utilities for building TestRail case content."""

# Characters / patterns that require a string value to be single-quoted in YAML
_YAML_UNSAFE = ('"', "'", '[', ']', '{', '}', '#', '\n')


def _needs_quoting(v: str) -> bool:
    """Return True if string value v must be quoted to be safe YAML."""
    if not v:
        return False
    # Leading ! is a YAML tag indicator
    if v.startswith('!'):
        return True
    # ': ' inside a value creates a spurious mapping entry
    if ': ' in v:
        return True
    return any(c in v for c in _YAML_UNSAFE)


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
    """Build a TestRail preconditions string from a list of easybdd step dicts.

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
            if not params and params != 0:
                # None / empty dict / empty list → bare action with no params
                lines.append(f"- {action_key}:")
            elif isinstance(params, dict):
                lines.append(f"- {action_key}:")
                for k, v in params.items():
                    if isinstance(v, (dict, list)):
                        # Inline flow-style keeps params flush-left so
                        # _fix_step_list_indent can safely re-indent them.
                        # Block-style indented children break re-indentation.
                        # yaml flow dump preserves native scalar types
                        # (0 / false stay unquoted) unlike str()-quoting.
                        import yaml as _yaml
                        inner = _yaml.safe_dump(
                            v, default_flow_style=True, width=100000
                        ).strip()
                        lines.append(f"{k}: {inner}")
                    elif isinstance(v, str) and _needs_quoting(v):
                        safe = v.replace("'", "''")
                        lines.append(f"{k}: '{safe}'")
                    else:
                        lines.append(f"{k}: {v}")
            else:
                # Scalar value (string, int, bool) — write inline.
                # This covers shared_step: "Slug_Name" and similar single-value steps.
                val_str = str(params)
                if isinstance(params, str) and _needs_quoting(params):
                    val_str = f"'{params.replace(chr(39), chr(39)*2)}'"
                lines.append(f"- {action_key}: {val_str}")
        else:
            step_num += 1
            lines.append(f"# {step_num}. step")
            lines.append(f"- {step}")
    return "\n".join(lines)
