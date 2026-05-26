# tests/test_state.py
import pytest
from langchain_core.messages import HumanMessage

from ta.state import GradeResult, RubricCriteria, TAState


class TestTAState:
    def test_minimal_state_has_messages(self):
        state: TAState = {
            "messages": [HumanMessage(content="hello")],
            "active_course_id": None,
            "active_course_name": None,
            "active_assignment_id": None,
            "rubric": None,
            "pending_grades": [],
            "last_tool_result": None,
            "awaiting_confirmation": False,
            "confirmation_action": None,
        }
        assert len(state["messages"]) == 1

    def test_rubric_criteria_fields(self):
        c: RubricCriteria = {
            "name": "Correctness",
            "weight": 0.40,
            "max_points": 40.0,
            "description": "Does it produce correct output?",
        }
        assert c["weight"] == pytest.approx(0.40)

    def test_grade_result_fields(self):
        r: GradeResult = {
            "student_id": "abc123",
            "submission_id": "sub456",
            "score": 87.5,
            "max_score": 100.0,
            "criteria_scores": {"Correctness": 35.0},
            "feedback_text": "Good work.",
            "inline_comments": [],
        }
        assert r["score"] == 87.5
