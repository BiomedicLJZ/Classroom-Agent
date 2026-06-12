# tests/test_grading.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage


class TestGradingLLM:
    def test_get_llm_uses_reasoning_settings(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        from ta.tools import grading
        grading._get_llm.cache_clear()
        with patch("ta.tools.grading.ChatNVIDIA") as mock_cls:
            mock_cls.return_value = MagicMock()
            grading._get_llm()
            kwargs = mock_cls.call_args.kwargs
            assert kwargs["temperature"] == 1.0
            assert kwargs["reasoning_budget"] == 16384
            assert kwargs["chat_template_kwargs"] == {"enable_thinking": True}
        grading._get_llm.cache_clear()

    def test_grading_prompt_no_legacy_toggle(self):
        from ta.tools.grading import GRADING_SYSTEM_PROMPT
        assert "detailed thinking" not in GRADING_SYSTEM_PROMPT.lower()

    def test_analyze_submission_handles_block_content(self):
        grade_json = (
            '{"criteria_scores": {"Q": 5.0}, "score": 5.0, "max_score": 5.0, '
            '"feedback_text": "ok", "inline_comments": []}'
        )
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = AIMessage(
            content=[{"type": "text", "text": grade_json}]
        )
        with patch("ta.tools.grading._get_llm", return_value=fake_llm):
            from ta.tools.grading import analyze_submission
            result = analyze_submission.func(
                submission_text="print('hi')", rubric_json="[]", assignment_type="code"
            )
        assert '"score": 5.0' in result


class TestExportGrades:
    def test_exports_matrix_to_xlsx(self, tmp_path):
        svc = MagicMock()
        svc.courses().students().list().execute.return_value = {
            "students": [
                {
                    "userId": "s1",
                    "profile": {
                        "name": {"fullName": "Ana López"},
                        "emailAddress": "ana@school.mx",
                    },
                },
                {
                    "userId": "s2",
                    "profile": {
                        "name": {"fullName": "Beto Ruiz"},
                        "emailAddress": "beto@school.mx",
                    },
                },
            ]
        }
        svc.courses().courseWork().list().execute.return_value = {
            "courseWork": [{"id": "w1", "title": "HW1"}, {"id": "w2", "title": "HW2"}]
        }
        svc.courses().courseWork().studentSubmissions().list().execute.side_effect = [
            {"studentSubmissions": [
                {"userId": "s1", "assignedGrade": 9.5},
                {"userId": "s2"},  # ungraded
            ]},
            {"studentSubmissions": [
                {"userId": "s1", "assignedGrade": 8.0},
                {"userId": "s2", "assignedGrade": 10.0},
            ]},
        ]
        out = tmp_path / "grades.xlsx"
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.grading import export_grades
            result = export_grades.func(course_id="c1", output_path=str(out))

        assert out.exists()
        from openpyxl import load_workbook
        ws = load_workbook(out)["Grades"]
        rows = list(ws.values)
        assert rows[0] == ("Student", "Email", "HW1", "HW2")
        assert rows[1] == ("Ana López", "ana@school.mx", 9.5, 8.0)
        assert rows[2] == ("Beto Ruiz", "beto@school.mx", None, 10.0)
        assert "2 students" in result
