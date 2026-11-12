"""MCP server: ask Claude Desktop / Cursor / any MCP client about your marketing.

  "Which post made the most money this month?"
  "Run the daily loop and summarise it."
  "What's waiting on me?"

Run: python -m marketing_team.mcp_server   (stdio transport)
Claude Desktop config (claude_desktop_config.json):
  {"mcpServers": {"marketing": {"command": "python",
     "args": ["-m", "marketing_team.mcp_server"], "cwd": "/path/to/Multi-agent-ai"}}}
"""
from __future__ import annotations

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import db, orchestrator

mcp = _Server("ai-marketing-team")


@mcp.tool()
def marketing_status() -> dict:
    """Today's numbers: posts written, videos posted, replies, calls booked, items waiting on the owner."""
    return db.status_today()


@mcp.tool()
def post_attribution(days: int = 30) -> list[dict]:
    """Published posts with attributed leads, calls, sales and revenue, best first."""
    return db.attribution(days)


@mcp.tool()
def waiting_on_me() -> dict:
    """Open escalations and pending approvals that need a human."""
    return {"escalations": db.query("SELECT id, trigger, detail FROM escalations WHERE status='open'"),
            "approvals": db.query("SELECT id, kind, summary FROM approvals WHERE status='pending'")}


@mcp.tool()
def run_daily_loop(days: int = 30) -> dict:
    """Run the full analytics loop (analyse → learn → plan → brief) and return the brief."""
    out = orchestrator.run_daily(days)
    return {"brief": out["brief"], "insights": out["insights"], "new_ideas": out["loop"]}


@mcp.tool()
def query_marketing_db(sql: str) -> list[dict]:
    """Read-only SQL over tables posts, leads, sales, emails, escalations, events (SELECT only)."""
    return db.readonly_query(sql)


if __name__ == "__main__":
    db.init_db()
    mcp.run()
