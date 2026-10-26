"""Validated, editable Malwarfare preparation profile."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .runtime.geometry import CANONICAL_HEIGHT, CANONICAL_WIDTH, Rect


@dataclass(frozen=True)
class MalwarfareTaskProfile:
    task_id: str
    sample_type: str
    base_roi: Rect
    font_profile: str
    allowed_labels: tuple[str, ...]
    payload: Mapping[str, Any]

    def effective_roi(self, *, padding_x: int, padding_y: int, vertical_offset: int) -> Rect:
        left = self.base_roi.x - padding_x
        top = self.base_roi.y + vertical_offset - padding_y
        right = self.base_roi.right + padding_x
        bottom = self.base_roi.bottom + vertical_offset + padding_y
        if left < 0 or top < 0 or right > CANONICAL_WIDTH or bottom > CANONICAL_HEIGHT:
            raise ValueError(f"effective ROI for {self.task_id} is outside canonical geometry")
        return Rect(left, top, right - left, bottom - top)


@dataclass(frozen=True)
class MalwarfareProfile:
    profile_id: str
    ui_language: str
    padding_x: int
    padding_y: int
    ui_offsets: Mapping[str, int]
    default_ui_profile: str
    tasks: Mapping[str, MalwarfareTaskProfile]
    raw: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.padding_x < 0 or self.padding_y < 0:
            raise ValueError("ROI padding must be non-negative")
        if self.default_ui_profile not in self.ui_offsets:
            raise ValueError("default UI profile is not defined in ui_offsets")
        if set(self.tasks) != {"count", "time", "paused"}:
            raise ValueError("Malwarfare profile must define count, time, and paused tasks")

    def resolved_task(self, task_id: str, ui_profile: str) -> tuple[MalwarfareTaskProfile, Rect]:
        if ui_profile not in self.ui_offsets:
            raise ValueError(f"unknown UI profile: {ui_profile}")
        task = self.tasks[task_id]
        return task, task.effective_roi(
            padding_x=self.padding_x,
            padding_y=self.padding_y,
            vertical_offset=int(self.ui_offsets[ui_profile]),
        )


def _task(task_id: str, payload: Mapping[str, Any]) -> MalwarfareTaskProfile:
    xyxy = payload.get("base_roi_xyxy")
    if not isinstance(xyxy, list) or len(xyxy) != 4:
        raise ValueError(f"{task_id}.base_roi_xyxy must contain x0,y0,x1,y1")
    x0, y0, x1, y1 = (int(value) for value in xyxy)
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"{task_id}.base_roi_xyxy must be non-empty and half-open")
    allowed = tuple(str(value) for value in payload.get("allowed_labels", ()))
    if not allowed or len(allowed) != len(set(allowed)):
        raise ValueError(f"{task_id}.allowed_labels must be non-empty and unique")
    return MalwarfareTaskProfile(
        task_id=task_id,
        sample_type=str(payload["sample_type"]),
        base_roi=Rect(x0, y0, x1 - x0, y1 - y0),
        font_profile=str(payload["font_profile"]),
        allowed_labels=allowed,
        payload=dict(payload),
    )


def load_profile(path: str | Path) -> MalwarfareProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported Malwarfare profile schema")
    canonical = payload.get("canonicalization", {})
    if canonical.get("width") != CANONICAL_WIDTH or canonical.get("height") != CANONICAL_HEIGHT:
        raise ValueError("Malwarfare profile canonical geometry must be 1920x1080")
    if canonical.get("interpolation") != "INTER_AREA":
        raise ValueError("Malwarfare preparation requires INTER_AREA")
    padding = payload.get("roi_padding", {})
    tasks_payload = payload.get("tasks", {})
    tasks = {task_id: _task(task_id, tasks_payload[task_id]) for task_id in ("count", "time", "paused")}
    return MalwarfareProfile(
        profile_id=str(payload["profile_id"]),
        ui_language=str(payload["ui_language"]),
        padding_x=int(padding["x"]),
        padding_y=int(padding["y"]),
        ui_offsets={str(key): int(value) for key, value in payload.get("ui_offsets", {}).items()},
        default_ui_profile=str(payload["default_ui_profile"]),
        tasks=tasks,
        raw=payload,
    )


def validate_raw_label(task_id: str, status: str, raw_label: Any) -> None:
    """Validate human annotation semantics without interpreting game events."""

    if status not in {"pending", "accepted", "empty", "ignore"}:
        raise ValueError(f"invalid annotation status: {status}")
    if status == "pending":
        if raw_label is not None:
            raise ValueError("pending annotations must not contain raw_label")
        return
    if status in {"empty", "ignore"}:
        if raw_label not in (None, status):
            raise ValueError(f"{status} annotation raw_label must be null or {status!r}")
        return
    if not isinstance(raw_label, str):
        raise ValueError("accepted annotations require a string raw_label")
    if task_id == "count" and raw_label not in {"c0", "c1", "c2", "c3", "c4"}:
        raise ValueError("accepted count raw_label must be c0 through c4")
    if task_id == "time" and (len(raw_label) != 3 or not raw_label.isascii() or not raw_label.isdigit() or not 0 <= int(raw_label) <= 359):
        raise ValueError("accepted time raw_label must be an MSS string from 000 through 359")
    if task_id == "paused" and raw_label != "paused":
        raise ValueError("accepted paused raw_label must be 'paused'")
    if task_id not in {"count", "time", "paused"}:
        raise ValueError(f"unknown task_id: {task_id}")
