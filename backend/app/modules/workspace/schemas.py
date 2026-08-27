from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceOverviewCardOut(BaseModel):
    module_key: str
    title: str
    metric_label: str
    metric_value: str
    subtitle: str | None = None
    link: str


class WorkspaceOverviewOut(BaseModel):
    cards: list[WorkspaceOverviewCardOut] = Field(default_factory=list)
