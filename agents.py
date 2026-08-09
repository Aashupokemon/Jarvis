"""
JARVIS — Multi-Agent System
Trigger phrase: "Agents assemble"

When activated, the Commander:
  1. Listens to your task description
  2. Parses it into sub-tasks for each specialist agent
  3. Runs all agents IN PARALLEL (concurrent threads)
  4. Aggregates results
  5. Sends everything to Claude for a unified spoken briefing

Agents:
  ResearchAgent  — web search, Wikipedia, news, facts
  FileAgent      — read, write, organise, search local files
  SystemAgent    — open/close apps, volume, brightness, screenshots
  ImageAgent     — generate AI images, describe screen
  EmailAgent     — Gmail, Google Calendar
  WebAgent       — open URLs, fill searches, navigate browser
  CodeAgent      — write, run, explain code; create Python scripts

Usage:
  Say "Agents assemble" → Jarvis asks what you need
  Say your task         → agents work in parallel
  Jarvis speaks a full briefing when all are done

Can also be imported and called directly:
  from agents import AgentCommander
  commander = AgentCommander(api_key, handler)
  commander.assemble("research top AI news and summarise it in a file")
"""

import os
import sys
import json
import time
import queue
import threading
import subprocess
import webbrowser
import datetime
import platform
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError


BASE_DIR = Path(__file__).parent
AGENT_LOG = BASE_DIR / "agent_log.json"

# ─── Colours for terminal output (optional cosmetic) ─────────────────────────
CYAN  = "\033[96m"
GOLD  = "\033[93m"
GREEN = "\033[92m"
RED   = "\033[91m"
DIM   = "\033[2m"
RESET = "\033[0m"

def _log(agent: str, msg: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"{DIM}[{ts}]{RESET} {CYAN}[{agent}]{RESET} {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# Base Agent
# ─────────────────────────────────────────────────────────────────────────────
class BaseAgent:
    """
    Every agent follows the same contract:
      result = agent.run(task: str) -> dict
    The dict always has:
      { "agent": name, "status": "ok"|"skip"|"error",
        "result": str, "data": any }
    Returning status="skip" means "this task isn't for me".
    """
    name = "Base"

    def __init__(self, api_key: str = "", handler=None):
        self.api_key = api_key
        self.handler = handler   # reference to CommandHandler for system ops
        self.os_name = platform.system()

    def run(self, task: str) -> dict:
        raise NotImplementedError

    def _ok(self, result: str, data=None) -> dict:
        return {"agent": self.name, "status": "ok", "result": result, "data": data}

    def _skip(self, reason: str = "") -> dict:
        return {"agent": self.name, "status": "skip", "result": reason, "data": None}

    def _err(self, error: str) -> dict:
        return {"agent": self.name, "status": "error", "result": str(error), "data": None}

    def _claude(self, prompt: str, system: str = "", max_tokens: int = 600) -> str:
        """Ask Claude AI and return the text response."""
        if not self.api_key:
            return "(AI unavailable — no API key)"
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": max_tokens,
                    "system": system or "You are a helpful AI assistant.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=20,
            )
            return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            return f"(Claude error: {e})"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Research Agent
