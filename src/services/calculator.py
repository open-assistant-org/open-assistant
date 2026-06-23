"""Calculator service for safe mathematical expression evaluation."""

import ast
import math
import operator
import re
from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Allowed operators
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Allowed math functions and constants
_FUNCTIONS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "ceil": math.ceil,
    "floor": math.floor,
    "pi": math.pi,
    "e": math.e,
}


def calculate(expression: str) -> Dict[str, Any]:
    """
    Safely evaluate a mathematical expression.

    Args:
        expression: Mathematical expression string

    Returns:
        Dict with result, expression, and any error message
    """
    try:
        # Pre-process common patterns
        expr = expression.strip()

        # Handle "X% of Y" → Y * X / 100
        percent_match = re.match(r"(\d+(?:\.\d+)?)\s*%\s*of\s+(\d+(?:\.\d+)?)", expr, re.IGNORECASE)
        if percent_match:
            pct = float(percent_match.group(1))
            val = float(percent_match.group(2))
            result = val * pct / 100
            return {
                "expression": expr,
                "result": result,
                "formatted": _format_result(result),
            }

        # Replace common words
        expr = expr.replace("^", "**")

        # Parse and evaluate
        tree = ast.parse(expr, mode="eval")
        result = _eval_node(tree.body)

        return {
            "expression": expression,
            "result": result,
            "formatted": _format_result(result),
        }

    except (ValueError, TypeError, ZeroDivisionError) as e:
        return {
            "expression": expression,
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Calculator error: {e}")
        return {
            "expression": expression,
            "error": f"Invalid expression: {str(e)}",
        }


def _eval_node(node: ast.AST) -> Any:
    """Recursively evaluate an AST node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _OPERATORS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        operand = _eval_node(node.operand)
        return _OPERATORS[op_type](operand)

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in _FUNCTIONS:
                raise ValueError(f"Unknown function: {func_name}")
            func = _FUNCTIONS[func_name]
            args = [_eval_node(arg) for arg in node.args]
            return func(*args)
        raise ValueError("Unsupported function call")

    if isinstance(node, ast.Name):
        name = node.id
        if name in _FUNCTIONS:
            val = _FUNCTIONS[name]
            if isinstance(val, (int, float)):
                return val
        raise ValueError(f"Unknown variable: {name}")

    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


def _format_result(result: Any) -> str:
    """Format a numeric result for display."""
    if isinstance(result, float):
        if result == int(result) and abs(result) < 1e15:
            return str(int(result))
        return f"{result:.10g}"
    return str(result)
