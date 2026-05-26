# tests/test_tools_grading.py
import json
from unittest.mock import MagicMock, patch

SAMPLE_RUBRIC_JSON = json.dumps([
    {"name": "Correctness", "weight": 0.5, "max_points": 50, "description": "Correct output?"},
    {"name": "Quality", "weight": 0.5, "max_points": 50, "description": "Clean code?"},
])

SAMPLE_GRADE_RESPONSE = json.dumps({
    "criteria_scores": {"Correctness": 45.0, "Quality": 40.0},
    "score": 85.0,
    "max_score": 100.0,
    "feedback_text": "Good work! A few edge cases missed.",
    "inline_comments": [],
})


class TestAnalyzeSubmission:
    def test_parses_json_with_code_fences(self):
        mock_resp = MagicMock()
        mock_resp.content = f"```json\n{SAMPLE_GRADE_RESPONSE}\n```"
        with patch("ta.tools.grading._get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_resp
            from ta.tools.grading import analyze_submission
            result = analyze_submission.invoke({
                "submission_text": "def add(a, b): return a + b",
                "rubric_json": SAMPLE_RUBRIC_JSON,
                "assignment_type": "code",
            })
        parsed = json.loads(result)
        assert parsed["score"] == 85.0
        assert "Correctness" in parsed["criteria_scores"]

    def test_parses_json_without_code_fences(self):
        mock_resp = MagicMock()
        mock_resp.content = SAMPLE_GRADE_RESPONSE
        with patch("ta.tools.grading._get_llm") as mock_llm:
            mock_llm.return_value.invoke.return_value = mock_resp
            from ta.tools.grading import analyze_submission
            result = analyze_submission.invoke({
                "submission_text": "def add(a, b): return a + b",
                "rubric_json": SAMPLE_RUBRIC_JSON,
                "assignment_type": "code",
            })
        assert json.loads(result)["feedback_text"] == "Good work! A few edge cases missed."


class TestLoadRubric:
    def test_loads_yaml(self, tmp_path):
        f = tmp_path / "rubric.yaml"
        f.write_text(
            "criteria:\n"
            "  - name: Correctness\n    weight: 0.5\n    max_points: 50\n    description: Is it correct?\n"  # noqa: E501
            "  - name: Style\n    weight: 0.5\n    max_points: 50\n    description: Is it clean?\n"  # noqa: E501
        )
        from ta.tools.grading import load_rubric
        parsed = json.loads(load_rubric.invoke({"rubric_path": str(f)}))
        assert len(parsed) == 2 and parsed[0]["name"] == "Correctness"

    def test_error_on_missing_file(self, tmp_path):
        from ta.tools.grading import load_rubric
        result = load_rubric.invoke({"rubric_path": str(tmp_path / "missing.yaml")})
        assert "error" in result.lower() or "not found" in result.lower()