# ─────────────────────────────────────────────────────────────────────────────
class ResearchAgent(BaseAgent):
    """
    Handles: search, research, find out, look up, news, what is, who is,
             Wikipedia, latest, current events
    """
    name = "Research"

    TRIGGERS = [
        "search", "research", "find out", "look up", "news", "what is",
        "who is", "wikipedia", "latest", "current", "information about",
        "tell me about", "facts about", "history of", "explain",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"Researching: {task[:60]}")

        # Try web search via wttr.in for weather, else Claude
        if "weather" in t:
            city = "auto"
            words = t.split()
            for i, w in enumerate(words):
                if w in ("in", "for", "at") and i + 1 < len(words):
                    city = words[i + 1]
                    break
            try:
                r = requests.get(f"https://wttr.in/{city}?format=3", timeout=6)
                return self._ok(f"Weather: {r.text.strip()}")
            except Exception:
                pass

        # Wikipedia summary
        if "wikipedia" in t or "who is" in t or "what is" in t:
            subject = task
            for stop in ["wikipedia", "who is", "what is", "tell me about",
                         "information about", "facts about"]:
                subject = subject.lower().replace(stop, "").strip()
            try:
                url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(subject)}"
                r = requests.get(url, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    extract = data.get("extract", "")[:500]
                    return self._ok(f"Wikipedia: {extract}", data)
            except Exception:
                pass

        # Claude as the research brain
        result = self._claude(
            f"Research this and give a concise 3-4 sentence summary: {task}",
            system=(
                "You are a research assistant. Give factual, concise answers. "
                "If you are unsure, say so. Keep it under 4 sentences."
            ),
            max_tokens=300,
        )
        return self._ok(result)


# ─────────────────────────────────────────────────────────────────────────────
# 2. File Agent
# ─────────────────────────────────────────────────────────────────────────────
class FileAgent(BaseAgent):
    """
    Handles: create file, write to file, save, read file, open file,
             list files, search files, organise, move, rename, delete
    """
    name = "File"

    TRIGGERS = [
        "create file", "write file", "save file", "read file", "open file",
        "list files", "search files", "find file", "move file", "rename",
        "delete file", "folder", "directory", "note", "document",
        "write to", "save to", "save as",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"File task: {task[:60]}")

        # Create / write file
        if any(k in t for k in ["create file", "write file", "save", "note", "document"]):
            return self._create_file(task)

        # Read file
        if any(k in t for k in ["read file", "open file", "show file"]):
            return self._read_file(task)

        # List files
        if any(k in t for k in ["list files", "show files", "what files"]):
            return self._list_files(task)

        # Search files
        if any(k in t for k in ["search files", "find file", "search for file"]):
            return self._search_files(task)

        return self._skip("File task not recognised")

    def _create_file(self, task: str) -> dict:
        import re
        # Extract filename if mentioned
        m = re.search(r'(?:named?|called?|as)\s+([\w\-. ]+\.?\w*)', task, re.I)
        if m:
            fname = m.group(1).strip()
        else:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"jarvis_note_{ts}.txt"

        # Generate content with Claude if task implies it
        content = ""
        if any(k in task.lower() for k in ["write", "draft", "create", "compose"]):
            content = self._claude(
                f"Write the content for this file task: {task}\n"
                "Just write the actual file content, no meta-commentary.",
                max_tokens=500,
            )

        path = Path.home() / "Documents" / fname
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content or f"Created by Jarvis at {datetime.datetime.now()}\n")

        # Open it
        try:
            if self.os_name == "Windows":
                os.startfile(str(path))
            elif self.os_name == "Darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass

        return self._ok(f"Created file: {path.name}", str(path))

    def _read_file(self, task: str) -> dict:
        import re
        m = re.search(r'(?:file|read|open)\s+([\w\-./\\]+)', task, re.I)
        if not m:
            return self._err("Please specify the filename.")
        fname = m.group(1).strip()
        candidates = [
            Path(fname),
            Path.home() / fname,
            Path.home() / "Documents" / fname,
            Path.home() / "Desktop" / fname,
        ]
        for p in candidates:
            if p.exists():
                text = p.read_text(errors="replace")[:1000]
                return self._ok(f"Contents of {p.name}: {text[:300]}...", text)
        return self._err(f"File not found: {fname}")

    def _list_files(self, task: str) -> dict:
        import re
        m = re.search(r'(?:in|inside|from)\s+([\w\-./\\~ ]+)', task, re.I)
        folder = m.group(1).strip() if m else "Documents"
        p = Path(folder).expanduser()
        if not p.exists():
            p = Path.home() / folder
        try:
            files = sorted(p.iterdir())[:20]
            names = [f.name for f in files]
            return self._ok(f"Files in {p.name}: {', '.join(names)}", names)
        except Exception as e:
            return self._err(str(e))

    def _search_files(self, task: str) -> dict:
        import re
        m = re.search(r'(?:for|named?|called?)\s+([\w\-. ]+)', task, re.I)
        query = m.group(1).strip() if m else task
        results = []
        search_root = Path.home()
        for p in search_root.rglob(f"*{query}*"):
            if p.is_file():
                results.append(str(p))
                if len(results) >= 10:
                    break
        if results:
            return self._ok(f"Found {len(results)} file(s) matching '{query}'", results)
        return self._ok(f"No files found matching '{query}'")


