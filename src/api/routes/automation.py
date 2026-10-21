"""Profile groups, scheduled tasks and the activity log."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ...services.automation.engine import STEP_VERBS, TEMPLATES, Automation, AutomationError

router = APIRouter(prefix="/automation", tags=["automation"])


def get_auto(request: Request) -> Automation:
    return request.app.state.container.automation


class GroupBody(BaseModel):
    profiles: list[str]


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    steps: list[dict[str, Any]] | None = Field(
        None, description=f"Steps like {{'do':'goto','url':...}}; verbs: {sorted(STEP_VERBS)}"
    )
    template: str | None = Field(None, description=f"One of {sorted(TEMPLATES)}")
    profiles: list[str] | None = None
    group: str | None = None
    every_minutes: int | None = None
    daily_at: str | None = Field(None, description="HH:MM local time")
    jitter_seconds: int = 0
    stop_after: bool = True
    sync: bool = Field(False, description="Pull before and push after (needs sync configured)")
    enabled: bool = True


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AutomationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/groups")
def groups(a: Automation = Depends(get_auto)) -> dict:
    return {"groups": a.groups()}


@router.put("/groups/{name}")
def set_group(name: str, body: GroupBody, a: Automation = Depends(get_auto)) -> dict:
    return {"name": name, "profiles": _guard(a.set_group, name, body.profiles)}


@router.delete("/groups/{name}")
def delete_group(name: str, a: Automation = Depends(get_auto)) -> dict:
    if not a.delete_group(name):
        raise HTTPException(status_code=404, detail="group not found")
    return {"success": True}


@router.get("/templates")
def templates() -> dict:
    return {"templates": TEMPLATES, "verbs": {k: list(v) for k, v in STEP_VERBS.items()}}


@router.get("/tasks")
def tasks(a: Automation = Depends(get_auto)) -> dict:
    return {"tasks": a.tasks()}


@router.post("/tasks")
def create_task(body: TaskCreate, a: Automation = Depends(get_auto)) -> dict:
    return _guard(a.create_task, **body.model_dump())


@router.post("/tasks/{task_id}/run")
def run_task(task_id: str, a: Automation = Depends(get_auto)) -> dict:
    return _guard(a.run_task, task_id)


@router.post("/tasks/{task_id}/enable")
def enable(task_id: str, enabled: bool = True, a: Automation = Depends(get_auto)) -> dict:
    return _guard(a.set_enabled, task_id, enabled)


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, a: Automation = Depends(get_auto)) -> dict:
    if not a.delete_task(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return {"success": True}


@router.get("/activity")
def activity(
    limit: int = Query(100, ge=1, le=1000),
    profile: str | None = None,
    a: Automation = Depends(get_auto),
) -> dict:
    return {"events": a.log.tail(limit, profile)}
