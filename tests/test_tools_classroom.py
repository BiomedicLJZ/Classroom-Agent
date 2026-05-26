# tests/test_tools_classroom.py
from unittest.mock import patch


class TestListCourses:
    def test_returns_course_list(self):
        mock_response = {"courses": [
            {"id": "123", "name": "AI 101", "section": "A"},
            {"id": "456", "name": "ML 201", "section": "B"},
        ]}
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            mock_svc.return_value.courses.return_value.list.return_value.execute.return_value = mock_response  # noqa: E501
            from ta.tools.classroom import list_courses
            result = list_courses.invoke({})
        assert "AI 101" in result and "ML 201" in result

    def test_returns_message_when_no_courses(self):
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            mock_svc.return_value.courses.return_value.list.return_value.execute.return_value = {"courses": []}  # noqa: E501
            from ta.tools.classroom import list_courses
            result = list_courses.invoke({})
        assert "no" in result.lower()


class TestListStudents:
    def test_returns_student_list(self):
        mock_response = {"students": [
            {"userId": "u1", "profile": {"name": {"fullName": "Ana García"}, "emailAddress": "ana@school.edu"}},  # noqa: E501
        ]}
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            mock_svc.return_value.courses.return_value.students.return_value.list.return_value.execute.return_value = mock_response  # noqa: E501
            from ta.tools.classroom import list_students
            result = list_students.invoke({"course_id": "123"})
        assert "Ana García" in result


class TestGetSubmissionStatus:
    def test_shows_submission_states(self):
        mock_response = {"studentSubmissions": [
            {"userId": "u1", "state": "TURNED_IN", "id": "sub1"},
            {"userId": "u2", "state": "NEW", "id": "sub2"},
        ]}
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            (mock_svc.return_value.courses.return_value.courseWork.return_value
             .studentSubmissions.return_value.list.return_value.execute.return_value) = mock_response  # noqa: E501
            from ta.tools.classroom import get_submission_status
            result = get_submission_status.invoke({"course_id": "123", "coursework_id": "cw1"})
        assert "TURNED_IN" in result and "NEW" in result


class TestPostAnnouncement:
    def test_posts_when_confirmed(self):
        with (
            patch("ta.tools.classroom.interrupt", return_value=True),
            patch("ta.tools.classroom._classroom_service") as mock_svc,
        ):
            mock_svc.return_value.courses.return_value.announcements.return_value.create.return_value.execute.return_value = {"id": "ann1"}  # noqa: E501
            from ta.tools.classroom import post_announcement
            result = post_announcement.invoke({"course_id": "123", "text": "Hello class!"})
        assert "ann1" in result or "posted" in result.lower()

    def test_cancels_when_declined(self):
        with patch("ta.tools.classroom.interrupt", return_value=False):
            from ta.tools.classroom import post_announcement
            result = post_announcement.invoke({"course_id": "123", "text": "Hello class!"})
        assert "cancel" in result.lower()


class TestCreateAssignment:
    def test_creates_when_confirmed(self):
        with (
            patch("ta.tools.classroom.interrupt", return_value=True),
            patch("ta.tools.classroom._classroom_service") as mock_svc,
        ):
            mock_svc.return_value.courses.return_value.courseWork.return_value.create.return_value.execute.return_value = {  # noqa: E501
                "id": "cw99", "title": "HW1"
            }
            from ta.tools.classroom import create_assignment
            result = create_assignment.invoke({
                "course_id": "123", "title": "HW1", "description": "Do the thing",
                "max_points": 100.0, "due_date": "2026-06-01", "due_time": "23:59",
                "materials_drive_ids": [],
            })
        assert "cw99" in result or "created" in result.lower()