# ─────────────────────────────────────────────────────────────────────────────
# 3. System Agent
# ─────────────────────────────────────────────────────────────────────────────
class SystemAgent(BaseAgent):
    """
    Handles: open app, close app, volume, brightness, screenshot,
             shutdown, restart, lock, sleep, battery, CPU, RAM
    """
    name = "System"

    TRIGGERS = [
        "open", "close", "volume", "brightness", "screenshot", "shutdown",
        "restart", "lock", "sleep", "battery", "cpu", "ram", "memory",
        "start", "launch", "kill", "terminate", "mute", "unmute",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"System task: {task[:60]}")

        if self.handler:
            result = self.handler.handle(task)
            if result and result != "SHUTDOWN":
                return self._ok(result)

        # Fallback implementations if handler not available
        if t.startswith("open "):
            app = task[5:].strip()
            return self._open_app(app)

        if "screenshot" in t:
            return self._screenshot()

        if "battery" in t:
            return self._battery()

        if any(k in t for k in ["cpu", "ram", "memory"]):
            return self._stats()

        return self._skip()

    def _open_app(self, app: str) -> dict:
        try:
            if self.os_name == "Windows":
                subprocess.Popen(["start", app], shell=True)
            elif self.os_name == "Darwin":
                subprocess.Popen(["open", "-a", app])
            else:
                subprocess.Popen([app.lower()])
            return self._ok(f"Opened {app}.")
        except Exception as e:
            return self._err(f"Couldn't open {app}: {e}")

    def _screenshot(self) -> dict:
        try:
            import pyautogui
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path.home() / "Pictures" / f"jarvis_{ts}.png"
            path.parent.mkdir(exist_ok=True)
            pyautogui.screenshot(str(path))
            return self._ok(f"Screenshot saved to {path.name}", str(path))
        except Exception as e:
            return self._err(str(e))

    def _battery(self) -> dict:
        try:
            import psutil
            b = psutil.sensors_battery()
            if b:
                st = "charging" if b.power_plugged else "on battery"
                return self._ok(f"Battery: {b.percent:.0f}%, {st}.")
            return self._ok("No battery detected.")
        except Exception:
            return self._err("psutil not available")

    def _stats(self) -> dict:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            ram = psutil.virtual_memory()
            return self._ok(
                f"CPU: {cpu}%, RAM: {ram.percent}% "
                f"({ram.used//1024//1024} MB / {ram.total//1024//1024} MB)."
            )
        except Exception:
            return self._err("psutil not available")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Image Agent
