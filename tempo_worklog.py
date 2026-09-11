#!/usr/bin/env python3
"""Tempo Timesheets worklog helper for Jira Cloud (Tempo API v4).

Generic template - replace placeholders before use:
  - AUTHOR_ACCOUNT_ID: your Atlassian accountId (find it via your Jira
    profile URL, e.g. https://home.atlassian.com/.../people/<accountId>)
  - ISSUE_ID_MAP: cache of "issueKey" -> numeric Jira issueId (see notes below)

Auth:
  Set TEMPO_TOKEN env var, or store the token in a local auth.json file at
  credential_pool.tempo.api_token (path configurable via AUTH_JSON below).

IMPORTANT: The Tempo v4 "create worklog" endpoint requires the *numeric*
Jira issueId, not the issue key (e.g. "PROJ-123"). Resolve it once via the
Jira REST API and cache it:

  GET https://<your-instance>.atlassian.net/rest/api/3/issue/{key}?fields=summary
  (Basic Auth: your Atlassian email + a Jira API token from
   https://id.atlassian.com/manage-profile/security/api-tokens)

Do NOT reuse an issueId you saw in someone else's worklog description -
the same-looking key can map to a different issue per project/instance
quirks. Always resolve your own issueId via the API.
"""
import os, sys, json, argparse, urllib.request, urllib.parse, urllib.error

BASE = "https://api.tempo.io/4"
AUTH_JSON = "/opt/data/auth.json"  # adjust to your environment

# TODO: replace with your own Atlassian accountId
AUTHOR_ACCOUNT_ID = "REPLACE_WITH_YOUR_ATLASSIAN_ACCOUNT_ID"

# TODO: fill in as you resolve issue keys -> numeric Jira issueId
ISSUE_ID_MAP = {
    # "PROJ-123": "1234567",
}


def get_token():
    """Read Tempo API token from auth.json or environment."""
    if os.environ.get("TEMPO_TOKEN"):
        return os.environ["TEMPO_TOKEN"]
    try:
        with open(AUTH_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("credential_pool", {}).get("tempo", {}).get("api_token")
        if token:
            return token
    except Exception as exc:
        raise RuntimeError(f"Cannot read Tempo token: {exc}") from exc
    raise RuntimeError("TEMPO_TOKEN not found in environment or credential_pool.tempo.api_token")


def request(token, method, path, payload=None, params=None):
    """Make a Tempo API request using only the Python standard library."""
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode("utf-8")
            if not content:
                return {"status": response.status}
            return json.loads(content)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Tempo API HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Tempo API connection error: {exc}") from exc


def create_worklog(token, issue_key, issue_id, date, seconds, description, start_time="09:00:00", billable_seconds=None):
    payload = {
        "issueId": issue_id,
        "startDate": date,
        "startTime": start_time,
        "timeSpentSeconds": seconds,
        "billableSeconds": billable_seconds if billable_seconds is not None else seconds,
        "description": description,
        "authorAccountId": AUTHOR_ACCOUNT_ID,
    }
    return request(token, "POST", "/worklogs", payload=payload)


def list_worklogs(token, from_date, to_date, limit=1000, account_id=None):
    # IMPORTANT: do NOT use the generic GET /worklogs?from=&to= endpoint to check
    # your own hours - it returns worklogs for ALL users in the Tempo instance
    # that day, paginated at `limit` (default 100). A personal worklog created
    # later than others that day can silently fall off the first page and look
    # "missing" even though it exists and is visible in the Tempo UI.
    # GET /worklogs/user/{accountId} is server-side filtered to just you and is
    # the authoritative source - always prefer it when auditing your own hours.
    account_id = account_id or AUTHOR_ACCOUNT_ID
    return request(token, "GET", f"/worklogs/user/{account_id}", params={"from": from_date, "to": to_date, "limit": limit})


def get_worklog(token, worklog_id):
    return request(token, "GET", f"/worklogs/{worklog_id}")


def update_worklog(token, worklog_id, payload):
    return request(token, "PUT", f"/worklogs/{worklog_id}", payload=payload)


def delete_worklog(token, worklog_id):
    return request(token, "DELETE", f"/worklogs/{worklog_id}")


def get_work_attributes(token):
    return request(token, "GET", "/work-attributes")


def main():
    parser = argparse.ArgumentParser(description="Tempo Timesheets CLI")
    sub = parser.add_subparsers(dest="cmd")

    p_create = sub.add_parser("create", help="Create a worklog")
    p_create.add_argument("--issue", required=True, help="Jira issue key, for example PROJ-123")
    p_create.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_create.add_argument("--hours", type=float, required=True, help="Hours spent")
    p_create.add_argument("--desc", required=True, help="Worklog description")
    p_create.add_argument("--start-time", default="09:00:00", help="Start time HH:MM:SS")
    p_create.add_argument("--billable-hours", type=float, default=None)

    p_list = sub.add_parser("list", help="List worklogs (org-wide for the date range)")
    p_list.add_argument("--from", dest="from_date", required=True, help="YYYY-MM-DD")
    p_list.add_argument("--to", required=True, help="YYYY-MM-DD")
    p_list.add_argument("--limit", type=int, default=100)

    p_get = sub.add_parser("get", help="Get a single worklog")
    p_get.add_argument("--id", type=int, required=True)

    p_update = sub.add_parser("update", help="Update a worklog")
    p_update.add_argument("--id", type=int, required=True)
    p_update.add_argument("--json", required=True, help="JSON payload string")

    p_delete = sub.add_parser("delete", help="Delete a worklog")
    p_delete.add_argument("--id", type=int, required=True)

    sub.add_parser("attrs", help="List work attributes")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    token = get_token()

    if args.cmd == "create":
        seconds = int(args.hours * 3600)
        billable = int(args.billable_hours * 3600) if args.billable_hours is not None else None
        issue_id = ISSUE_ID_MAP.get(args.issue, args.issue)
        if issue_id == args.issue:
            print(
                f"WARNING: '{args.issue}' is not in ISSUE_ID_MAP. Tempo v4 requires the "
                f"numeric Jira issueId, not the key. Resolve it first via the Jira API "
                f"(GET /rest/api/3/issue/{args.issue}) and add it to ISSUE_ID_MAP.",
                file=sys.stderr,
            )
        result = create_worklog(token, args.issue, issue_id, args.date, seconds, args.desc, args.start_time, billable)
    elif args.cmd == "list":
        result = list_worklogs(token, args.from_date, args.to, args.limit)
    elif args.cmd == "get":
        result = get_worklog(token, args.id)
    elif args.cmd == "update":
        result = update_worklog(token, args.id, json.loads(args.json))
    elif args.cmd == "delete":
        result = delete_worklog(token, args.id)
    elif args.cmd == "attrs":
        result = get_work_attributes(token)
    else:
        raise RuntimeError(f"Unknown command: {args.cmd}")

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
