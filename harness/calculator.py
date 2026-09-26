"""Deterministic calculator: exact arithmetic with every step shown.

The model proposes, code disposes -- and for plain arithmetic no model is
needed at all. This module:

1. Recognises a calculation in a natural-language request ("add 2 + 2",
   "what is 15% of 2400", "square root of 144", "sum of 4, 5 and 6").
   Recognition is deliberately conservative: after normalisation the text
   may contain ONLY numbers, operators, parentheses and whitelisted math
   names, so a document question like "What is 201-XV-01?" is never
   mistaken for arithmetic.
2. Evaluates it by walking the Python AST -- never eval() -- with hard
   limits on length, node count, exponent size and result magnitude.
3. Records each intermediate operation, so the answer shows its working.

Used by harness/runner.py (answered before intent routing, no model call)
and by the agent's `calculate` tool (harness/agent_tools.py).
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Optional

MAX_EXPRESSION_CHARS = 300
MAX_NODES = 80
MAX_EXPONENT = 1000
MAX_MAGNITUDE = 1e300


class CalculationError(ValueError):
    """The text is not a valid, safe arithmetic expression."""


_BINOPS = {
    ast.Add: ("+", operator.add),
    ast.Sub: ("−", operator.sub),
    ast.Mult: ("×", operator.mul),
    ast.Div: ("÷", operator.truediv),
    ast.FloorDiv: ("//", operator.floordiv),
    ast.Mod: ("mod", operator.mod),
    ast.Pow: ("^", operator.pow),
}

_FUNCTIONS = {
    "sqrt": math.sqrt, "cbrt": lambda x: math.copysign(abs(x) ** (1 / 3), x),
    "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "exp": math.exp, "ln": math.log, "log": math.log10, "log10": math.log10, "log2": math.log2,
    # Trigonometry in DEGREES -- what an engineer typing "sin(30)" means.
    "sin": lambda d: math.sin(math.radians(d)), "cos": lambda d: math.cos(math.radians(d)),
    "tan": lambda d: math.tan(math.radians(d)),
    "asin": lambda x: math.degrees(math.asin(x)), "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "factorial": math.factorial,
}
_CONSTANTS = {"pi": math.pi, "e": math.e}
_ALLOWED_NAMES = set(_FUNCTIONS) | set(_CONSTANTS)


def fmt(value: float) -> str:
    """Readable number: integers without '.0', otherwise 10 significant digits."""
    if isinstance(value, bool):
        raise CalculationError("booleans are not numbers")
    if isinstance(value, float):
        value = float(format(value, ".12g"))  # drop float noise: 2800.0000000000005 -> 2800
    if isinstance(value, int) or (value.is_integer() and abs(value) < 1e15):
        return f"{int(value):,}"
    if 1e-6 <= abs(value) < 1e15:
        return f"{value:,.6f}".rstrip("0").rstrip(".")
    return format(value, ".10g")


# ---------------------------------------------------------------------------
# Natural language -> expression
# ---------------------------------------------------------------------------

_LEAD = re.compile(
    r"^(?:please\s+|pls\s+|can you\s+|could you\s+|kindly\s+)*"
    r"(?:what\s+is|what's|whats|how\s+much\s+is|calculate|compute|evaluate|work\s+out|find|solve|"
    r"add|sum(?:\s+up)?|total|multiply|subtract|divide)?\b\s*(?:the\s+)?(?:value\s+of\s+|result\s+of\s+|sum\s+of\s+|total\s+of\s+|of\s+)?",
    re.IGNORECASE,
)
_WORD_OPS = [
    (r"\bsquare\s+root\s+of\s+", "sqrt "), (r"\bcube\s+root\s+of\s+", "cbrt "),
    (r"\bsqrt\s+of\s+", "sqrt "),
    (r"\bmultiplied\s+by\b", "*"), (r"\btimes\b", "*"), (r"\bdivided\s+by\b", "/"),
    (r"\bover\b", "/"), (r"\bplus\b", "+"), (r"\bminus\b", "-"), (r"\bmod(?:ulo)?\b", "%"),
    (r"\bto\s+the\s+power\s+of\b", "**"), (r"\braised\s+to\b", "**"), (r"\bsquared\b", "**2"), (r"\bcubed\b", "**3"),
    (r"(\d)\s*[x×]\s*(?=[\d(])", r"\1*"), (r"÷", "/"), (r"\^", "**"), (r"−", "-"),
]


_NUM = r"-?\d[\d,]*(?:\.\d+)?"
_IT = r"(?:it|that|this|the\s+(?:result|answer|total|sum))"

# First clause of a step-by-step request: "add 2 with 2", "multiply 6 by 7",
# "subtract 3 from 10", "divide 100 by 4", or anything to_expression accepts.
_FIRST = [
    (re.compile(rf"^(?:add|sum)\s+({_NUM})\s+(?:with|and|to|plus)\s+({_NUM})$"), lambda a, b: f"({a}+{b})"),
    (re.compile(rf"^multiply\s+({_NUM})\s+(?:by|with|and)\s+({_NUM})$"), lambda a, b: f"({a}*{b})"),
    (re.compile(rf"^subtract\s+({_NUM})\s+from\s+({_NUM})$"), lambda a, b: f"({b}-{a})"),
    (re.compile(rf"^divide\s+({_NUM})\s+(?:by|with)\s+({_NUM})$"), lambda a, b: f"({a}/{b})"),
]
# Each later clause operates on the running result: "then divide it by 593".
_NEXT = [
    (re.compile(rf"^(?:add|plus)\s+({_NUM})(?:\s+to\s+{_IT})?$"), "({prev}+{n})"),
    (re.compile(rf"^add\s+{_IT}\s+(?:to|with)\s+({_NUM})$"), "({prev}+{n})"),
    (re.compile(rf"^(?:subtract|minus|take\s+away|less)\s+({_NUM})(?:\s+from\s+{_IT})?$"), "({prev}-{n})"),
    (re.compile(rf"^(?:multiply|times)(?:\s+{_IT})?\s+(?:by\s+)?({_NUM})$"), "({prev}*{n})"),
    (re.compile(rf"^(?:divide|divided)(?:\s+{_IT})?\s+(?:by\s+)?({_NUM})$"), "({prev}/{n})"),
    (re.compile(rf"^(?:raise\s+{_IT}\s+to|to)\s+(?:the\s+)?(?:power\s+(?:of\s+)?)?({_NUM})$"), "({prev}**{n})"),
    (re.compile(rf"^(?:square)(?:\s+{_IT})?$"), "({prev}**2)"),
    (re.compile(rf"^(?:cube)(?:\s+{_IT})?$"), "({prev}**3)"),
    (re.compile(rf"^(?:take\s+)?(?:the\s+)?square\s+root(?:\s+of\s+{_IT})?$"), "sqrt({prev})"),
    (re.compile(rf"^(?:take\s+)?({_NUM})\s*(?:%|percent)\s+of\s+{_IT}$"), "({n}/100*{prev})"),
]


def _stepwise(s: str) -> Optional[str]:
    """'add 2 with 2 and then divide it by 593' -> '((2+2)/593)'."""
    clauses = [c.strip(" ,") for c in re.split(r"\s*,?\s*\b(?:and\s+then|then|after\s+that|and\s+after\s+that)\b\s*", s) if c.strip(" ,")]
    if not clauses:
        return None
    expr = None
    for pattern, build in _FIRST:
        m = pattern.match(clauses[0])
        if m:
            expr = build(*(g.replace(",", "") for g in m.groups()))
            break
    if expr is None:
        if len(clauses) == 1:
            return None
        expr = to_expression(clauses[0], _allow_stepwise=False)
        if expr is None:
            return None
        expr = f"({expr})"
    for clause in clauses[1:]:
        for pattern, template in _NEXT:
            m = pattern.match(clause)
            if m:
                n = m.group(1).replace(",", "") if m.groups() else ""
                expr = template.format(prev=expr, n=n)
                break
        else:
            return None  # a clause we don't understand: don't guess
    return expr


def to_expression(text: str, _allow_stepwise: bool = True) -> Optional[str]:
    """Return a normalised arithmetic expression, or None if `text` isn't one."""
    raw = (text or "").strip()
    if not raw or len(raw) > MAX_EXPRESSION_CHARS:
        return None
    s = raw.lower().rstrip(" ?.!=")
    if _allow_stepwise:
        polite = re.sub(r"^(?:please\s+|pls\s+|can you\s+|could you\s+|kindly\s+)+", "", s)
        stepwise = _stepwise(polite)
        if stepwise is not None:
            return stepwise
    verb = re.match(r"^(?:please\s+|can you\s+|could you\s+)*(add|sum|total)\b", s)
    s = _LEAD.sub("", s, count=1).strip()
    s = re.sub(r"\s+(?:using|with)\s+(?:a\s+)?calculator$", "", s)
    for pattern, repl in _WORD_OPS:
        s = re.sub(pattern, repl, s)
    # Percentages: "15% of 2400" -> (15/100)*2400 ; "15 percent" -> (15/100)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+", r"(\1/100)*", s)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)(?![\d(])", r"(\1/100)", s)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)  # 2,400 -> 2400
    if verb:
        # "add 2 and 3", "sum of 4, 5 and 6"
        s = re.sub(r"\s*(?:,|\band\b)\s*", "+", s)
    # "sqrt 16" -> "sqrt(16)" for a bare number argument
    s = re.sub(r"\b(" + "|".join(_FUNCTIONS) + r")\s+(\d+(?:\.\d+)?)", r"\1(\2)", s)
    s = s.strip()
    if not s or not re.fullmatch(r"[\d\s.+\-*/%()a-z_,]*", s):
        return None
    names = set(re.findall(r"[a-z_]+", s))
    if not names <= _ALLOWED_NAMES:
        return None
    has_op = re.search(r"\d\s*(\*\*|[+\-*/%])\s*[\d(a-z]|[+\-*/%]\s*\(|\)\s*[+\-*/%]", s) or names & set(_FUNCTIONS)
    if not has_op:
        return None  # a bare number ("2025") is not a calculation
    return s


