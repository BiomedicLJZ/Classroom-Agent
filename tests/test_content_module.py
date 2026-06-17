# tests/test_content_module.py
import json
from unittest.mock import MagicMock, patch


class TestSyllabusValidation:
    def test_valid_syllabus_saves_and_normalizes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASE_WORKSPACE_PATH", str(tmp_path))
        from ta.tools.planning import save_syllabus
        syl = json.dumps([
            {"week": 1, "topic_name": "Intro",
             "assignments": [{"title": "HW1", "points": 10}],
             "announcements": ["Welcome"]}
        ])
        res = save_syllabus.invoke({"course_name": "C1", "syllabus_json": syl})
        assert "SUCCESS" in res
        saved = json.loads((tmp_path / "C1" / "syllabus.json").read_text(encoding="utf-8"))
        assert saved[0]["topic_name"] == "Intro"
        assert saved[0]["assignments"][0]["title"] == "HW1"

    def test_invalid_json_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASE_WORKSPACE_PATH", str(tmp_path))
        from ta.tools.planning import save_syllabus
        res = save_syllabus.invoke({"course_name": "C1", "syllabus_json": "{not json"})
        assert res.startswith("ERROR: Invalid JSON")

    def test_missing_required_field_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BASE_WORKSPACE_PATH", str(tmp_path))
        from ta.tools.planning import save_syllabus
        # week object missing required 'topic_name'
        res = save_syllabus.invoke(
            {"course_name": "C1", "syllabus_json": json.dumps([{"week": 1}])}
        )
        assert "failed validation" in res
        assert "topic_name" in res


class TestRichDocx:
    def test_write_word_renders_headings_code_table(self, tmp_path):
        from ta.tools.office import read_word_file, write_word_file
        md = (
            "# H1\n\n## H2\n\n### H3\n\n- bullet\n\n1. numbered\n\n"
            "```\ncode_line()\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        )
        p = tmp_path / "d.docx"
        out = write_word_file.invoke({"file_path": str(p), "content": md})
        assert "SUCCESS" in out
        back = read_word_file.invoke({"file_path": str(p)})
        assert "H1" in back and "H3" in back
        assert "code_line()" in back
        assert "A | B" in back  # markdown table rendered as a docx table

    def test_overwrite_guard_refuses(self, tmp_path):
        from ta.tools.office import write_word_file
        p = tmp_path / "d.docx"
        write_word_file.invoke({"file_path": str(p), "content": "# x"})
        res = write_word_file.invoke(
            {"file_path": str(p), "content": "# y", "overwrite": False}
        )
        assert res.startswith("REFUSED")


class TestTextOverwriteGuard:
    def test_write_text_refuses_without_overwrite(self, tmp_path):
        from ta.tools.files import write_text_file
        p = tmp_path / "x.md"
        write_text_file.invoke({"file_path": str(p), "content": "a"})
        res = write_text_file.invoke(
            {"file_path": str(p), "content": "b", "overwrite": False}
        )
        assert res.startswith("REFUSED")
        assert p.read_text(encoding="utf-8") == "a"  # original preserved


class TestPdfExport:
    def test_export_md_to_pdf(self, tmp_path):
        from ta.tools.office import export_to_pdf
        md = tmp_path / "g.md"
        md.write_text("# Título ñ á\n\n- punto\n\n```\nx = 1\n```\n", encoding="utf-8")
        res = export_to_pdf.invoke({"source_path": str(md)})
        assert "SUCCESS" in res
        pdf = md.with_suffix(".pdf")
        assert pdf.exists() and pdf.stat().st_size > 0


class TestPerAgentModel:
    def test_build_llm_google_without_key_returns_none(self):
        from ta.agent import _build_llm
        from ta.config import Settings
        assert _build_llm(Settings(google_api_key=""), "google", True) is None

    def test_build_llm_nvidia_builds(self):
        from ta.agent import _build_llm
        from ta.config import Settings
        with patch("ta.agent.ChatNVIDIA", return_value=MagicMock()):
            assert _build_llm(Settings(nvidia_api_key="k"), "nvidia", True) is not None

    def test_content_subagent_falls_back_to_main_llm(self):
        from ta import agent as agent_mod
        from ta.config import Settings
        with patch("ta.agent.ChatNVIDIA", return_value=MagicMock()), \
             patch("ta.agent.create_deep_agent") as mock_create:
            mock_create.return_value = MagicMock()
            agent_mod.build_agent(
                Settings(nvidia_api_key="k", google_api_key=""),
                checkpointer=MagicMock(),
            )
            subagents = mock_create.call_args.kwargs["subagents"]
            content = next(s for s in subagents if s["name"] == "content_agent")
            assert content["model"] is not None