# ─────────────────────────────────────────────────────────────────────────────
class ImageAgent(BaseAgent):
    """
    Handles: generate image, draw, paint, imagine, create picture,
             what's on screen, describe screen, read screen
    """
    name = "Image"

    TRIGGERS = [
        "generate image", "generate a", "create image", "draw", "paint",
        "imagine", "create picture", "make image", "render",
        "what's on screen", "what is on screen", "describe screen",
        "read screen", "look at screen", "screen vision",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"Image task: {task[:60]}")

        # Screen vision
        if any(k in t for k in ["screen", "what's on", "describe screen", "read screen"]):
            return self._screen_vision(task)

        # Image generation
        try:
            from image_gen import ImageGenerator
            gen = ImageGenerator(self.api_key)
            import re
            prompt = re.sub(
                r"(?:generate|create|draw|paint|imagine|make|render)\s+(?:an?\s+)?(?:image\s+of\s+)?",
                "", task, flags=re.I
            ).strip()
            result = gen.generate(prompt)
            return self._ok(result)
        except Exception as e:
            return self._err(f"Image generation failed: {e}")

    def _screen_vision(self, task: str) -> dict:
        try:
            from screen_vision import ScreenVision
            sv = ScreenVision(self.api_key)
            desc = sv.ask_about_screen(task)
            return self._ok(desc)
        except Exception as e:
            return self._err(f"Screen vision failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Email Agent
# ─────────────────────────────────────────────────────────────────────────────
class EmailAgent(BaseAgent):
    """
    Handles: email, calendar, schedule, meetings, inbox,
             gmail, google calendar
    """
    name = "Email"

    TRIGGERS = [
        "email", "mail", "inbox", "calendar", "schedule", "meeting",
        "event", "appointment", "gmail", "google calendar", "unread",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"Email task: {task[:60]}")

        try:
            from email_calendar import EmailCalendarSkill
            skill = EmailCalendarSkill()
            result = skill.handle(task)
            if result:
                return self._ok(result)
            return self._skip("Email agent couldn't handle this task")
        except Exception as e:
            return self._err(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 6. Web Agent
# ─────────────────────────────────────────────────────────────────────────────
class WebAgent(BaseAgent):
    """
    Handles: open website, go to, browse, search google, youtube,
             visit URL, navigate to
    """
    name = "Web"

    TRIGGERS = [
        "open website", "go to", "browse", "visit", "navigate to",
        "search google", "google", "youtube", "open url", "http",
        "www.", ".com", ".org", ".net", "open github", "open reddit",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"Web task: {task[:60]}")

        # YouTube
        if "youtube" in t:
            query = t.replace("youtube", "").replace("search", "").strip()
            url = f"https://www.youtube.com/results?search_query={requests.utils.quote(query)}"
            webbrowser.open(url)
            return self._ok(f"Opened YouTube search for: {query}")

        # Google search
        if any(k in t for k in ["search", "google"]):
            query = t
            for stop in ["search", "google", "search for", "google for"]:
                query = query.replace(stop, "").strip()
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
            webbrowser.open(url)
            return self._ok(f"Searched Google for: {query}")

        # Direct URL
        import re
        url_match = re.search(r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.(com|org|net|io|co)[^\s]*)', task)
        if url_match:
            url = url_match.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            return self._ok(f"Opened {url}")

        # go to / visit / navigate to
        if any(k in t for k in ["go to", "visit", "navigate to", "open website"]):
            site = t
            for stop in ["go to", "visit", "navigate to", "open website", "open"]:
                site = site.replace(stop, "").strip()
            if site and not site.startswith("http"):
                site = "https://" + site
            webbrowser.open(site)
            return self._ok(f"Opened {site}")

        return self._skip()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Code Agent
# ─────────────────────────────────────────────────────────────────────────────
class CodeAgent(BaseAgent):
    """
    Handles: write code, create script, fix code, explain code,
             run python, execute, debug, program
    """
    name = "Code"

    TRIGGERS = [
        "write code", "create script", "fix code", "explain code",
        "run python", "execute", "debug", "program", "script",
        "function", "class", "code to", "python", "javascript",
        "write a function", "write a script", "write a program",
    ]

    def run(self, task: str) -> dict:
        t = task.lower()
        if not any(kw in t for kw in self.TRIGGERS):
            return self._skip()

        _log(self.name, f"Code task: {task[:60]}")

        # Write and save code
        if any(k in t for k in ["write", "create", "generate", "make"]):
            return self._write_code(task)

        # Run existing Python snippet
        if any(k in t for k in ["run", "execute"]):
            return self._run_code(task)

        # Explain code
        if "explain" in t:
            result = self._claude(
                f"Explain this code task clearly and concisely: {task}",
                system="You are a coding expert. Give clear, short explanations.",
                max_tokens=400,
            )
            return self._ok(result)

        # Default: ask Claude
        result = self._claude(
            f"Complete this coding task and provide the code with a brief explanation: {task}",
            system=(
                "You are an expert programmer. Write clean, working code. "
                "Give a one-sentence explanation after the code block. "
                "Keep the total response under 30 lines."
            ),
            max_tokens=600,
        )
        return self._ok(result)

    def _write_code(self, task: str) -> dict:
        code = self._claude(
            f"Write the code for this task: {task}\n"
            "Return ONLY the code, no explanation, no markdown fences.",
            system="You are an expert programmer. Write clean, working, commented code.",
            max_tokens=800,
        )
        # Save to file
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # Detect language
        lang = "py"
        for kw, ext in [("javascript", "js"), ("typescript", "ts"), ("html", "html"),
                        ("css", "css"), ("bash", "sh"), ("java ", "java")]:
            if kw in task.lower():
                lang = ext
                break
        path = Path.home() / "Documents" / f"jarvis_code_{ts}.{lang}"
        path.write_text(code)
        return self._ok(
            f"Code written to {path.name}. Preview:\n{code[:200]}",
            {"path": str(path), "code": code}
        )

    def _run_code(self, task: str) -> dict:
        import re
        # Extract code from the task if quoted
        m = re.search(r'`([^`]+)`', task)
        if m:
            code = m.group(1)
        else:
            # Ask Claude to write it first
            code = self._claude(
                f"Write a minimal Python snippet for: {task}\nReturn ONLY the code.",
                max_tokens=200,
            )
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip() or result.stderr.strip() or "(no output)"
            return self._ok(f"Code ran. Output: {output[:200]}")
        except subprocess.TimeoutExpired:
            return self._err("Code timed out after 10 seconds")
        except Exception as e:
            return self._err(f"Run failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Task Orchestrator — decides which agents handle which sub-tasks
# ─────────────────────────────────────────────────────────────────────────────
class TaskOrchestrator:
    """
    Uses Claude to intelligently split a complex task into sub-tasks,
    assigns each to the right agent, then runs them all in parallel.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    def parse(self, task: str, agents: list) -> list:
        """
        Ask Claude to break the task into per-agent sub-tasks.
        Returns list of (agent_name, sub_task) tuples.
        """
        agent_names = [a.name for a in agents]

        prompt = (
            f"You are a task dispatcher for a multi-agent AI system.\n"
            f"Available agents: {', '.join(agent_names)}\n\n"
            f"Agent capabilities:\n"
            f"- Research: web search, facts, news, Wikipedia, weather\n"
            f"- File: create/read/write/search local files and documents\n"
            f"- System: open/close apps, volume, brightness, screenshots, battery\n"
            f"- Image: generate AI images, describe screen contents\n"
            f"- Email: check Gmail inbox, Google Calendar events\n"
            f"- Web: open websites, Google search, YouTube, navigate URLs\n"
            f"- Code: write, run, debug, explain code and scripts\n\n"
            f"User task: {task}\n\n"
            f"Respond ONLY with a JSON array of objects. Each object must have:\n"
            f'  {{"agent": "AgentName", "task": "specific sub-task description"}}\n'
            f"Only include agents that have something to do. "
            f"Split compound tasks. If the task is simple, assign just one agent.\n"
            f"Example: [{{'agent':'Research','task':'search for Python tutorials'}}, "
            f"{{'agent':'File','task':'save results to tutorial_notes.txt'}}]"
        )

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 400,
                    "system": "You are a task dispatcher. Respond ONLY with valid JSON, no markdown.",
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=15,
            )
            text = resp.json()["content"][0]["text"].strip()
            # Strip markdown fences if Claude adds them
            text = text.replace("```json", "").replace("```", "").strip()
            assignments = json.loads(text)
            return [(a["agent"], a["task"]) for a in assignments]
        except Exception as e:
            _log("Orchestrator", f"Parse failed ({e}), using fallback routing")
            # Fallback: assign to all agents, let them self-filter
            return [(a.name, task) for a in agents]


# ─────────────────────────────────────────────────────────────────────────────
# Result Aggregator + Claude Summariser
# ─────────────────────────────────────────────────────────────────────────────
class ResultAggregator:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def merge(self, results: list, original_task: str) -> str:
        """
        Takes list of agent result dicts, merges them, asks Claude to
        produce a single natural-language spoken briefing.
        """
        # Filter out skips and errors with no useful content
        useful = [r for r in results if r["status"] == "ok"]
        errors = [r for r in results if r["status"] == "error"]

        if not useful:
            parts = [r["result"] for r in errors if r["result"]]
            return "All agents encountered issues. " + " ".join(parts) if parts else "Agents completed with no results."

        # Build summary input for Claude
        summary_input = f"Original task: {original_task}\n\nAgent results:\n"
        for r in useful:
            summary_input += f"\n{r['agent']} Agent: {r['result']}\n"
        if errors:
            summary_input += f"\nAgents that had issues: {', '.join(r['agent'] for r in errors)}\n"

        summary_input += (
            "\nGive a concise spoken briefing (3-6 sentences max) covering all completed tasks. "
            "Sound like a confident assistant reporting to a busy person. "
            "No bullet points. No markdown. Natural speech only."
        )

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-6",
                    "max_tokens": 300,
                    "system": (
                        "You are Jarvis, briefing your user after completing multiple tasks. "
                        "Be concise, confident, and conversational. Spoken word only — no lists."
                    ),
                    "messages": [{"role": "user", "content": summary_input}],
                },
                timeout=15,
            )
            return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            # Fallback: concat results
            parts = [f"{r['agent']}: {r['result'][:100]}" for r in useful]
            return "All agents done. " + ". ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Commander — main entry point
# ─────────────────────────────────────────────────────────────────────────────
class AgentCommander:
    """
    The top-level controller.
    Call assemble(task) to dispatch all agents and get a spoken briefing.
    """
    TRIGGER_PHRASES = [
        "agents assemble", "agent assemble", "assemble agents",
        "all agents", "deploy agents", "launch agents",
        "activate agents", "send in the agents",
    ]

    def __init__(self, api_key: str, handler=None, speak_fn=None, ui_fn=None, agent_event_fn=None):
        self.api_key  = api_key
        self.handler  = handler    # CommandHandler reference
        self.speak    = speak_fn   # speak(text) callback
        self.ui       = ui_fn      # ui(speaker, text) callback for HUD
        self.agent_event = agent_event_fn  # agent_event(name, "start"|"done"|"error") callback

        # Initialise all agents
        kw = {"api_key": api_key, "handler": handler}
        self.agents = [
            ResearchAgent(**kw),
            FileAgent(**kw),
            SystemAgent(**kw),
            ImageAgent(**kw),
            EmailAgent(**kw),
            WebAgent(**kw),
            CodeAgent(**kw),
        ]
        self.orchestrator = TaskOrchestrator(api_key)
        self.aggregator   = ResultAggregator(api_key)

    def is_trigger(self, text: str) -> bool:
        t = text.lower().strip()
        return any(phrase in t for phrase in self.TRIGGER_PHRASES)

    def assemble(self, task: str) -> str:
        """
        Full pipeline:
          parse task → assign agents → run in parallel → aggregate → brief
        Returns the final spoken briefing string.
        """
        _log("Commander", f"Task received: {task}")
        self._agent_event("__mission__", "start")
        self._say(f"Agents assembling. Parsing your task now.")
        self._ui("JARVIS", f"Agents assembling — task: {task}")

        # 1. Orchestrate
        assignments = self.orchestrator.parse(task, self.agents)
        assigned_names = [name for name, _ in assignments]
        _log("Commander", f"Assigned to: {', '.join(assigned_names)}")
        self._say(f"Dispatching {len(assignments)} agents: {', '.join(assigned_names)}.")
        self._ui("sys", f"Agents dispatched: {', '.join(assigned_names)}")

        # 2. Build agent map
        agent_map = {a.name: a for a in self.agents}

        # 3. Run all assigned agents in parallel
        results = []
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=len(assignments)) as pool:
            futures = {}
            for agent_name, sub_task in assignments:
                agent = agent_map.get(agent_name)
                if agent:
                    future = pool.submit(agent.run, sub_task)
                    futures[future] = agent_name
                    self._agent_event(agent_name, "start")
                else:
                    _log("Commander", f"Unknown agent: {agent_name}")

            for future in as_completed(futures, timeout=30):
                agent_name = futures[future]
                try:
                    result = future.result(timeout=25)
                    results.append(result)
                    status_icon = "✅" if result["status"] == "ok" else "⚠️"
                    _log(agent_name, f"{status_icon} {result['status']}: {result['result'][:80]}")
                    self._ui("sys", f"{agent_name}: {result['result'][:60]}")
                    self._agent_event(agent_name, "done" if result["status"] == "ok" else "error")
                except TimeoutError:
                    results.append({"agent": agent_name, "status": "error",
                                    "result": "timed out", "data": None})
                    _log(agent_name, "❌ Timed out")
                    self._agent_event(agent_name, "error")
                except Exception as e:
                    results.append({"agent": agent_name, "status": "error",
                                    "result": str(e), "data": None})
                    _log(agent_name, f"❌ Error: {e}")
                    self._agent_event(agent_name, "error")

        elapsed = time.time() - start_time
        _log("Commander", f"All agents done in {elapsed:.1f}s")

        # 4. Aggregate + summarise
        self._ui("sys", f"Aggregating results from {len(results)} agents...")
        briefing = self.aggregator.merge(results, task)

        # 5. Log to file
        self._save_log(task, assignments, results, briefing)
        self._agent_event("__mission__", "end")

        return briefing

    def _say(self, text: str):
        if self.speak:
            self.speak(text)
        else:
            print(f"🤖 Jarvis: {text}")

    def _ui(self, speaker: str, text: str):
        if self.ui:
            self.ui(speaker, text)

    def _agent_event(self, agent_name: str, status: str):
        if self.agent_event:
            try:
                self.agent_event(agent_name, status)
            except Exception:
                pass

    def _save_log(self, task, assignments, results, briefing):
        try:
            log = {
                "timestamp": datetime.datetime.now().isoformat(),
                "task": task,
                "assignments": [{"agent": a, "task": t} for a, t in assignments],
                "results": [{k: v for k, v in r.items() if k != "data"} for r in results],
                "briefing": briefing,
            }
            existing = []
            if AGENT_LOG.exists():
                existing = json.loads(AGENT_LOG.read_text())
            existing.append(log)
            AGENT_LOG.write_text(json.dumps(existing[-50:], indent=2))  # keep last 50
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Quick standalone test
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("Set ANTHROPIC_API_KEY to test.")
        sys.exit(1)

    commander = AgentCommander(api_key)

    print("\n" + "="*50)
    print("JARVIS AGENTS — Standalone Test")
    print("="*50)

    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
           "Search for latest AI news and save a summary to a file called ai_news.txt"

    print(f"\nTask: {task}\n")
    briefing = commander.assemble(task)
    print(f"\n{'='*50}")
    print("BRIEFING:")
    print(briefing)
    print("="*50)
