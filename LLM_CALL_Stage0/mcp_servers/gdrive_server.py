"""
mcp_servers/gdrive_server.py
----------------------------
A small MCP server that mocks a Google Drive workspace.

Transport: stdio. Logs go to stderr.

Why mocked? Real Google Drive needs OAuth, a GCP project, scoped tokens,
etc. The teaching goal here is to show how an LLM uses MCP - so we keep
the protocol real and the backend mocked. To swap in the real Drive API
later, you only have to replace the bodies of the functions below; the
tool surface stays the same.

Tools:
  - list_files(folder, query, limit)  -- list files in a folder or matching a query
  - search_files(query, limit)        -- full-text search across all files
  - read_file(file_id)                -- return the contents of a file
  - list_folders()                    -- enumerate available folders
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | gdrive_server | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("gdrive_server")

mcp = FastMCP("gdrive")


@dataclass
class _DriveFile:
    id: str
    name: str
    folder: str
    mime_type: str
    owner: str
    modified_at: str
    content: str


def _ts(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# Realistic-looking mock drive contents.
_FILES: list[_DriveFile] = [
    _DriveFile(
        id="1aB-q3a-onboarding",
        name="Q3 Onboarding Plan.docx",
        folder="People Ops",
        mime_type="application/vnd.google-apps.document",
        owner="hr-lead@example.com",
        modified_at=_ts(2),
        content=(
            "Q3 Onboarding Plan\n\n"
            "Week 1: Laptop provisioning, Okta SSO setup, mandatory security "
            "training, intro to internal tools (Slack, Jira, GitHub, Confluence).\n"
            "Week 2: Team-specific shadowing, first 1:1 with manager, sign up "
            "for engineering bootcamp.\n"
            "Week 3: First ticket assignment, contribute small PR to "
            "techmate-bot repository.\n"
            "Owners: HR lead + hiring manager. Target time-to-productivity: 30 days."
        ),
    ),
    _DriveFile(
        id="2cD-vpn-runbook",
        name="VPN Setup Runbook.md",
        folder="IT Helpdesk",
        mime_type="text/markdown",
        owner="it-lead@example.com",
        modified_at=_ts(7),
        content=(
            "# VPN Setup Runbook\n\n"
            "1. Download the company VPN client from the Okta dashboard.\n"
            "2. Install. On macOS approve the network extension under System "
            "Settings > Privacy & Security.\n"
            "3. Connect to the 'us-east' or 'eu-west' gateway.\n"
            "4. If disconnects happen, switch DNS to 1.1.1.1 inside the "
            "client settings.\n"
            "Common issue: certificate trust prompts on first connect - "
            "click 'Always Trust'."
        ),
    ),
    _DriveFile(
        id="3eF-phishing-policy",
        name="Phishing Response Policy.pdf",
        folder="Security",
        mime_type="application/pdf",
        owner="security@example.com",
        modified_at=_ts(14),
        content=(
            "Phishing Response Policy\n\n"
            "If you receive a suspicious email:\n"
            "1. Do NOT click links or download attachments.\n"
            "2. Use the 'Report Phish' button in Outlook (top toolbar).\n"
            "3. Forward the original as an attachment to security@example.com.\n"
            "4. Notify #security in Slack.\n"
            "Reference: NIST SP 800-61, MITRE ATT&CK Initial Access."
        ),
    ),
    _DriveFile(
        id="4gH-mcp-rfc",
        name="RFC-014 MCP Adoption.md",
        folder="Engineering",
        mime_type="text/markdown",
        owner="staff-eng@example.com",
        modified_at=_ts(1),
        content=(
            "# RFC-014: MCP Adoption\n\n"
            "Status: Draft\n\n"
            "Proposal: replace our ad-hoc tool integrations with MCP servers "
            "so any LLM agent we run can talk to the same backends.\n\n"
            "Servers in scope for Q4: Jira, GitHub, Slack, Internal KB.\n"
            "Out of scope: anything requiring write access to production.\n\n"
            "Risks: stdio transport requires careful subprocess management; "
            "auth must live in each server.\n"
            "Reviewers: @alice.chen, @david.kim, @grace.li"
        ),
    ),
    _DriveFile(
        id="5iJ-budget",
        name="2026 Engineering Budget.xlsx",
        folder="Finance",
        mime_type="application/vnd.google-apps.spreadsheet",
        owner="finance@example.com",
        modified_at=_ts(30),
        content=(
            "2026 Engineering Budget Summary\n\n"
            "Total: $4.2M (up 12% YoY).\n"
            "Headcount: +6 SWEs, +2 SREs.\n"
            "Tooling: $180k (GitHub Enterprise, CI/CD, Datadog, Anthropic API).\n"
            "Hardware refresh: $220k.\n"
            "Quarterly review with CFO scheduled for end of Q1."
        ),
    ),
    _DriveFile(
        id="6kL-1on1-template",
        name="1-on-1 Meeting Template.docx",
        folder="People Ops",
        mime_type="application/vnd.google-apps.document",
        owner="hr-lead@example.com",
        modified_at=_ts(45),
        content=(
            "1-on-1 Meeting Template\n\n"
            "Wins since last 1:1:\n"
            "Blockers / asks:\n"
            "Career growth & learning goals:\n"
            "Feedback for me as your manager:\n"
            "Action items (owner + due):\n\n"
            "Cadence: weekly, 30 min. Notes live in shared doc per report."
        ),
    ),
    _DriveFile(
        id="7mN-incident-template",
        name="Incident Postmortem Template.md",
        folder="Engineering",
        mime_type="text/markdown",
        owner="staff-eng@example.com",
        modified_at=_ts(60),
        content=(
            "# Incident Postmortem Template\n\n"
            "Summary: 1-2 sentence description of what happened.\n"
            "Impact: Who was affected, for how long, by how much.\n"
            "Timeline (UTC): Bullet-point chronology.\n"
            "Root cause: Technical explanation.\n"
            "What went well / poorly.\n"
            "Action items with owners and due dates.\n"
            "Blameless - we focus on systems, not people."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
def _to_summary(f: _DriveFile) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "folder": f.folder,
        "mime_type": f.mime_type,
        "owner": f.owner,
        "modified_at": f.modified_at,
    }


@mcp.tool()
def list_folders() -> dict:
    """List every folder in the workspace and how many files it contains."""
    log.info("list_folders()")
    folders: dict[str, int] = {}
    for f in _FILES:
        folders[f.folder] = folders.get(f.folder, 0) + 1
    return {
        "count": len(folders),
        "folders": [{"name": k, "file_count": v}
                    for k, v in sorted(folders.items())],
    }


@mcp.tool()
def list_files(folder: Optional[str] = None, limit: int = 20) -> dict:
    """
    List files in the workspace, optionally filtered by folder name.

    folder -- if provided, only return files in that folder (case-insensitive
              exact match).
    limit  -- max files to return (default 20).
    """
    log.info("list_files(folder=%r, limit=%d)", folder, limit)
    rows = list(_FILES)
    if folder:
        f = folder.strip().lower()
        rows = [r for r in rows if r.folder.lower() == f]
    rows.sort(key=lambda r: r.modified_at, reverse=True)
    rows = rows[:max(1, min(50, int(limit)))]
    return {"count": len(rows), "files": [_to_summary(r) for r in rows]}


@mcp.tool()
def search_files(query: str, limit: int = 10) -> dict:
    """
    Free-text search across file names and contents.

    query -- search string (case-insensitive substring match).
    limit -- max results (default 10).
    """
    if not query or not query.strip():
        return {"error": "query is required"}
    q = query.strip().lower()
    log.info("search_files(%r)", q)

    matches: list[_DriveFile] = []
    for f in _FILES:
        if q in f.name.lower() or q in f.content.lower() or q in f.folder.lower():
            matches.append(f)
    matches.sort(key=lambda r: r.modified_at, reverse=True)
    matches = matches[:max(1, min(50, int(limit)))]
    return {
        "query": query,
        "count": len(matches),
        "files": [_to_summary(f) for f in matches],
    }


@mcp.tool()
def read_file(file_id: str) -> dict:
    """
    Return the full contents of a file by its ID.

    file_id -- the 'id' field from list_files / search_files output.
    """
    log.info("read_file(%r)", file_id)
    for f in _FILES:
        if f.id == file_id:
            return {
                "found": True,
                "file": {**_to_summary(f), "content": f.content},
            }
    return {
        "found": False,
        "file_id": file_id,
        "known_ids": [f.id for f in _FILES],
    }


if __name__ == "__main__":
    log.info("Starting Google Drive MCP server (stdio, MOCK mode)")
    mcp.run(transport="stdio")
