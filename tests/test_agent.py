# tests/test_agent.py
from unittest.mock import MagicMock, patch


class TestBuildAgent:
    def test_compiles_successfully(self):
        with patch("ta.agent.ChatNVIDIA") as mock_llm_cls, \
             patch("ta.agent.create_deep_agent") as mock_create:
            mock_llm_cls.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            from ta.agent import build_agent
            from ta.config import Settings
            result = build_agent(Settings())
            assert result is not None
            mock_create.assert_called_once()

    def test_llm_configured_with_reasoning(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        with patch("ta.agent.ChatNVIDIA") as mock_llm_cls, \
             patch("ta.agent.create_deep_agent") as mock_create:
            mock_llm_cls.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            from ta.agent import build_agent
            from ta.config import Settings
            build_agent(Settings())
            kwargs = mock_llm_cls.call_args.kwargs
            assert kwargs["temperature"] == 1.0
            assert kwargs["top_p"] == 0.95
            assert kwargs["max_tokens"] == 16384
            assert kwargs["reasoning_budget"] == 16384
            assert kwargs["chat_template_kwargs"] == {"enable_thinking": True}

    def test_prompts_have_no_legacy_thinking_toggle(self):
        from ta.agent import _GRADING_SUBAGENT_PROMPT, SYSTEM_PROMPT
        assert "detailed thinking" not in SYSTEM_PROMPT.lower()
        assert "detailed thinking" not in _GRADING_SUBAGENT_PROMPT.lower()

    def test_system_prompt_has_rewrite_protocol(self):
        from ta.agent import SYSTEM_PROMPT
        assert "REWRITE PROTOCOL" in SYSTEM_PROMPT

    def test_all_tools_registered(self):
        from ta.tools import ALL_TOOLS
        names = [t.name for t in ALL_TOOLS]
        for expected in [
            "list_courses", "post_announcement", "create_assignment",
            "get_submission_status", "analyze_submission", "batch_grade_assignment",
            "load_rubric", "post_grade", "get_drive_file_text", "get_doc_text",
            "add_doc_comment",
            # rework additions
            "update_assignment", "delete_assignment",
            "list_announcements", "update_announcement", "delete_announcement",
            "list_materials", "update_material", "delete_material",
            "list_topics", "create_topic", "export_grades",
        ]:
            assert expected in names, f"Missing tool: {expected}"

    def test_minimum_tool_count(self):
        from ta.tools import ALL_TOOLS
        assert len(ALL_TOOLS) >= 42
