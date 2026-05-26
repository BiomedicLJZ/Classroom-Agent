# tests/test_agent.py
from unittest.mock import MagicMock, patch


class TestBuildAgent:
    def test_compiles_successfully(self):
        with patch("ta.agent.ChatNVIDIA") as mock_llm_cls:
            mock_llm_cls.return_value = MagicMock()
            from ta.agent import build_agent
            from ta.config import Settings
            assert build_agent(Settings()) is not None

    def test_all_tools_registered(self):
        from ta.tools import ALL_TOOLS
        names = [t.name for t in ALL_TOOLS]
        for expected in [
            "list_courses", "post_announcement", "create_assignment",
            "get_submission_status", "analyze_submission", "batch_grade_assignment",
            "load_rubric", "post_grade", "get_drive_file_text", "get_doc_text", "add_doc_comment",
        ]:
            assert expected in names, f"Missing tool: {expected}"

    def test_minimum_tool_count(self):
        from ta.tools import ALL_TOOLS
        assert len(ALL_TOOLS) >= 15
