"""MCP tools for profile sync and automation (registered on the shared `mcp` app)."""

from __future__ import annotations

from .server import _READ, _arequest, _quote, mcp

# --- Sync: move logged-in profiles between machines ---------------------------


@mcp.tool(annotations=_READ)
async def sync_status() -> dict:
    """Per-profile sync state against the encrypted store: synced, remote-newer,
    local-only or remote-only."""
    return await _arequest("GET", "/sync")


@mcp.tool()
async def sync_push(name: str, force: bool = False) -> dict:
    """Upload a stopped profile (cookies, logins, fingerprint) so other machines can pull it.
    Refused when another machine pushed a newer version; pull first, or use force."""
    return await _arequest(
        "POST", f"/sync/{_quote(name)}/push", query={"force": str(force).lower()}
    )


@mcp.tool()
async def sync_pull(name: str, force: bool = False) -> dict:
    """Download a profile from the store; replaces the local copy (a .syncbak is kept)."""
    return await _arequest(
        "POST", f"/sync/{_quote(name)}/pull", query={"force": str(force).lower()}
    )


# --- Automation ---------------------------------------------------------------


@mcp.tool(annotations=_READ)
async def list_groups() -> dict:
    """Profile groups (name -> profiles)."""
    return await _arequest("GET", "/automation/groups")


@mcp.tool()
async def set_group(name: str, profiles: list[str]) -> dict:
    """Create or replace a group of profiles."""
    return await _arequest("PUT", f"/automation/groups/{_quote(name)}", {"profiles": profiles})


@mcp.tool(annotations=_READ)
async def list_tasks() -> dict:
    """Scheduled tasks with last run, status and next run."""
    return await _arequest("GET", "/automation/tasks")


@mcp.tool()
async def create_task(
    name: str,
    steps: list[dict] | None = None,
    template: str | None = None,
    profiles: list[str] | None = None,
    group: str | None = None,
    every_minutes: int | None = None,
    daily_at: str | None = None,
    jitter_seconds: int = 0,
    sync: bool = False,
) -> dict:
    """Schedule steps to run in profiles (launch, run, stop). A step is a dict with 'do' =
    goto{url} | wait{seconds or [min,max]} | scroll | click{selector} | type{selector,text} |
    press{key} | wait_for{selector} | evaluate{script} | screenshot | text. Or pass template
    'keepalive-gmail' or 'browse-warmup'. Set every_minutes or daily_at (HH:MM); with neither
    the task only runs on demand via run_task."""
    body = {
        "name": name,
        "steps": steps,
        "template": template,
        "profiles": profiles,
        "group": group,
        "every_minutes": every_minutes,
        "daily_at": daily_at,
        "jitter_seconds": jitter_seconds,
        "sync": sync,
    }
    return await _arequest("POST", "/automation/tasks", body)


@mcp.tool()
async def run_task(task_id: str) -> dict:
    """Run a task now, in the background."""
    return await _arequest("POST", f"/automation/tasks/{_quote(task_id)}/run")


@mcp.tool()
async def set_task_enabled(task_id: str, enabled: bool) -> dict:
    """Pause or resume a task's schedule."""
    return await _arequest(
        "POST",
        f"/automation/tasks/{_quote(task_id)}/enable",
        query={"enabled": str(enabled).lower()},
    )


@mcp.tool(annotations=_READ)
async def activity_log(limit: int = 50, profile: str | None = None) -> dict:
    """Recent automation events, newest first."""
    return await _arequest(
        "GET", "/automation/activity", query={"limit": limit, "profile": profile}
    )
