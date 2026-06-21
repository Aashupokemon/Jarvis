"""
Example Jarvis plugin: Calculator
Drop any .py file into the plugins/ folder to extend Jarvis automatically.
Each plugin must define TRIGGERS (list of keywords) and handle(text, ctx) -> str|None.
Return None to let Jarvis fall through to Claude AI or other handlers.
"""
import re

TRIGGERS = ["calculate", "what is", "how much is", "compute"]

def handle(text: str, ctx: dict) -> str:
    expr = (text.lower()
            .replace("calculate", "")
            .replace("what is", "")
            .replace("how much is", "")
            .replace("compute", "")
            .replace("x", "*")
            .replace("times", "*")
            .replace("divided by", "/")
            .replace("plus", "+")
            .replace("minus", "-"))
    expr = re.sub(r"[^0-9+\-*/().% ]", "", expr).strip()
    if not expr or not re.search(r"\d", expr):
        return None  # not a math query, let Claude handle it
    try:
        result = eval(expr, {"__builtins__": {}})
        return f"The result is {result}."
    except Exception:
        return None
