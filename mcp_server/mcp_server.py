"""
MCP Tool Server — Deterministic Tool Implementations.

Exposes three tools via the Model Context Protocol (FastMCP):
  1. text_processor  — String manipulation (uppercase, lowercase, word count, reverse, title case)
  2. calculator      — Safe arithmetic expression evaluation (no eval())
  3. weather_mock    — Synthetic weather data for any location

Run standalone:  python mcp_server.py
The Agent Controller spawns this as a subprocess and communicates via stdio.
"""

import ast
import hashlib
import json
import operator
import random
import string
import uuid as uuid_lib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

mcp = FastMCP(name="AgentCapabilities")


# ---------------------------------------------------------------------------
# Tool 1: Text Processor
# ---------------------------------------------------------------------------
@mcp.tool()
def text_processor(text: str, operation: str) -> str:
    """
    Transforms text based on a specified operation.

    Supported operations:
      - uppercase  : Convert text to UPPER CASE
      - lowercase  : Convert text to lower case
      - wordcount  : Count the number of words
      - reverse    : Reverse the text
      - titlecase  : Convert To Title Case
    """
    ops = {
        "uppercase": lambda t: t.upper(),
        "lowercase": lambda t: t.lower(),
        "wordcount": lambda t: str(len(t.split())),
        "reverse": lambda t: t[::-1],
        "titlecase": lambda t: t.title(),
    }
    fn = ops.get(operation.strip().lower())
    if fn is None:
        return f"Invalid operation '{operation}'. Supported: {', '.join(ops.keys())}"
    return fn(text)


# ---------------------------------------------------------------------------
# Tool 2: Calculator (safe AST-based evaluation)
# ---------------------------------------------------------------------------

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_node(node):
    """Recursively evaluate an AST node using only whitelisted operators."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    # Python < 3.8 compat (ast.Num is deprecated but still present)
    if isinstance(node, ast.Num):  # noqa: E501
        return node.n
    if isinstance(node, ast.BinOp):
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        op = _ALLOWED_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval_node(node.operand)
        op = _ALLOWED_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op(operand)
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


@mcp.tool()
def calculator(expression: str) -> str:
    """
    Evaluates a basic arithmetic expression securely.

    Supports: +, -, *, /, %, ** and parentheses.
    Does NOT use eval() — parses the AST and walks it with whitelisted operators.

    Example: calculator("(3 + 5) * 2") → "16"
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval_node(tree.body)
        # Format nicely: integers stay integers, floats keep precision
        if isinstance(result, float) and result == int(result):
            return str(int(result))
        return str(result)
    except ZeroDivisionError:
        return "Error: Division by zero"
    except Exception as e:
        return f"Error evaluating expression: {e}"


