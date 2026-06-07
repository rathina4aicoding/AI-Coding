"""
mcp_servers/github_server.py
----------------------------
A small MCP server that mocks GitHub.

Transport: stdio. Logs go to stderr.

Tools:
  - list_repos()                       -- enumerate repositories
  - search_code(query, repo)           -- code search across repos
  - list_pull_requests(repo, state)    -- list PRs
  - get_pull_request(pr_id)            -- single PR details
  - list_issues(repo, state, label)    -- list issues
  - create_issue(repo, title, body)    -- file a new issue
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | github_server | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("github_server")

mcp = FastMCP("github")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------
_REPOS = [
    {"name": "techmate-bot",
     "description": "Source code for the TechMate IT assistant.",
     "visibility": "private", "default_branch": "main",
     "language": "Python", "stars": 12},
    {"name": "marketing-site",
     "description": "Public marketing site (Next.js).",
     "visibility": "public", "default_branch": "main",
     "language": "TypeScript", "stars": 47},
    {"name": "analytics-prod",
     "description": "Production data warehouse (dbt + Airflow).",
     "visibility": "internal", "default_branch": "main",
     "language": "Python", "stars": 8},
]

_CODE_SNIPPETS = [
    {"repo": "techmate-bot", "path": "agent.py", "language": "Python",
     "snippet": "async def run_agent_turn(user_message: str):\n    "
                "messages = [{'role': 'user', 'content': user_message}]\n    "
                "response = client.messages.create(...)\n    "
                "for block in response.content:\n        "
                "if block.type == 'tool_use':\n            ..."},
    {"repo": "techmate-bot", "path": "mcp_client.py", "language": "Python",
     "snippet": "async def call_tool(self, name: str, args: dict) -> dict:\n    "
                "session = self._route_for(name)\n    "
                "result = await session.call_tool(name, arguments=args)\n    "
                "return _coerce_mcp_result(result)"},
    {"repo": "techmate-bot", "path": "tools.py", "language": "Python",
     "snippet": "TOOL_DEFINITIONS = [\n    "
                "{'name': 'list_tickets', 'description': '...', "
                "'input_schema': {...}},\n    ...\n]"},
    {"repo": "marketing-site", "path": "pages/pricing.tsx",
     "language": "TypeScript",
     "snippet": "export default function PricingPage() {\n    "
                "return <Layout><PricingTable plans={PLANS} /></Layout>;\n}"},
    {"repo": "analytics-prod", "path": "models/revenue_daily.sql",
     "language": "SQL",
     "snippet": "SELECT date_trunc('day', order_ts) AS day, "
                "SUM(amount) AS revenue\nFROM orders WHERE status='paid'\n"
                "GROUP BY 1 ORDER BY 1;"},
]

_PULL_REQUESTS = [
    {"id": "PR-101", "repo": "techmate-bot",
     "title": "Add MCP client wiring for Jira",
     "author": "alice.chen@example.com",
     "state": "open", "reviewers": ["bob.martinez@example.com"],
     "created_at": (_now() - timedelta(hours=18)).isoformat(),
     "updated_at": (_now() - timedelta(hours=2)).isoformat(),
     "checks": "passing", "additions": 412, "deletions": 28,
     "labels": ["enhancement", "mcp"]},
    {"id": "PR-102", "repo": "techmate-bot",
     "title": "Stream agent events to Gradio activity panel",
     "author": "david.kim@example.com",
     "state": "open",
     "reviewers": ["alice.chen@example.com", "grace.li@example.com"],
     "created_at": (_now() - timedelta(days=1)).isoformat(),
     "updated_at": (_now() - timedelta(hours=5)).isoformat(),
     "checks": "failing", "additions": 187, "deletions": 12,
     "labels": ["ui", "needs-tests"]},
    {"id": "PR-220", "repo": "analytics-prod",
     "title": "Fix nightly revenue rollup off-by-one",
     "author": "emma.foster@example.com",
     "state": "merged", "reviewers": ["david.kim@example.com"],
     "created_at": (_now() - timedelta(days=3)).isoformat(),
     "updated_at": (_now() - timedelta(days=2)).isoformat(),
     "checks": "passing", "additions": 9, "deletions": 6,
     "labels": ["bug"]},
    {"id": "PR-415", "repo": "marketing-site",
     "title": "Update pricing page copy",
     "author": "frank.osei@example.com",
     "state": "closed", "reviewers": ["grace.li@example.com"],
     "created_at": (_now() - timedelta(days=7)).isoformat(),
     "updated_at": (_now() - timedelta(days=6)).isoformat(),
     "checks": "passing", "additions": 24, "deletions": 18,
     "labels": ["docs"]},
]

_ISSUES = [
    {"id": "ISSUE-201", "repo": "techmate-bot",
     "title": "Tool call timeout should be configurable",
     "state": "open", "author": "alice.chen@example.com",
     "labels": ["enhancement"], "comments": 3,
     "created_at": (_now() - timedelta(days=2)).isoformat()},
    {"id": "ISSUE-202", "repo": "techmate-bot",
     "title": "Activity log truncates long JSON results",
     "state": "open", "author": "grace.li@example.com",
     "labels": ["bug", "ui"], "comments": 1,
     "created_at": (_now() - timedelta(days=1)).isoformat()},
    {"id": "ISSUE-203", "repo": "techmate-bot",
     "title": "Add MCP server health check",
     "state": "closed", "author": "david.kim@example.com",
     "labels": ["mcp"], "comments": 5,
     "created_at": (_now() - timedelta(days=8)).isoformat()},
    {"id": "ISSUE-310", "repo": "marketing-site",
     "title": "404 on /enterprise page",
     "state": "open", "author": "external-user@example.com",
     "labels": ["bug", "good-first-issue"], "comments": 2,
     "created_at": (_now() - timedelta(days=5)).isoformat()},
]

# Issues created via the create_issue tool during this session
_CREATED_ISSUES: list[dict] = []


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
def list_repos() -> dict:
    """List every repository in the organization."""
    log.info("list_repos()")
    return {"count": len(_REPOS), "repos": _REPOS}


@mcp.tool()
def search_code(query: str, repo: Optional[str] = None) -> dict:
    """
    Search for code across repositories.

    query -- search string (case-insensitive substring match against snippets).
    repo  -- optional exact repo name to limit search.
    """
    if not query or not query.strip():
        return {"error": "query is required"}
    q = query.strip().lower()
    log.info("search_code(%r, repo=%r)", q, repo)

    matches = []
    for snip in _CODE_SNIPPETS:
        if repo and snip["repo"] != repo:
            continue
        if q in snip["snippet"].lower() or q in snip["path"].lower():
            matches.append(snip)
    return {"query": query, "count": len(matches), "matches": matches}


@mcp.tool()
def list_pull_requests(
    repo: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """
    List pull requests across repos, with optional filters.

    repo  -- limit to one repo (exact name).
    state -- one of: open, closed, merged.
    limit -- max results (default 10).
    """
    if state and state not in ("open", "closed", "merged"):
        return {"error": "state must be open, closed, or merged"}
    log.info("list_pull_requests(repo=%r, state=%r)", repo, state)

    prs = list(_PULL_REQUESTS)
    if repo:
        prs = [p for p in prs if p["repo"] == repo]
    if state:
        prs = [p for p in prs if p["state"] == state]
    prs.sort(key=lambda p: p["updated_at"], reverse=True)
    prs = prs[:max(1, min(50, int(limit)))]
    return {"count": len(prs), "pull_requests": prs}


@mcp.tool()
def get_pull_request(pr_id: str) -> dict:
    """Fetch a single pull request by ID (e.g. 'PR-101')."""
    log.info("get_pull_request(%r)", pr_id)
    target = pr_id.strip().upper()
    for p in _PULL_REQUESTS:
        if p["id"].upper() == target:
            return {"found": True, "pull_request": p}
    return {"found": False, "pr_id": pr_id,
            "known_pr_ids": [p["id"] for p in _PULL_REQUESTS]}


@mcp.tool()
def list_issues(
    repo: Optional[str] = None,
    state: Optional[str] = None,
    label: Optional[str] = None,
    limit: int = 10,
) -> dict:
    """
    List issues across repos.

    repo  -- limit to one repo.
    state -- 'open' or 'closed'.
    label -- only issues carrying this label.
    limit -- max results.
    """
    if state and state not in ("open", "closed"):
        return {"error": "state must be open or closed"}
    log.info("list_issues(repo=%r, state=%r, label=%r)", repo, state, label)

    rows = list(_ISSUES) + _CREATED_ISSUES
    if repo:
        rows = [r for r in rows if r["repo"] == repo]
    if state:
        rows = [r for r in rows if r["state"] == state]
    if label:
        rows = [r for r in rows if label in r.get("labels", [])]
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    rows = rows[:max(1, min(50, int(limit)))]
    return {"count": len(rows), "issues": rows}


@mcp.tool()
def create_issue(repo: str, title: str, body: str = "",
                 labels: Optional[list[str]] = None) -> dict:
    """
    File a new issue.

    repo   -- exact repo name.
    title  -- short headline.
    body   -- detailed description (markdown supported).
    labels -- optional list of label strings.
    """
    log.info("create_issue(repo=%r, title=%r)", repo, title)
    known = {r["name"] for r in _REPOS}
    if repo not in known:
        return {"error": f"Unknown repo {repo!r}. Known: {sorted(known)}"}
    if not title.strip():
        return {"error": "title is required"}

    new_id = f"ISSUE-{900 + len(_CREATED_ISSUES) + 1}"
    issue = {
        "id": new_id, "repo": repo, "title": title.strip(),
        "body": body, "state": "open",
        "author": "mcp-client@example.com",
        "labels": list(labels or []),
        "comments": 0,
        "created_at": _now().isoformat(),
    }
    _CREATED_ISSUES.append(issue)
    return {"created": True, "issue": issue}


if __name__ == "__main__":
    log.info("Starting GitHub MCP server (stdio, MOCK mode)")
    mcp.run(transport="stdio")
