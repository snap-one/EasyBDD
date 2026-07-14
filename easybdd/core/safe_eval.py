"""
Safe expression evaluation for Easy BDD Framework

Provides secure evaluation of user expressions with restricted builtins.
"""

import ast
import operator
from typing import Any, Dict


def _contains(container: Any, item: Any) -> bool:
    """Check if item is contained in container, casting both to str for substring checks.

    Lets expressions write contains(last_response, 'error') instead of
    'error' in str(last_response), regardless of whether last_response is
    already a string or some other type (dict, list, etc).
    """
    if isinstance(container, str) or isinstance(item, str):
        return str(item) in str(container)
    return item in container


def _not_contains(container: Any, item: Any) -> bool:
    """Inverse of contains() — see contains() docstring."""
    return not _contains(container, item)


class SafeEvaluator:
    """Safe expression evaluator with restricted operations."""

    # Allowed operators
    SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge,
        ast.Eq: operator.eq,
        ast.NotEq: operator.ne,
        ast.And: operator.and_,
        ast.Or: operator.or_,
        ast.Not: operator.not_,
        ast.In: lambda x, y: x in y,
        ast.NotIn: lambda x, y: x not in y,
        ast.Is: operator.is_,
        ast.IsNot: operator.is_not,
    }

    # Allowed built-in functions
    SAFE_BUILTINS = {
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        "abs": abs,
        "min": min,
        "max": max,
        "sum": sum,
        "round": round,
        "range": range,
        "enumerate": enumerate,
        "zip": zip,
        "sorted": sorted,
        "reversed": reversed,
        "any": any,
        "all": all,
        "isinstance": isinstance,
        "type": type,
        "contains": _contains,
        "not_contains": _not_contains,
    }

    def __init__(self, context: Dict[str, Any] = None):
        """
        Initialize safe evaluator.

        Args:
            context: Dictionary of allowed variables
        """
        self.context = context or {}

    def eval(self, expression: str) -> Any:
        """
        Safely evaluate an expression.

        Args:
            expression: Python expression string

        Returns:
            Result of expression evaluation

        Raises:
            ValueError: If expression contains unsafe operations
        """
        if not expression or not isinstance(expression, str):
            raise ValueError("Expression must be a non-empty string")

        try:
            # Parse the expression
            tree = ast.parse(expression, mode="eval")

            # Validate the AST (no function calls to unsafe functions)
            self._validate_ast(tree)

            # Evaluate with restricted namespace
            namespace = {"__builtins__": self.SAFE_BUILTINS, **self.context}

            result = eval(compile(tree, "<string>", "eval"), namespace)
            return result

        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {e}")
        except Exception as e:
            raise ValueError(f"Expression evaluation error: {e}")

    def _validate_ast(self, node: ast.AST):
        """
        Validate AST node to ensure it only contains safe operations.

        Args:
            node: AST node to validate

        Raises:
            ValueError: If node contains unsafe operations
        """
        # Allow basic expressions and operators
        safe_nodes = (
            ast.Expression,
            ast.Compare,
            ast.BinOp,
            ast.UnaryOp,
            ast.BoolOp,
            ast.Constant,
            ast.Num,
            ast.Str,
            ast.NameConstant,
            ast.Name,
            ast.Load,
            ast.Attribute,
            ast.Subscript,
            ast.Index,
            ast.Slice,
            ast.List,
            ast.Tuple,
            ast.Dict,
            ast.ListComp,
            ast.DictComp,
            ast.SetComp,
            ast.GeneratorExp,
            ast.comprehension,
            ast.keyword,
            # Comparison operators
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
            ast.Is,
            ast.IsNot,
            ast.In,
            ast.NotIn,
            # Binary operators
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.LShift,
            ast.RShift,
            ast.BitOr,
            ast.BitXor,
            ast.BitAnd,
            # Unary operators
            ast.Invert,
            ast.Not,
            ast.UAdd,
            ast.USub,
            # Boolean operators
            ast.And,
            ast.Or,
        )

        for child in ast.walk(node):
            # Check for function calls
            if isinstance(child, ast.Call):
                # Only allow calls to safe built-ins
                if isinstance(child.func, ast.Name):
                    func_name = child.func.id
                    if func_name not in self.SAFE_BUILTINS:
                        raise ValueError(f"Function call not allowed: {func_name}")
                elif isinstance(child.func, ast.Attribute):
                    # Allow some method calls on known objects
                    self._validate_method_call(child)
                else:
                    raise ValueError("Complex function calls not allowed")

            # Check for imports
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                raise ValueError("Import statements not allowed")

            # Check for assignments
            elif isinstance(child, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                raise ValueError("Assignment operations not allowed")

            # Check for attribute deletion
            elif isinstance(child, ast.Delete):
                raise ValueError("Delete operations not allowed")

            # Ensure all nodes are in safe list
            elif not isinstance(child, safe_nodes):
                raise ValueError(f"Unsafe operation: {child.__class__.__name__}")

    def _validate_method_call(self, call_node: ast.Call):
        """
        Validate method calls on objects.

        Args:
            call_node: AST Call node

        Raises:
            ValueError: If method call is unsafe
        """
        # Allowed method names (whitelist approach)
        safe_methods = {
            "get",
            "keys",
            "values",
            "items",  # dict methods
            "count",
            "index",  # list/string methods
            "split",
            "join",
            "strip",
            "lower",
            "upper",  # string methods
            "replace",
            "startswith",
            "endswith",  # string methods
            "isdigit",
            "isalpha",
            "isalnum",  # string checks
        }

        if isinstance(call_node.func, ast.Attribute):
            method_name = call_node.func.attr
            if method_name not in safe_methods:
                raise ValueError(f"Method call not allowed: {method_name}")


def safe_eval(expression: str, context: Dict[str, Any] = None) -> Any:
    """
    Convenience function for safe expression evaluation.

    Args:
        expression: Python expression to evaluate
        context: Dictionary of variables available in expression

    Returns:
        Result of expression evaluation

    Example:
        >>> safe_eval("x + y", {"x": 1, "y": 2})
        3
        >>> safe_eval("status_code == 200", {"status_code": 200})
        True
    """
    evaluator = SafeEvaluator(context)
    return evaluator.eval(expression)
