# ta/state.py
from __future__ import annotations

from typing import Annotated, Any, NotRequired

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.managed.is_last_step import RemainingStepsManager
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


class TAState(TypedDict):
    # Conversation history — append-only via add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Session context
    active_course_id: str | None
    active_course_name: str | None
    active_assignment_id: str | None

    # Grading session — populated by batch_grade_assignment, flushed on post
    rubric: list[RubricCriteria] | None
    pending_grades: list[GradeResult]

    # Scratch space for tool output
    last_tool_result: Any | None

    # Confirmation state — paired with interrupt() in destructive tools
    awaiting_confirmation: bool
    confirmation_action: str | None

    # Required by LangGraph create_react_agent for recursion budget tracking
    remaining_steps: NotRequired[Annotated[int, RemainingStepsManager]]