# ---------------------------------------------------------------------------
# Tool 3: Weather Mock (deterministic hash-based)
# ---------------------------------------------------------------------------
@mcp.tool()
def weather_mock(location: str) -> str:
    """
    Returns synthetic but consistent weather data for a given location.

    The output is deterministic: the same location always returns the same
    weather, making it suitable for testing and demonstrations.
    """
    conditions = ["Sunny", "Partly Cloudy", "Cloudy", "Rainy", "Thunderstorms", "Snowy", "Windy", "Foggy"]

    # Use a hash to get deterministic-but-varied results per location
    digest = int(hashlib.md5(location.lower().strip().encode()).hexdigest(), 16)
    temp = (digest % 55) - 10  # Range: -10 to 44 °C
    humidity = (digest >> 8) % 60 + 30  # Range: 30% to 89%
    condition = conditions[digest % len(conditions)]

    return json.dumps(
        {
            "location": location,
            "temperature_celsius": temp,
            "humidity_percent": humidity,
            "condition": condition,
            "forecast": f"{condition} with a high of {temp}°C",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Tool 4: DateTime Tool
# ---------------------------------------------------------------------------
@mcp.tool()
def datetime_tool(operation: str, value: str = "", timezone_name: str = "UTC", days: int = 0) -> str:
    """
    Date/time operations.

    Operations:
      - now           : current date/time in specified timezone
      - add_days      : add/subtract days from a date (value=YYYY-MM-DD, days=N)
      - days_between  : days between two dates (value=YYYY-MM-DD,YYYY-MM-DD)
      - format        : reformat a date string (value=any date string)
    """
    try:
        tz = ZoneInfo(timezone_name)
    except (KeyError, ValueError):
        tz = timezone.utc

    op = operation.strip().lower()

    if op == "now":
        now = datetime.now(tz)
        return json.dumps({
            "datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timezone": timezone_name,
            "day_of_week": now.strftime("%A"),
        })

    elif op == "add_days":
        base_date = value.strip() if value else datetime.now(tz).strftime("%Y-%m-%d")
        try:
            dt = datetime.strptime(base_date, "%Y-%m-%d").replace(tzinfo=tz)
        except ValueError:
            return f"Error: Invalid date format '{base_date}'. Use YYYY-MM-DD."
        result = dt + timedelta(days=days)
        return json.dumps({
            "original_date": base_date,
            "days_added": days,
            "result_date": result.strftime("%Y-%m-%d"),
            "day_of_week": result.strftime("%A"),
        })

    elif op == "days_between":
        parts = [p.strip() for p in value.split(",")]
        if len(parts) != 2:
            return "Error: Provide two dates separated by comma (YYYY-MM-DD,YYYY-MM-DD)"
        try:
            d1 = datetime.strptime(parts[0], "%Y-%m-%d")
            d2 = datetime.strptime(parts[1], "%Y-%m-%d")
        except ValueError:
            return "Error: Invalid date format. Use YYYY-MM-DD."
        diff = (d2 - d1).days
        return json.dumps({
            "date_1": parts[0],
            "date_2": parts[1],
            "days_between": abs(diff),
            "direction": "future" if diff >= 0 else "past",
        })

    elif op == "format":
        try:
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y", "%d-%m-%Y"):
                try:
                    dt = datetime.strptime(value.strip(), fmt)
                    return json.dumps({
                        "iso": dt.isoformat(),
                        "human": dt.strftime("%B %d, %Y"),
                        "short": dt.strftime("%m/%d/%Y"),
                    })
                except ValueError:
                    continue
            return f"Error: Could not parse date '{value}'"
        except Exception as e:
            return f"Error: {e}"

    return f"Invalid operation '{operation}'. Supported: now, add_days, days_between, format"


# ---------------------------------------------------------------------------
# Tool 5: Unit Converter
# ---------------------------------------------------------------------------
@mcp.tool()
def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """
    Convert between common units.

    Categories:
      - Temperature: C, F, K
      - Length: m, km, mi, ft, in, cm
      - Weight: kg, lb, oz, g
      - Volume: l, ml, gal, cup
    """
    f = from_unit.strip().lower()
    t = to_unit.strip().lower()

    # Temperature conversions
    temp_conversions = {
        ("c", "f"): lambda v: v * 9 / 5 + 32,
        ("f", "c"): lambda v: (v - 32) * 5 / 9,
        ("c", "k"): lambda v: v + 273.15,
        ("k", "c"): lambda v: v - 273.15,
        ("f", "k"): lambda v: (v - 32) * 5 / 9 + 273.15,
        ("k", "f"): lambda v: (v - 273.15) * 9 / 5 + 32,
    }

    if (f, t) in temp_conversions:
        result = temp_conversions[(f, t)](value)
        return json.dumps({"value": round(result, 2), "from": from_unit, "to": to_unit})

    # Length: convert to meters as base
    length_to_m = {"m": 1, "km": 1000, "mi": 1609.344, "ft": 0.3048, "in": 0.0254, "cm": 0.01}
    if f in length_to_m and t in length_to_m:
        meters = value * length_to_m[f]
        result = meters / length_to_m[t]
        return json.dumps({"value": round(result, 4), "from": from_unit, "to": to_unit})

    # Weight: convert to grams as base
    weight_to_g = {"g": 1, "kg": 1000, "lb": 453.592, "oz": 28.3495}
    if f in weight_to_g and t in weight_to_g:
        grams = value * weight_to_g[f]
        result = grams / weight_to_g[t]
        return json.dumps({"value": round(result, 4), "from": from_unit, "to": to_unit})

    # Volume: convert to ml as base
    vol_to_ml = {"ml": 1, "l": 1000, "gal": 3785.41, "cup": 236.588}
    if f in vol_to_ml and t in vol_to_ml:
        ml = value * vol_to_ml[f]
        result = ml / vol_to_ml[t]
        return json.dumps({"value": round(result, 4), "from": from_unit, "to": to_unit})

    if f == t:
        return json.dumps({"value": value, "from": from_unit, "to": to_unit})

    return f"Error: Cannot convert from '{from_unit}' to '{to_unit}'. Check supported units."


# ---------------------------------------------------------------------------
# Tool 6: JSON Formatter
# ---------------------------------------------------------------------------
@mcp.tool()
def json_formatter(json_string: str, operation: str = "prettify") -> str:
    """
    JSON manipulation tool.

    Operations:
      - validate     : check if valid JSON, return "valid" or error
      - prettify     : return indented JSON
      - minify       : return compact single-line JSON
      - extract_keys : return top-level keys
      - count_items  : count top-level items
    """
    op = operation.strip().lower()

    if op == "validate":
        try:
            json.loads(json_string)
            return "valid"
        except json.JSONDecodeError as e:
            return f"invalid: {e}"

    try:
        data = json.loads(json_string)
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON — {e}"

    if op == "prettify":
        return json.dumps(data, indent=2, ensure_ascii=False)
    elif op == "minify":
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    elif op == "extract_keys":
        if isinstance(data, dict):
            return json.dumps(list(data.keys()))
        return "Error: JSON is not an object (no keys to extract)"
    elif op == "count_items":
        if isinstance(data, dict):
            return str(len(data))
        elif isinstance(data, list):
            return str(len(data))
        return "1"

    return f"Invalid operation '{operation}'. Supported: validate, prettify, minify, extract_keys, count_items"


# ---------------------------------------------------------------------------
# Tool 7: Hash Generator
# ---------------------------------------------------------------------------
@mcp.tool()
def hash_generator(text: str, algorithm: str = "sha256") -> str:
    """
    Generate cryptographic hash of input text.

    Algorithms: md5, sha1, sha256, sha512
    Returns the hex digest string.
    """
    algo = algorithm.strip().lower()
    algorithms = {
        "md5": hashlib.md5,
        "sha1": hashlib.sha1,
        "sha256": hashlib.sha256,
        "sha512": hashlib.sha512,
    }
    fn = algorithms.get(algo)
    if fn is None:
        return f"Error: Unsupported algorithm '{algorithm}'. Supported: {', '.join(algorithms.keys())}"

    digest = fn(text.encode("utf-8")).hexdigest()
    return json.dumps({"input": text, "algorithm": algo, "hash": digest})


# ---------------------------------------------------------------------------
# Tool 8: Random Generator
# ---------------------------------------------------------------------------
@mcp.tool()
def random_generator(operation: str, min_val: int = 0, max_val: int = 100,
                     length: int = 16, items: str = "", seed: int = -1) -> str:
    """
    Generate random values.

    Operations:
      - number   : random integer between min_val and max_val
      - uuid     : generate a UUID v4
      - password : random string of given length (letters + digits + symbols)
      - choice   : pick random item from comma-separated items string

    Optional: seed for reproducible results in testing (default -1 = truly random)
    """
    rng = random.Random()
    if seed >= 0:
        rng = random.Random(seed)

    op = operation.strip().lower()

    if op == "number":
        result = rng.randint(min_val, max_val)
        return json.dumps({"value": result, "min": min_val, "max": max_val})

    elif op == "uuid":
        return json.dumps({"value": str(uuid_lib.uuid4())})

    elif op == "password":
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pwd = "".join(rng.choice(chars) for _ in range(length))
        return json.dumps({"value": pwd, "length": length})

    elif op == "choice":
        options = [i.strip() for i in items.split(",") if i.strip()]
        if not options:
            return "Error: No items provided. Pass comma-separated values in 'items'."
        picked = rng.choice(options)
        return json.dumps({"value": picked, "from": options})

    return f"Invalid operation '{operation}'. Supported: number, uuid, password, choice"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run()
