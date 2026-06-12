# tests/test_classroom_admin.py
from unittest.mock import MagicMock, patch


def _service_mock():
    """MagicMock standing in for the Classroom service resource."""
    return MagicMock()


class TestFullTextConfirmations:
    def test_post_announcement_shows_full_text(self):
        long_text = "Línea importante. " * 30  # ~540 chars, > old 200-char cut
        captured: list[dict] = []
        svc = _service_mock()
        svc.courses().announcements().create().execute.return_value = {"id": "a1"}
        with patch("ta.tools.classroom.interrupt",
                   side_effect=lambda p: captured.append(p) or True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import post_announcement
            post_announcement.func(course_id="c1", text=long_text)
        assert long_text in captured[0]["details"]

    def test_create_assignment_shows_description(self):
        captured: list[dict] = []
        svc = _service_mock()
        svc.courses().courseWork().create().execute.return_value = {
            "id": "w1", "title": "T"
        }
        with patch("ta.tools.classroom.interrupt",
                   side_effect=lambda p: captured.append(p) or True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import create_assignment
            create_assignment.func(
                course_id="c1", title="T", description="FULL_DESCRIPTION_BODY",
                max_points=10.0, due_date="2026-06-20", due_time="23:59",
                materials_drive_ids=[],
            )
        assert "FULL_DESCRIPTION_BODY" in captured[0]["details"]

    def test_create_material_shows_description(self):
        captured: list[dict] = []
        svc = _service_mock()
        svc.courses().courseWorkMaterials().create().execute.return_value = {"id": "m1"}
        with patch("ta.tools.classroom.interrupt",
                   side_effect=lambda p: captured.append(p) or True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import create_material
            create_material.func(
                course_id="c1", title="M", description="MATERIAL_DESC_BODY",
                drive_file_ids=[], youtube_urls=[], link_urls=[],
            )
        assert "MATERIAL_DESC_BODY" in captured[0]["details"]
