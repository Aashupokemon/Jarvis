"""
Example Jarvis plugin: Reminders
Demonstrates a stateful plugin using a local JSON file for persistence.
"""
import json
import re
import datetime
from pathlib import Path

TRIGGERS = ["remind me", "set a reminder", "list reminders", "my reminders"]

REMINDERS_FILE = Path(__file__).parent / "_reminders.json"

def _load():
    if REMINDERS_FILE.exists():
        return json.loads(REMINDERS_FILE.read_text())
    return []

def _save(items):
    REMINDERS_FILE.write_text(json.dumps(items, indent=2))

def handle(text: str, ctx: dict) -> str:
    t = text.lower().strip()

    if "list reminders" in t or "my reminders" in t:
        items = _load()
        if not items:
            return "You have no reminders set."
        lines = [f"{i+1}. {r['text']}" for i, r in enumerate(items)]
        return "Your reminders: " + "; ".join(lines)

    if "remind me" in t or "set a reminder" in t:
        # Extract "remind me to X" or "remind me about X"
        m = re.search(r"remind me (?:to |about )?(.+)", t)
        reminder_text = m.group(1).strip() if m else t
        items = _load()
        items.append({
            "text": reminder_text,
            "created": datetime.datetime.now().isoformat()
        })
        _save(items)
        return f"Got it. I'll remember: {reminder_text}."

    return None
