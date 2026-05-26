# tests/test_tools_drive.py
from unittest.mock import patch


class TestGetDriveFileText:
    def test_reads_google_doc(self):
        with patch("ta.tools.drive._drive_service") as mock_svc:
            mock_svc.return_value.files.return_value.get.return_value.execute.return_value = {
                "mimeType": "application/vnd.google-apps.document"
            }
            mock_svc.return_value.files.return_value.export_media.return_value.execute.return_value = b"Document content."  # noqa: E501
            from ta.tools.drive import get_drive_file_text
            result = get_drive_file_text.invoke({"file_id": "doc123"})
        assert "Document content" in result

    def test_reads_python_file(self):
        with patch("ta.tools.drive._drive_service") as mock_svc:
            mock_svc.return_value.files.return_value.get.return_value.execute.return_value = {
                "mimeType": "text/x-python"
            }
            mock_svc.return_value.files.return_value.get_media.return_value.execute.return_value = b"print('hello')"  # noqa: E501
            from ta.tools.drive import get_drive_file_text
            result = get_drive_file_text.invoke({"file_id": "py123"})
        assert "hello" in result

    def test_unsupported_mime(self):
        with patch("ta.tools.drive._drive_service") as mock_svc:
            mock_svc.return_value.files.return_value.get.return_value.execute.return_value = {
                "mimeType": "image/png", "name": "diagram.png"
            }
            from ta.tools.drive import get_drive_file_text
            result = get_drive_file_text.invoke({"file_id": "img123"})
        assert "cannot read" in result.lower() or "image/png" in result


class TestGetDocText:
    def test_concatenates_paragraphs(self):
        mock_doc = {"body": {"content": [
            {"paragraph": {"elements": [{"textRun": {"content": "Hello "}}]}},
            {"paragraph": {"elements": [{"textRun": {"content": "World\n"}}]}},
        ]}}
        with patch("ta.tools.docs._docs_service") as mock_svc:
            mock_svc.return_value.documents.return_value.get.return_value.execute.return_value = mock_doc  # noqa: E501
            from ta.tools.docs import get_doc_text
            result = get_doc_text.invoke({"document_id": "doc456"})
        assert "Hello" in result and "World" in result
