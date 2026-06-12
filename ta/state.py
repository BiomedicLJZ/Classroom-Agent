# ta/state.py
from __future__ import annotations

from typing import Any, NotRequired

from deepagents import DeepAgentState
from typing_extensions import TypedDict


class RubricCriteria(TypedDict):
    name: str
    weight: float
    max_points: float
    description: str


class GradeResult(TypedDict):
    student_id: str
    submission_id: str
    score: float
    max_score: float
    criteria_scores: dict[str, float]
    feedback_text: str
    inline_comments: list[dict]


class TAState(DeepAgentState):
    # Session context
    active_course_id: NotRequired[str | None]
    active_course_name: NotRequired[str | None]
    active_assignment_id: NotRequired[str | None]

    # Grading session — populated by batch_grade_assignment, flushed on post
    rubric: NotRequired[list[RubricCriteria] | None]
    pending_grades: NotRequired[list[GradeResult]]

    # Scratch space for tool output
    last_tool_result: NotRequired[Any | None]

    # Confirmation state — paired with interrupt() in destructive tools
    awaiting_confirmation: NotRequired[bool]
    confirmation_action: NotRequired[str | None]
