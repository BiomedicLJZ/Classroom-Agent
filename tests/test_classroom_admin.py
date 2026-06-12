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


class TestUpdateAssignment:
    def test_patches_only_provided_fields(self):
        svc = _service_mock()
        patch_call = svc.courses().courseWork().patch
        patch_call().execute.return_value = {"id": "w1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import update_assignment
            result = update_assignment.func(
                course_id="c1", coursework_id="w1", title="New title", max_points=50.0
            )
        kwargs = patch_call.call_args.kwargs
        assert kwargs["updateMask"] == "title,maxPoints"
        assert kwargs["body"] == {"title": "New title", "maxPoints": 50.0}
        assert "updated" in result

    def test_due_date_and_topic(self):
        svc = _service_mock()
        patch_call = svc.courses().courseWork().patch
        patch_call().execute.return_value = {"id": "w1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import update_assignment
            update_assignment.func(
                course_id="c1", coursework_id="w1",
                due_date="2026-07-01", due_time="23:59", topic_id="topic9",
            )
        kwargs = patch_call.call_args.kwargs
        assert kwargs["updateMask"] == "dueDate,dueTime,topicId"
        assert kwargs["body"]["dueDate"] == {"year": 2026, "month": 7, "day": 1}
        assert kwargs["body"]["dueTime"] == {"hours": 23, "minutes": 59}
        assert kwargs["body"]["topicId"] == "topic9"

    def test_no_fields_returns_message_without_interrupt(self):
        with patch("ta.tools.classroom.interrupt") as mock_intr, \
             patch("ta.tools.classroom._classroom_service"):
            from ta.tools.classroom import update_assignment
            result = update_assignment.func(course_id="c1", coursework_id="w1")
        assert "Nothing to update" in result
        mock_intr.assert_not_called()

    def test_cancelled_does_not_patch(self):
        svc = _service_mock()
        with patch("ta.tools.classroom.interrupt", return_value=False), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import update_assignment
            result = update_assignment.func(
                course_id="c1", coursework_id="w1", title="X"
            )
        assert "cancelled" in result.lower()
        svc.courses().courseWork().patch.assert_not_called()


class TestDeleteAssignment:
    def test_deletes_after_confirmation(self):
        svc = _service_mock()
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import delete_assignment
            result = delete_assignment.func(course_id="c1", coursework_id="w1")
        svc.courses().courseWork().delete.assert_called_once_with(
            courseId="c1", id="w1"
        )
        assert "deleted" in result

    def test_cancelled_does_not_delete(self):
        svc = _service_mock()
        with patch("ta.tools.classroom.interrupt", return_value=False), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import delete_assignment
            result = delete_assignment.func(course_id="c1", coursework_id="w1")
        assert "cancelled" in result.lower()
        svc.courses().courseWork().delete.assert_not_called()
