"""
Custom assertions and validators for the Easy BDD Framework.

This module provides a powerful assertion engine that supports:
- Safe expression evaluation with custom operators
- JSON schema validation
- Response validation (status, headers, body)
- Complex assertion expressions

Author: Easy BDD Framework
Date: November 22, 2025
"""

import ast
import json
import operator
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union


def _path_get(obj: Any, path: str, default: Any = None) -> Any:
    """Traverse a nested dict/list using a dot-separated path string.

    Example: path(last_json, 'restful_res.systemInfo') returns the nested dict,
    or `default` (None) if any key is missing or obj is not a dict at that level.
    """
    for key in str(path).split("."):
        if isinstance(obj, dict):
            obj = obj.get(key, default)
        elif isinstance(obj, (list, tuple)):
            try:
                obj = obj[int(key)]
            except (ValueError, IndexError):
                return default
        else:
            return default
        if obj is default:
            return default
    return obj


@dataclass
class AssertionResult:
    """Result of an assertion evaluation."""

    passed: bool
    message: str
    expected: Any = None
    actual: Any = None
    details: Optional[Dict[str, Any]] = None


class AssertionEngine:
    """
    Safe expression evaluator for custom assertions.

    Supports common comparison operators and functions while preventing
    dangerous operations like file I/O, imports, or arbitrary code execution.
    """

    # Safe operators that can be used in expressions
    SAFE_OPERATORS = {
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.In: lambda x, y: x in y,
        ast.NotIn: lambda x, y: x not in y,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Mod: operator.mod,
        ast.And: operator.and_,
        ast.Or: operator.or_,
        ast.Not: operator.not_,
    }

    # Safe built-in functions
    SAFE_FUNCTIONS = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "round": round,
        "sorted": sorted,
        "list": list,
        "dict": dict,
        "set": set,
        "tuple": tuple,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "any": any,
        "all": all,
        "isinstance": isinstance,
        "type": type,
        "path": _path_get,
    }

    def __init__(self, context: Optional[Dict[str, Any]] = None):
        """
        Initialize the assertion engine.

        Args:
            context: Variable context for expression evaluation
        """
        self.context = context or {}

    def evaluate_expression(
        self, expression: str, context: Optional[Dict[str, Any]] = None
    ) -> AssertionResult:
        """
        Safely evaluate an assertion expression.

        Args:
            expression: The expression to evaluate (e.g., "len(data) > 0")
            context: Additional context variables

        Returns:
            AssertionResult with evaluation result
        """
        # Merge context
        eval_context = {**self.context, **(context or {})}

        try:
            # Parse the expression into an AST
            tree = ast.parse(expression, mode="eval")

            # Evaluate the expression safely
            result = self._eval_node(tree.body, eval_context)

            if isinstance(result, bool):
                return AssertionResult(
                    passed=result,
                    message=f"Expression '{expression}' evaluated to {result}",
                    expected=True,
                    actual=result,
                )
            else:
                # Non-boolean result is considered a failure
                return AssertionResult(
                    passed=False,
                    message=f"Expression '{expression}' did not return a boolean value",
                    expected="boolean",
                    actual=type(result).__name__,
                )

        except Exception as e:
            return AssertionResult(
                passed=False,
                message=f"Failed to evaluate expression '{expression}': {str(e)}",
                expected="valid expression",
                actual=str(e),
            )

    def _eval_node(self, node: ast.AST, context: Dict[str, Any]) -> Any:
        """
        Recursively evaluate an AST node.

        Args:
            node: AST node to evaluate
            context: Variable context

        Returns:
            Evaluated result
        """
        if isinstance(node, ast.Constant):
            return node.value

        elif isinstance(node, ast.Name):
            if node.id in context:
                return context[node.id]
            elif node.id in self.SAFE_FUNCTIONS:
                return self.SAFE_FUNCTIONS[node.id]
            else:
                raise NameError(f"Variable '{node.id}' not found in context")

        elif isinstance(node, ast.Attribute):
            obj = self._eval_node(node.value, context)
            # Allow dot-notation on dicts: response.data.restful_res.fwConfs
            if isinstance(obj, dict) and node.attr in obj:
                return obj[node.attr]
            return getattr(obj, node.attr)

        elif isinstance(node, ast.Subscript):
            obj = self._eval_node(node.value, context)
            key = self._eval_node(node.slice, context)
            return obj[key]

        elif isinstance(node, ast.Index):  # Python 3.8 compatibility
            return self._eval_node(node.value, context)

        elif isinstance(node, ast.Slice):
            lower = self._eval_node(node.lower, context) if node.lower else None
            upper = self._eval_node(node.upper, context) if node.upper else None
            step = self._eval_node(node.step, context) if node.step else None
            return slice(lower, upper, step)

        elif isinstance(node, ast.List):
            return [self._eval_node(elem, context) for elem in node.elts]

        elif isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elem, context) for elem in node.elts)

        elif isinstance(node, ast.Dict):
            return {
                self._eval_node(k, context): self._eval_node(v, context)
                for k, v in zip(node.keys, node.values)
            }

        elif isinstance(node, ast.Compare):
            left = self._eval_node(node.left, context)
            result = True
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, context)
                op_func = self.SAFE_OPERATORS.get(type(op))
                if op_func is None:
                    raise ValueError(f"Unsupported operator: {type(op).__name__}")
                result = result and op_func(left, right)
                left = right
            return result

        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, context)
            right = self._eval_node(node.right, context)
            op_func = self.SAFE_OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op_func(left, right)

        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, context)
            op_func = self.SAFE_OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
            return op_func(operand)

        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(value, context) for value in node.values)
            elif isinstance(node.op, ast.Or):
                return any(self._eval_node(value, context) for value in node.values)

        elif isinstance(node, ast.Call):
            # Allow method calls on built-in safe types (dict.get, list.append, str.lower, etc.)
            if isinstance(node.func, ast.Attribute):
                obj = self._eval_node(node.func.value, context)
                if isinstance(obj, (dict, list, str, int, float, bool, tuple, set, bytes)):
                    func = getattr(obj, node.func.attr)
                    args = [self._eval_node(arg, context) for arg in node.args]
                    kwargs = {
                        kw.arg: self._eval_node(kw.value, context)
                        for kw in node.keywords
                    }
                    return func(*args, **kwargs)
                raise ValueError(
                    f"Method calls on {type(obj).__name__} are restricted for security"
                )

            func = self._eval_node(node.func, context)
            args = [self._eval_node(arg, context) for arg in node.args]
            kwargs = {
                kw.arg: self._eval_node(kw.value, context) for kw in node.keywords
            }

            # Only allow safe free functions
            if func not in self.SAFE_FUNCTIONS.values():
                raise ValueError("Function calls are restricted for security")

            return func(*args, **kwargs)

        elif isinstance(node, ast.IfExp):
            test = self._eval_node(node.test, context)
            if test:
                return self._eval_node(node.body, context)
            else:
                return self._eval_node(node.orelse, context)

        else:
            raise ValueError(f"Unsupported AST node type: {type(node).__name__}")

    def assert_expression(
        self,
        expression: str,
        message: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AssertionResult:
        """
        Assert that an expression is true.

        Args:
            expression: Expression to evaluate
            message: Custom error message
            context: Additional context variables

        Returns:
            AssertionResult
        """
        result = self.evaluate_expression(expression, context)

        if not result.passed and message:
            result.message = message

        return result

    def contains(self, container: Any, item: Any) -> bool:
        """Check if container contains item (helper for expressions)."""
        return item in container


class JSONSchemaValidator:
    """Validator for JSON Schema validation."""

    def __init__(self):
        """Initialize the JSON schema validator."""
        try:
            import jsonschema

            self.jsonschema = jsonschema
            self.available = True
        except ImportError:
            self.available = False

    def validate(self, data: Any, schema: Union[Dict, str, Path]) -> AssertionResult:
        """
        Validate data against a JSON schema.

        Args:
            data: Data to validate
            schema: Schema dict, file path, or Path object

        Returns:
            AssertionResult
        """
        if not self.available:
            return AssertionResult(
                passed=False,
                message="jsonschema library is not installed. Install with: pip install jsonschema",
                expected="jsonschema installed",
                actual="not installed",
            )

        # Load schema if it's a file path
        if isinstance(schema, (str, Path)):
            schema_path = Path(schema)
            if not schema_path.exists():
                return AssertionResult(
                    passed=False,
                    message=f"Schema file not found: {schema_path}",
                    expected="schema file exists",
                    actual="file not found",
                )

            try:
                with open(schema_path, "r") as f:
                    schema = json.load(f)
            except Exception as e:
                return AssertionResult(
                    passed=False,
                    message=f"Failed to load schema file: {str(e)}",
                    expected="valid JSON schema file",
                    actual=str(e),
                )

        # Validate the data
        try:
            self.jsonschema.validate(instance=data, schema=schema)
            return AssertionResult(
                passed=True,
                message="Data validates against schema",
                expected="valid data",
                actual="valid",
            )
        except self.jsonschema.ValidationError as e:
            return AssertionResult(
                passed=False,
                message=f"JSON schema validation failed: {e.message}",
                expected="valid data",
                actual=e.message,
                details={
                    "path": list(e.absolute_path),
                    "validator": e.validator,
                    "validator_value": e.validator_value,
                },
            )
        except Exception as e:
            return AssertionResult(
                passed=False,
                message=f"Schema validation error: {str(e)}",
                expected="valid schema",
                actual=str(e),
            )


class ResponseValidator:
    """Validator for HTTP response assertions."""

    def validate_response(
        self, response: Dict[str, Any], expectations: Dict[str, Any]
    ) -> AssertionResult:
        """
        Validate an HTTP response against expectations.

        Args:
            response: Response dict with status, headers, body, etc.
            expectations: Expected values for status, headers, body patterns, etc.

        Returns:
            AssertionResult
        """
        failures = []

        # Validate status code (support both "status" and "status_code" keys)
        expected_status = None
        if "status" in expectations:
            expected_status = expectations["status"]
        elif "status_code" in expectations:
            expected_status = expectations["status_code"]

        if expected_status is not None:
            actual_status = response.get("status") or response.get("status_code")
            if actual_status != expected_status:
                failures.append(
                    f"Status code mismatch: expected {expected_status}, got {actual_status}"
                )

        # Validate headers
        if "headers" in expectations:
            response_headers = response.get("headers", {})

            for header_name, expected_value in expectations["headers"].items():
                # Case-insensitive header name matching
                actual_value = None
                for resp_header, resp_value in response_headers.items():
                    if resp_header.lower() == header_name.lower():
                        actual_value = resp_value
                        break

                if actual_value is None:
                    failures.append(f"Header '{header_name}' not found in response")
                elif (
                    isinstance(expected_value, str)
                    and expected_value not in actual_value
                ):
                    failures.append(
                        f"Header '{header_name}': expected to contain '{expected_value}', got '{actual_value}'"
                    )
                elif (
                    not isinstance(expected_value, str)
                    and actual_value != expected_value
                ):
                    failures.append(
                        f"Header '{header_name}': expected {expected_value}, got '{actual_value}'"
                    )

        # Validate body patterns (regex or substring)
        if "body_contains" in expectations:
            body = response.get("body", "")
            if isinstance(body, dict):
                body = json.dumps(body)

            patterns = expectations["body_contains"]
            if isinstance(patterns, str):
                patterns = [patterns]

            for pattern in patterns:
                if pattern not in str(body):
                    failures.append(
                        f"Body does not contain expected pattern: '{pattern}'"
                    )

        # Validate body regex
        if "body_matches" in expectations:
            body = response.get("body", "")
            if isinstance(body, dict):
                body = json.dumps(body)

            pattern = expectations["body_matches"]
            if not re.search(pattern, str(body)):
                failures.append(f"Body does not match regex pattern: '{pattern}'")

        # Validate response time
        if "max_response_time" in expectations:
            max_time = expectations["max_response_time"]
            actual_time = response.get("response_time", 0)

            if actual_time > max_time:
                failures.append(
                    f"Response time {actual_time}ms exceeded maximum {max_time}ms"
                )

        # Build result
        if failures:
            return AssertionResult(
                passed=False,
                message=f"Response validation failed: {'; '.join(failures)}",
                expected=expectations,
                actual=response,
                details={"failures": failures},
            )
        else:
            return AssertionResult(
                passed=True,
                message="Response validates against all expectations",
                expected=expectations,
                actual=response,
            )
