"""
JARVIS — Phase 4: Email & Calendar integration (Gmail + Google Calendar)

Uses Google's official API via OAuth — your credentials never touch
any third party. Requires a one-time setup:

  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "Gmail API" and "Google Calendar API"
  3. Create OAuth credentials (Desktop app) → download as credentials.json
  4. Place credentials.json in this folder
  5. First run will open a browser to authorize — token is cached after that

Add this file's commands into jarvis.py's CommandHandler by importing
EmailCalendarSkill and calling .handle(text) before falling through to AI.
See the INTEGRATION snippet at the bottom of this file.
"""

import os
import base64
import datetime
from pathlib import Path
from email.mime.text import MIMEText

BASE_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "_google_token.json"
CREDS_FILE = BASE_DIR / "credentials.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


class EmailCalendarSkill:
    """
    Handles voice commands for Gmail and Google Calendar.
    Lazily authenticates on first real use so Jarvis still starts up fine
    even if the user hasn't set up Google credentials yet.
    """

    def __init__(self):
        self.service_gmail = None
        self.service_cal   = None
        self._creds        = None
        self.available     = CREDS_FILE.exists()

    # ── Auth ─────────────────────────────────────────────────────────────
    def _authenticate(self):
        if self._creds:
            return self._creds
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow

            creds = None
            if TOKEN_FILE.exists():
                creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not CREDS_FILE.exists():
                        return None
                    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
                    creds = flow.run_local_server(port=0)
                TOKEN_FILE.write_text(creds.to_json())

            self._creds = creds
            return creds
        except ImportError:
            return None
        except Exception as e:
            print(f"[EmailCalendar] Auth error: {e}")
            return None

    def _gmail(self):
        if self.service_gmail:
            return self.service_gmail
        creds = self._authenticate()
        if not creds:
            return None
        from googleapiclient.discovery import build
        self.service_gmail = build("gmail", "v1", credentials=creds)
        return self.service_gmail

    def _calendar(self):
        if self.service_cal:
            return self.service_cal
        creds = self._authenticate()
        if not creds:
            return None
        from googleapiclient.discovery import build
        self.service_cal = build("calendar", "v3", credentials=creds)
        return self.service_cal

    # ── Router ───────────────────────────────────────────────────────────
    def handle(self, text: str) -> str | None:
        t = text.lower().strip()

        if not self.available:
            triggers = ["check my email", "read my email", "unread email",
                       "my calendar", "my schedule", "today's meetings",
                       "send an email", "send email"]
            if any(k in t for k in triggers):
                return ("Google integration isn't set up yet. Add credentials.json "
                        "to the Jarvis folder — see email_calendar.py for setup steps.")
            return None

        # Email
        if any(k in t for k in ["check my email", "read my email", "unread email", "new email"]):
            return self._check_email()

        if t.startswith("send an email") or t.startswith("send email"):
            return ("Email sending needs recipient, subject, and body — "
                    "use send_email(to, subject, body) directly, or extend this "
                    "trigger to parse those fields from speech.")

        # Calendar
        if any(k in t for k in ["my calendar", "my schedule", "today's meetings",
                                "what's on my calendar", "upcoming events"]):
            return self._check_calendar()

        if t.startswith("schedule a meeting") or t.startswith("add event") or t.startswith("create event"):
            return ("To schedule an event, tell me the title, date, and time — "
                    "e.g. 'schedule meeting Team Sync tomorrow at 3pm'. "
                    "Extend create_event() to parse natural language dates with dateparser.")

        return None

    # ── Email actions ────────────────────────────────────────────────────
    def _check_email(self) -> str:
        gmail = self._gmail()
        if not gmail:
            return "Couldn't connect to Gmail. Check your credentials.json setup."
        try:
            results = gmail.users().messages().list(
                userId="me", labelIds=["INBOX", "UNREAD"], maxResults=5
            ).execute()
            messages = results.get("messages", [])
            if not messages:
                return "No unread emails. Inbox is clear."

            summaries = []
            for m in messages[:5]:
                msg = gmail.users().messages().get(
                    userId="me", id=m["id"], format="metadata",
                    metadataHeaders=["From", "Subject"]
                ).execute()
                headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
                sender = headers.get("From", "Unknown").split("<")[0].strip()
                subject = headers.get("Subject", "No subject")
                summaries.append(f"{sender}: {subject}")

            count = len(messages)
            preview = "; ".join(summaries[:3])
            return f"You have {count} unread emails. Top ones: {preview}."
        except Exception as e:
            return f"Couldn't fetch emails: {e}"

    def send_email(self, to: str, subject: str, body: str) -> str:
        gmail = self._gmail()
        if not gmail:
            return "Couldn't connect to Gmail."
        try:
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
            return f"Email sent to {to}."
        except Exception as e:
            return f"Couldn't send email: {e}"

    # ── Calendar actions ─────────────────────────────────────────────────
    def _check_calendar(self) -> str:
        cal = self._calendar()
        if not cal:
            return "Couldn't connect to Google Calendar. Check your credentials.json setup."
        try:
            now = datetime.datetime.utcnow().isoformat() + "Z"
            end = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + "Z"
            events_result = cal.events().list(
                calendarId="primary", timeMin=now, timeMax=end,
                maxResults=10, singleEvents=True, orderBy="startTime"
            ).execute()
            events = events_result.get("items", [])
            if not events:
                return "Nothing on your calendar for the next 24 hours. You're free."

            summaries = []
            for e in events[:5]:
                start = e["start"].get("dateTime", e["start"].get("date"))
                try:
                    dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                    time_str = dt.strftime("%I:%M %p")
                except Exception:
                    time_str = start
                summaries.append(f"{e.get('summary', 'Untitled')} at {time_str}")

            return f"You have {len(events)} events coming up: " + "; ".join(summaries) + "."
        except Exception as e:
            return f"Couldn't fetch calendar: {e}"

    def create_event(self, title: str, start_dt: datetime.datetime,
                     duration_minutes: int = 30) -> str:
        cal = self._calendar()
        if not cal:
            return "Couldn't connect to Google Calendar."
        try:
            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)
            event = {
                "summary": title,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
                "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "UTC"},
            }
            cal.events().insert(calendarId="primary", body=event).execute()
            return f"Created event '{title}' at {start_dt.strftime('%I:%M %p on %B %d')}."
        except Exception as e:
            return f"Couldn't create event: {e}"


# ─────────────────────────────────────────────────────────────────────────
# INTEGRATION SNIPPET — add to jarvis.py's CommandHandler.handle(), right
# after the plugin matching block:
#
#   from email_calendar import EmailCalendarSkill
#   # in __init__: self.email_cal = EmailCalendarSkill()
#   # in handle():
#   result = self.email_cal.handle(text)
#   if result:
#       return result
# ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Quick manual test
    skill = EmailCalendarSkill()
    print("Available:", skill.available)
    if skill.available:
        print(skill.handle("check my email"))
        print(skill.handle("my schedule"))
