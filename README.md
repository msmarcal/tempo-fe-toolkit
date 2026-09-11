# Tempo Timesheets AI Assistant (Field Engineer toolkit)

Automate daily/weekly Tempo Timesheets worklog entries for Jira Cloud, cross-referencing your Google Calendar, with an AI agent (Hermes Agent) proposing entries for your review — it never posts a worklog without your explicit approval.

## What this does

1. **`tempo_worklog.py`** — CLI to create/list/get/update/delete Tempo worklogs via the Tempo Cloud REST API v4.
2. **`tempo_weekly_report.py`** — read-only report: for the current week (Mon-Fri), shows hours already logged vs an 8h/day target, and lists Calendar events that could explain any gap.
3. **`cron_prompt.md`** — the prompt template used to schedule a weekly AI job (e.g. every Friday) that runs the report and proposes a table of suggested worklogs for you to review — it never auto-creates anything.
4. **`auth.example.json`** — example credential file layout (no real secrets).

## Why two separate tokens

Tempo and Jira are separate authentication systems, even on the same Atlassian instance:

- **Tempo API token**: generate in Tempo → Settings → API Integration. Used as a Bearer token against `api.tempo.io`.
- **Jira API token**: generate at <https://id.atlassian.com/manage-profile/security/api-tokens>. Used as Basic Auth (`email:token`) against `https://<your-instance>.atlassian.net/rest/api/3`.

You need the Jira token to resolve a Jira issue key (e.g. `PROJ-123`) to its **numeric issueId**, which the Tempo v4 `POST /worklogs` endpoint actually requires (not the key).

```bash
curl -u "your.email@company.com:JIRA_API_TOKEN" \
  "https://<your-instance>.atlassian.net/rest/api/3/issue/PROJ-123?fields=summary"
```

Cache the resulting `id` value in `ISSUE_ID_MAP` inside `tempo_worklog.py`. **Never** infer an issueId from someone else's worklog data — resolve your own via the API.

## Setup

1. Copy `auth.example.json` to a local `auth.json` (**do not commit this file**) and fill in:
   - `credential_pool.tempo.api_token`
   - `credential_pool.jira.email` and `credential_pool.jira.api_token`
2. In `tempo_worklog.py` and `tempo_weekly_report.py`, replace:
   - `AUTH_JSON` / `AUTH_PATH` with the path to your `auth.json`
   - `AUTHOR_ACCOUNT_ID` / `MY_ACCOUNT_ID` with your Atlassian accountId (find it in your Jira profile URL, format `xxxxx:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
   - `ISSUE_ID_MAP` with your resolved issue keys → numeric IDs
3. Swap `get_calendar_events()` in `tempo_weekly_report.py` for your own Calendar integration if you don't use Google Workspace (Outlook/Graph, etc. — any source that returns `{"summary", "start", "end"}` per event works).

## Usage

```bash
# List work attributes (categories, accounts, etc. required by your org)
python3 tempo_worklog.py attrs

# List worklogs for a date range
python3 tempo_worklog.py list --from 2026-09-01 --to 2026-09-05

# Create a worklog
python3 tempo_worklog.py create --issue PROJ-123 --date 2026-09-02 \
  --hours 4 --desc "Investigated customer issue" --start-time 09:00:00

# Weekly gap report (read-only)
python3 tempo_weekly_report.py
```

## Scheduling with an AI agent (optional)

If you use an AI agent platform with cron/scheduling support (this was built with [Hermes Agent](https://hermes-agent.nousresearch.com)), see `cron_prompt.md` for a ready-to-adapt weekly prompt. Point it at your own script paths, your confirmed work items, and your team's scope rules.

**Golden rule baked into the prompt: the agent must never invent a Jira issue key or auto-submit a worklog. It only proposes; you always confirm.**

## Guardrails we learned the hard way

- Never assume you're associated with a project just because it shows up in team-wide worklog listings or a calendar meeting title — confirm explicitly before logging.
- If you (a human) interact with the Tempo web UI (e.g. "Log Activities") around the same time the script writes via the API, entries can merge/duplicate. Always re-fetch and display the resulting daily total before trusting it.
- Browser `.har` network exports can be huge (tens of millions of tokens) — if you ever need to extract a request from one for an AI agent, grep/extract only the relevant snippet from disk rather than loading the whole file.
- Keep confirmation as a hard gate before any create/update/delete — timesheets feed billing and management reporting.

## License

MIT — reuse and adapt freely across teams.
