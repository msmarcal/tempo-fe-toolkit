#!/usr/bin/env python3
"""
Weekly Tempo timesheet reconciliation helper (generic template).

Fetches Google Calendar events + existing Tempo worklogs for the current
week (Mon-Fri) and prints a gap report (hours missing per day vs an 8h/day
target), plus the calendar events that could explain each gap.

Does NOT create/modify any worklog. Output only, for human/agent review.

Setup:
  - Tempo API token: env var TEMPO_TOKEN, or credential_pool.tempo.api_token
    in a local auth.json (path in AUTH_PATH below).
  - Your Atlassian accountId (find via your Jira profile URL).
  - A way to list Calendar events for a given day. This template shells out
    to a helper script (GOOGLE_PY / GOOGLE_API below); swap in whatever
    Calendar integration you have (Google Workspace API, Outlook/Graph, etc.)
    as long as get_calendar_events() returns a list of dicts with
    "summary", "start", "end".
"""
import json
import subprocess
import urllib.request
from datetime import datetime, timedelta

AUTH_PATH = "/opt/data/auth.json"                 # adjust to your environment
GOOGLE_PY = "/opt/data/.venv_google/bin/python"    # adjust or replace entirely
GOOGLE_API = "/opt/data/skills/productivity/google-workspace/scripts/google_api.py"

# TODO: replace with your own Atlassian accountId
MY_ACCOUNT_ID = "REPLACE_WITH_YOUR_ATLASSIAN_ACCOUNT_ID"
DAILY_TARGET_H = 8.0


def load_tempo_token():
    with open(AUTH_PATH) as f:
        return json.load(f)["credential_pool"]["tempo"]["api_token"]


def get_worklogs(token, date):
    req = urllib.request.Request(
        f"https://api.tempo.io/4/worklogs/user/{MY_ACCOUNT_ID}?from={date}&to={date}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return data.get("results", [])


def get_calendar_events(date):
    """Return [{"summary":..., "start":..., "end":...}, ...] for the given day.
    Swap this implementation for your own Calendar integration if you don't
    use the Google Workspace helper referenced above."""
    start = f"{date}T00:00:00-03:00"  # adjust timezone offset as needed
    end = f"{date}T23:59:59-03:00"
    try:
        out = subprocess.run(
            [GOOGLE_PY, GOOGLE_API, "calendar", "list", "--start", start, "--end", end],
            capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads(out.stdout)
    except Exception as e:
        return [{"summary": f"[ERROR fetching calendar: {e}]", "start": date, "end": date}]


def monday_of_current_week():
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday


def main():
    token = load_tempo_token()
    monday = monday_of_current_week()
    days = [monday + timedelta(days=i) for i in range(5)]  # Mon-Fri

    print("=" * 70)
    print(f"TEMPO WEEKLY RECONCILIATION - Week of {monday.strftime('%Y-%m-%d')}")
    print("=" * 70)

    week_total = 0.0
    for day in days:
        date_str = day.strftime("%Y-%m-%d")
        weekday = day.strftime("%A")
        worklogs = get_worklogs(token, date_str)
        logged_h = sum(w["timeSpentSeconds"] for w in worklogs) / 3600
        week_total += logged_h
        gap_h = DAILY_TARGET_H - logged_h

        print(f"\n--- {weekday} {date_str} ---")
        print(f"Logged: {logged_h}h / {DAILY_TARGET_H}h  (gap: {gap_h}h)")

        if worklogs:
            print("Existing worklogs:")
            for w in worklogs:
                h = w["timeSpentSeconds"] / 3600
                desc = w.get("description", "")[:60]
                print(f"  - {h}h  issue_id={w['issue']['id']}  \"{desc}\"")
        else:
            print("Existing worklogs: (none)")

        if gap_h > 0:
            events = get_calendar_events(date_str)
            meeting_events = [
                e for e in events
                if e.get("summary") not in ("Home",) and "T" in e.get("start", "")
            ]
            if meeting_events:
                print("Calendar events (candidates to cover the gap):")
                for e in meeting_events:
                    print(f"  - {e.get('summary')}  {e.get('start')} -> {e.get('end')}")
            else:
                print("Calendar events: (none found, or all-day only)")

    print("\n" + "=" * 70)
    print(f"WEEK TOTAL: {week_total}h / {DAILY_TARGET_H * 5}h")
    print("=" * 70)
    print("\nNOTE: This report is informational only. No worklogs were created.")
    print("Cross-reference with prior week's confirmed Jira work items before proposing.")


if __name__ == "__main__":
    main()