# ---------------------------------------------------------------------------
# Safe evaluation with steps
# ---------------------------------------------------------------------------

def evaluate(expression: str) -> tuple[float, list[str]]:
    """Evaluate a normalised expression. Returns (result, steps)."""
    if len(expression) > MAX_EXPRESSION_CHARS:
        raise CalculationError("expression too long")
    try:
        tree = ast.parse(expression.replace("^", "**"), mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"not a valid expression: {exc.msg}") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise CalculationError("expression too complex")
    steps: list[str] = []

    def check(v):
        if isinstance(v, complex) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) or abs(v) > MAX_MAGNITUDE:
            raise CalculationError("result is out of range")
        return v

    def walk(node) -> float:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.Name) and node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = walk(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            left, right = walk(node.left), walk(node.right)
            symbol, fn = _BINOPS[type(node.op)]
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
                raise CalculationError("exponent too large")
            try:
                value = check(fn(left, right))
            except ZeroDivisionError:
                raise CalculationError("division by zero") from None
            except OverflowError:
                raise CalculationError("result is out of range") from None
            steps.append(f"{fmt(left)} {symbol} {fmt(right)} = {fmt(value)}")
            return value
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCTIONS
                and len(node.args) in (1, 2) and not node.keywords):
            args = [walk(a) for a in node.args]
            if node.func.id == "factorial" and (args[0] > 170 or args[0] != int(args[0]) or args[0] < 0):
                raise CalculationError("factorial needs a whole number from 0 to 170")
            try:
                value = check(_FUNCTIONS[node.func.id](*[int(a) if node.func.id == "factorial" else a for a in args]))
            except (ValueError, OverflowError) as exc:
                raise CalculationError(f"{node.func.id}: {exc}") from None
            unit = "°" if node.func.id in ("sin", "cos", "tan") else ""
            steps.append(f"{node.func.id}({', '.join(fmt(a) + unit for a in args)}) = {fmt(value)}")
            return value
        raise CalculationError("only numbers, + − × ÷ ^ %, parentheses and math functions are allowed")

    result = walk(tree)
    return result, steps


def calculate(text: str) -> Optional[dict]:
    """Recognise and evaluate a calculation. None if `text` isn't arithmetic.

    Raises CalculationError when it IS arithmetic but can't be evaluated
    (e.g. division by zero), so callers can report that honestly.
    """
    expression = to_expression(text)
    if expression is None:
        return None
    result, steps = evaluate(expression)
    pretty = expression.replace("**", "^").replace("*", "×").replace("/", "÷")
    # Same number formatting as the steps: 439434034 -> 439,434,034
    pretty = re.sub(r"\d+(?:\.\d+)?", lambda m: fmt(float(m.group()) if "." in m.group() else int(m.group())), pretty)
    return {"expression": expression, "display": pretty, "result": result, "result_text": fmt(result), "steps": steps}


def render_markdown(calc: dict) -> str:
    lines = [f"## {calc['display']} = **{calc['result_text']}**", "", "### Calculation steps"]
    if calc["steps"]:
        lines += [f"{i}. {step}" for i, step in enumerate(calc["steps"], start=1)]
    else:
        lines.append("1. No operations needed.")
    if any(fn in calc["expression"] for fn in ("sin", "cos", "tan")):
        lines += ["", "_Angles are in degrees._"]
    return "\n".join(lines)
