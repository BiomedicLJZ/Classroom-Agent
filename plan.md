# LangGraph Classroom TA Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI-based AI Teaching Assistant that manages Google Classroom admin duties (announcements, assignments, materials, grading, feedback) using a LangGraph ReAct agent powered by ChatNVIDIA models.

**Architecture:** Single `create_react_agent` ReAct loop with ~17 Google API tools; destructive tools call `interrupt()` before writing, pausing for CLI confirmation. OAuth2 credentials are cached in `credentials/token.json` after the first browser-based consent flow.

**Tech Stack:** Python 3.13+, LangGraph ≥1.2.1, LangChain ≥1.3.1, langchain-nvidia-ai-endpoints, google-api-python-client + google-auth-oauthlib, pydantic-settings, rich, pyyaml, pypdf, pytest + pytest-mock.

---

## File Map

| File | Responsibility |
|---|---|
| `ta/__init__.py` | Package marker |
| `ta/config.py` | Pydantic-settings config (API keys, paths) |
| `ta/google_auth.py` | OAuth2 credential manager (token file caching) |
| `ta/state.py` | `TAState` TypedDict + `RubricCriteria` / `GradeResult` types |
| `ta/agent.py` | Graph construction via `create_react_agent`, system prompt |
| `ta/cli.py` | REPL loop, interrupt handling, rich output |
| `ta/tools/__init__.py` | `ALL_TOOLS` export list |
| `ta/tools/classroom.py` | Google Classroom API tools (read + write) |
| `ta/tools/drive.py` | Google Drive file download/upload tools |
| `ta/tools/docs.py` | Google Docs read + inline comment tools |
| `ta/tools/grading.py` | AI-powered grading tools (analyze + batch + post) |
| `main.py` | CLI entrypoint |
| `.env.example` | Template for required env vars |
| `credentials/` | Gitignored — holds client_secret.json + token.json |
| `rubrics/example_rubric.yaml` | Sample grading rubric |
| `tests/conftest.py` | Shared pytest fixtures (mock creds, mock API) |
| `tests/test_state.py` | State schema unit tests |
| `tests/test_tools_classroom.py` | Classroom tool tests (mocked API) |
| `tests/test_tools_grading.py` | Grading tool tests (mocked LLM + API) |
| `tests/test_tools_drive.py` | Drive/Docs tool tests |
| `tests/test_agent.py` | Graph compilation + tool registration integration test |
| `tests/test_cli.py` | CLI REPL logic with mocked graph.stream() |

---

## Prerequisites (do once before coding)

### Google Cloud Setup

1. Go to https://console.cloud.google.com
2. Create a project named **ta-agent**
3. Enable these APIs (APIs & Services > Library):
   - Google Classroom API
   - Google Drive API
   - Google Docs API
4. OAuth consent screen > External > fill App name, your email
5. Add scopes:
   ```
   https://www.googleapis.com/auth/classroom.courses.readonly
   https://www.googleapis.com/auth/classroom.coursework.students
   https://www.googleapis.com/auth/classroom.coursework.me
   https://www.googleapis.com/auth/classroom.announcements
   https://www.googleapis.com/auth/classroom.rosters.readonly
   https://www.googleapis.com/auth/classroom.student-submissions.students.readonly
   https://www.googleapis.com/auth/drive
   https://www.googleapis.com/auth/documents
   ```
6. Add your Google account as a **test user**
7. Credentials > Create Credentials > OAuth client ID > Desktop app > download JSON
8. Save downloaded JSON as `credentials/client_secret.json`

### NVIDIA NIM Setup

1. Sign up at https://build.nvidia.com
2. Create an API key (starts with `nvapi-...`)
3. Add to `.env` as `NVIDIA_API_KEY=nvapi-...`

---

## Task 1: Project Setup & Dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `.env.example`, `.gitignore`, `credentials/.gitkeep`, `rubrics/example_rubric.yaml`

- [ ] **Step 1: Replace `pyproject.toml`**

```toml
[project]
name = "agentes"
version = "0.1.0"
description = "LangGraph AI Teaching Assistant for Google Classroom"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "google-api-python-client>=2.196.0",
    "google-auth>=2.35.0",
    "google-auth-oauthlib>=1.2.1",
    "google-auth-httplib2>=0.2.0",
    "langgraph>=1.2.1",
    "langchain>=1.3.1",
    "langchain-nvidia-ai-endpoints>=1.4.0",
    "pydantic-settings>=2.7.0",
    "python-dotenv>=1.0.1",
    "pyyaml>=6.0.2",
    "rich>=13.9.0",
    "pypdf>=5.1.0",
    "ipykernel>=7.2.0",
    "jupyter>=1.1.1",
    "jupyterlab>=4.5.7",
    "notebook>=7.5.6",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.8.0",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Install dependencies**

```bash
uv sync
```

Expected: All packages resolve. No errors.

- [ ] **Step 3: Create `.env.example`**

```
NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE
NVIDIA_MODEL=meta/llama-3.3-70b-instruct
GOOGLE_CLIENT_SECRET_PATH=credentials/client_secret.json
GOOGLE_TOKEN_PATH=credentials/token.json
```

- [ ] **Step 4: Create `.env` and fill in your NVIDIA key**

```bash
cp .env.example .env
# Edit .env — replace nvapi-YOUR_KEY_HERE with your real key
```

- [ ] **Step 5: Create `.gitignore`**

```
credentials/
.env
__pycache__/
.venv/
*.pyc
.pytest_cache/
*.egg-info/
dist/
build/
```

- [ ] **Step 6: Create `credentials/` directory and `rubrics/example_rubric.yaml`**

```bash
mkdir credentials
```

```yaml
# rubrics/example_rubric.yaml
criteria:
  - name: Correctness
    weight: 0.40
    max_points: 40
    description: |
      Does the code produce the expected outputs for all test cases?
      Does it handle edge cases and error conditions correctly?
  - name: Code Quality
    weight: 0.25
    max_points: 25
    description: |
      Is the code readable, well-organized, and appropriately commented?
  - name: Documentation
    weight: 0.20
    max_points: 20
    description: |
      Are functions documented with docstrings? Is there an explanatory README?
  - name: Design
    weight: 0.15
    max_points: 15
    description: |
      Is the solution well-structured? Are abstractions appropriate?
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .env.example .gitignore credentials/ rubrics/
git commit -m "chore: add dependencies, env template, rubric example, gitignore"
```

---

## Task 2: Config & Auth Layer

**Files:**
- Create: `ta/__init__.py`, `ta/config.py`, `ta/google_auth.py`
- Create: `tests/__init__.py`, `tests/conftest.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing tests** — create `tests/__init__.py` (empty) and `tests/test_auth.py`:

```python
# tests/test_auth.py
import json
from unittest.mock import MagicMock, patch

import pytest

from ta.config import Settings
from ta.google_auth import SCOPES, get_credentials


class TestSettings:
    def test_loads_nvidia_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
        monkeypatch.setenv("GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json")
        monkeypatch.setenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
        settings = Settings()
        assert settings.nvidia_api_key == "nvapi-test"
        assert settings.nvidia_model == "meta/llama-3.3-70b-instruct"

    def test_raises_if_nvidia_key_missing(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(Exception):
            Settings()


class TestGetCredentials:
    def test_loads_from_existing_valid_token(self, tmp_path):
        token_data = {
            "token": "ya29.fake",
            "refresh_token": "1//fake",
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": "fake.apps.googleusercontent.com",
            "client_secret": "fake-secret",
            "scopes": SCOPES,
        }
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps(token_data))

        mock_creds = MagicMock()
        mock_creds.valid = True

        with patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=mock_creds):
            creds = get_credentials("fake_secret.json", str(token_file))

        assert creds is mock_creds

    def test_refreshes_expired_token(self, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "1//fake"
        mock_creds.to_json.return_value = "{}"

        with patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=mock_creds):
            with patch("ta.google_auth.Request") as mock_request:
                get_credentials("fake_secret.json", str(token_file))
                mock_creds.refresh.assert_called_once_with(mock_request())
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'ta'`

- [ ] **Step 3: Create `ta/__init__.py`** (empty)

- [ ] **Step 4: Create `ta/config.py`**

```python
# ta/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    nvidia_api_key: str
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    google_client_secret_path: str = "credentials/client_secret.json"
    google_token_path: str = "credentials/token.json"
```

- [ ] **Step 5: Create `ta/google_auth.py`**

```python
# ta/google_auth.py
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students",
    "https://www.googleapis.com/auth/classroom.coursework.me",
    "https://www.googleapis.com/auth/classroom.announcements",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def get_credentials(client_secret_path: str, token_path: str) -> Credentials:
    """Load OAuth2 credentials, refreshing or triggering browser flow as needed."""
    creds = None
    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())

    return creds
```

- [ ] **Step 6: Create `tests/conftest.py`**

```python
# tests/conftest.py
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_creds():
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    return creds


@pytest.fixture(autouse=True)
def set_required_env_vars(monkeypatch):
    """Ensure required env vars are set in every test."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET_PATH", "credentials/client_secret.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "credentials/token.json")
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add ta/ tests/
git commit -m "feat: config and Google OAuth2 auth layer"
```

---

## Task 3: State Schema

**Files:**
- Create: `ta/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_state.py -v
```

- [ ] **Step 3: Create `ta/state.py`**

```python
# ta/state.py
from __future__ import annotations

from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class RubricCriteria(TypedDict):
    name: str
    weight: float
    max_points: float
    description: str


class GradeResult(TypedDict):
    student_id: str
    submission_id: str
    score: float
    max_score: float
    criteria_scores: dict[str, float]
    feedback_text: str
    inline_comments: list[dict]


class TAState(TypedDict):
    # Conversation history — append-only via add_messages reducer
    messages: Annotated[list[BaseMessage], add_messages]

    # Session context
    active_course_id: Optional[str]
    active_course_name: Optional[str]
    active_assignment_id: Optional[str]

    # Grading session — populated by batch_grade_assignment, flushed on post
    rubric: Optional[list[RubricCriteria]]
    pending_grades: list[GradeResult]

    # Scratch space for tool output
    last_tool_result: Optional[Any]

    # Confirmation state — paired with interrupt() in destructive tools
    awaiting_confirmation: bool
    confirmation_action: Optional[str]
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_state.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ta/state.py tests/test_state.py
git commit -m "feat: TAState schema with grading session and confirmation fields"
```

---

## Task 4: Google Classroom Read Tools

**Files:**
- Create: `ta/tools/__init__.py` (stub), `ta/tools/classroom.py` (read section)
- Test: `tests/test_tools_classroom.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_classroom.py
from unittest.mock import patch


class TestListCourses:
    def test_returns_course_list(self):
        mock_response = {"courses": [
            {"id": "123", "name": "AI 101", "section": "A"},
            {"id": "456", "name": "ML 201", "section": "B"},
        ]}
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            mock_svc.return_value.courses.return_value.list.return_value.execute.return_value = mock_response
            from ta.tools.classroom import list_courses
            result = list_courses.invoke({})
        assert "AI 101" in result and "ML 201" in result

    def test_returns_message_when_no_courses(self):
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            mock_svc.return_value.courses.return_value.list.return_value.execute.return_value = {"courses": []}
            from ta.tools.classroom import list_courses
            result = list_courses.invoke({})
        assert "no" in result.lower()


class TestListStudents:
    def test_returns_student_list(self):
        mock_response = {"students": [
            {"userId": "u1", "profile": {"name": {"fullName": "Ana García"}, "emailAddress": "ana@school.edu"}},
        ]}
        with patch("ta.tools.classroom._classroom_service") as mock_svc:
            mock_svc.return_value.courses.return_value.students.return_value.list.return_value.execute.return_value = mock_response
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
             .studentSubmissions.return_value.list.return_value.execute.return_value) = mock_response
            from ta.tools.classroom import get_submission_status
            result = get_submission_status.invoke({"course_id": "123", "coursework_id": "cw1"})
        assert "TURNED_IN" in result and "NEW" in result
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_tools_classroom.py -v
```

- [ ] **Step 3: Create `ta/tools/__init__.py`** (stub)

```python
# ta/tools/__init__.py
# Completed in Task 8
ALL_TOOLS: list = []
```

- [ ] **Step 4: Create `ta/tools/classroom.py`** — read tools

```python
# ta/tools/classroom.py
import json
from functools import lru_cache

from googleapiclient.discovery import build
from langchain_core.tools import tool

from ta.config import Settings
from ta.google_auth import get_credentials


@lru_cache(maxsize=1)
def _classroom_service():
    settings = Settings()
    creds = get_credentials(settings.google_client_secret_path, settings.google_token_path)
    return build("classroom", "v1", credentials=creds)


@tool
def list_courses() -> str:
    """List all active Google Classroom courses the authenticated user has access to."""
    svc = _classroom_service()
    response = svc.courses().list(courseStates=["ACTIVE"]).execute()
    courses = response.get("courses", [])
    if not courses:
        return "No active courses found."
    lines = [f"- [{c['id']}] {c.get('name', 'Unnamed')} — {c.get('section', '')}" for c in courses]
    return "Active courses:\n" + "\n".join(lines)


@tool
def list_students(course_id: str) -> str:
    """List all enrolled students in a Google Classroom course."""
    svc = _classroom_service()
    response = svc.courses().students().list(courseId=course_id).execute()
    students = response.get("students", [])
    if not students:
        return f"No students found in course {course_id}."
    lines = []
    for s in students:
        profile = s.get("profile", {})
        name = profile.get("name", {}).get("fullName", "Unknown")
        email = profile.get("emailAddress", "")
        lines.append(f"- [{s['userId']}] {name} <{email}>")
    return f"Students ({len(lines)}):\n" + "\n".join(lines)


@tool
def list_assignments(course_id: str) -> str:
    """List all coursework (assignments, quizzes) in a Google Classroom course."""
    svc = _classroom_service()
    response = svc.courses().courseWork().list(courseId=course_id).execute()
    items = response.get("courseWork", [])
    if not items:
        return f"No assignments found in course {course_id}."
    lines = [
        f"- [{cw['id']}] {cw.get('title', 'Untitled')} (max: {cw.get('maxPoints', 'N/A')} pts)"
        for cw in items
    ]
    return "Assignments:\n" + "\n".join(lines)


@tool
def get_submission_status(course_id: str, coursework_id: str) -> str:
    """Return submission state for every student in an assignment.
    States: NEW, CREATED, TURNED_IN, RETURNED, RECLAIMED_BY_STUDENT."""
    svc = _classroom_service()
    response = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id)
        .execute()
    )
    subs = response.get("studentSubmissions", [])
    if not subs:
        return "No submissions found."
    lines = [f"- [{s['userId']}] Submission {s['id']}: {s.get('state', 'UNKNOWN')}" for s in subs]
    return f"Submission status ({len(lines)} students):\n" + "\n".join(lines)


@tool
def get_submission(course_id: str, coursework_id: str, submission_id: str) -> str:
    """Fetch a single student submission including attached Drive file IDs."""
    svc = _classroom_service()
    sub = (
        svc.courses().courseWork().studentSubmissions()
        .get(courseId=course_id, courseWorkId=coursework_id, id=submission_id)
        .execute()
    )
    attachments = [
        a["driveFile"].get("id", "unknown")
        for a in sub.get("assignmentSubmission", {}).get("attachments", [])
        if "driveFile" in a
    ]
    return json.dumps({
        "submission_id": sub["id"],
        "student_id": sub["userId"],
        "state": sub.get("state"),
        "drive_file_ids": attachments,
        "late": sub.get("late", False),
    }, indent=2)
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_tools_classroom.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ta/tools/ tests/test_tools_classroom.py
git commit -m "feat: Google Classroom read tools"
```

---

## Task 5: Google Classroom Write Tools

**Files:**
- Modify: `ta/tools/classroom.py` (append write tools)
- Modify: `tests/test_tools_classroom.py` (append write tests)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_tools_classroom.py

class TestPostAnnouncement:
    def test_posts_when_confirmed(self):
        with patch("ta.tools.classroom.interrupt", return_value=True):
            with patch("ta.tools.classroom._classroom_service") as mock_svc:
                mock_svc.return_value.courses.return_value.announcements.return_value.create.return_value.execute.return_value = {"id": "ann1"}
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
        with patch("ta.tools.classroom.interrupt", return_value=True):
            with patch("ta.tools.classroom._classroom_service") as mock_svc:
                mock_svc.return_value.courses.return_value.courseWork.return_value.create.return_value.execute.return_value = {
                    "id": "cw99", "title": "HW1"
                }
                from ta.tools.classroom import create_assignment
                result = create_assignment.invoke({
                    "course_id": "123", "title": "HW1", "description": "Do the thing",
                    "max_points": 100.0, "due_date": "2026-06-01", "due_time": "23:59",
                    "materials_drive_ids": [],
                })
        assert "cw99" in result or "created" in result.lower()
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_tools_classroom.py::TestPostAnnouncement -v
```

- [ ] **Step 3: Append write tools to `ta/tools/classroom.py`**

```python
# Append to bottom of ta/tools/classroom.py

from langgraph.types import interrupt


@tool
def post_announcement(course_id: str, text: str) -> str:
    """Post a plain-text announcement to a Google Classroom course. Requires confirmation."""
    confirmed = interrupt({
        "action": "post_announcement",
        "details": f"Post announcement to course {course_id}:\n\n{text[:200]}{'...' if len(text) > 200 else ''}",
    })
    if not confirmed:
        return "Announcement posting cancelled."
    svc = _classroom_service()
    result = svc.courses().announcements().create(
        courseId=course_id, body={"text": text, "state": "PUBLISHED"}
    ).execute()
    return f"Announcement posted (id: {result['id']})."


@tool
def create_assignment(
    course_id: str,
    title: str,
    description: str,
    max_points: float,
    due_date: str,
    due_time: str,
    materials_drive_ids: list[str],
) -> str:
    """Create a new assignment in a Google Classroom course. Requires confirmation.
    due_date: YYYY-MM-DD format. due_time: HH:MM (24h)."""
    confirmed = interrupt({
        "action": "create_assignment",
        "details": f"Create assignment '{title}' in course {course_id}\n"
                   f"Max points: {max_points}, Due: {due_date} {due_time}",
    })
    if not confirmed:
        return "Assignment creation cancelled."
    year, month, day = map(int, due_date.split("-"))
    hour, minute = map(int, due_time.split(":"))
    body: dict = {
        "title": title, "description": description, "maxPoints": max_points,
        "workType": "ASSIGNMENT", "state": "PUBLISHED",
        "dueDate": {"year": year, "month": month, "day": day},
        "dueTime": {"hours": hour, "minutes": minute},
    }
    if materials_drive_ids:
        body["materials"] = [
            {"driveFile": {"driveFile": {"id": fid}, "shareMode": "VIEW"}}
            for fid in materials_drive_ids
        ]
    svc = _classroom_service()
    result = svc.courses().courseWork().create(courseId=course_id, body=body).execute()
    return f"Assignment created (id: {result['id']}, title: {result.get('title')})."


@tool
def create_material(
    course_id: str,
    title: str,
    description: str,
    drive_file_ids: list[str],
    youtube_urls: list[str],
    link_urls: list[str],
) -> str:
    """Post study materials (Drive files, YouTube, links) to a course. Requires confirmation."""
    confirmed = interrupt({
        "action": "create_material",
        "details": f"Post material '{title}' to course {course_id}",
    })
    if not confirmed:
        return "Material posting cancelled."
    materials = []
    for fid in drive_file_ids:
        materials.append({"driveFile": {"driveFile": {"id": fid}, "shareMode": "VIEW"}})
    for url in youtube_urls:
        video_id = url.split("v=")[-1].split("&")[0]
        materials.append({"youtubeVideo": {"id": video_id}})
    for url in link_urls:
        materials.append({"link": {"url": url}})
    svc = _classroom_service()
    result = svc.courses().courseWorkMaterials().create(
        courseId=course_id,
        body={"title": title, "description": description, "materials": materials, "state": "PUBLISHED"},
    ).execute()
    return f"Material posted (id: {result['id']})."
```

- [ ] **Step 4: Run all classroom tests**

```bash
uv run pytest tests/test_tools_classroom.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ta/tools/classroom.py tests/test_tools_classroom.py
git commit -m "feat: Classroom write tools with interrupt confirmation"
```

---

## Task 6: Google Drive & Docs Tools

**Files:**
- Create: `ta/tools/drive.py`, `ta/tools/docs.py`
- Test: `tests/test_tools_drive.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tools_drive.py
from unittest.mock import MagicMock, patch


class TestGetDriveFileText:
    def test_reads_google_doc(self):
        with patch("ta.tools.drive._drive_service") as mock_svc:
            mock_svc.return_value.files.return_value.get.return_value.execute.return_value = {
                "mimeType": "application/vnd.google-apps.document"
            }
            mock_svc.return_value.files.return_value.export_media.return_value.execute.return_value = b"Document content."
            from ta.tools.drive import get_drive_file_text
            result = get_drive_file_text.invoke({"file_id": "doc123"})
        assert "Document content" in result

    def test_reads_python_file(self):
        with patch("ta.tools.drive._drive_service") as mock_svc:
            mock_svc.return_value.files.return_value.get.return_value.execute.return_value = {
                "mimeType": "text/x-python"
            }
            mock_svc.return_value.files.return_value.get_media.return_value.execute.return_value = b"print('hello')"
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
            mock_svc.return_value.documents.return_value.get.return_value.execute.return_value = mock_doc
            from ta.tools.docs import get_doc_text
            result = get_doc_text.invoke({"document_id": "doc456"})
        assert "Hello" in result and "World" in result
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_tools_drive.py -v
```

- [ ] **Step 3: Create `ta/tools/drive.py`**

```python
# ta/tools/drive.py
import io
from functools import lru_cache

from googleapiclient.discovery import build
from langchain_core.tools import tool

from ta.config import Settings
from ta.google_auth import get_credentials

_GOOGLE_DOC_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
_TEXT_MIMES = {
    "text/plain", "text/x-python", "text/markdown",
    "text/x-markdown", "application/json", "text/html",
}


@lru_cache(maxsize=1)
def _drive_service():
    settings = Settings()
    creds = get_credentials(settings.google_client_secret_path, settings.google_token_path)
    return build("drive", "v3", credentials=creds)


@tool
def get_drive_file_text(file_id: str) -> str:
    """Download and return text content of a Google Drive file.
    Supports: Google Docs/Sheets/Slides (exported as text), Python/text/markdown files,
    PDFs (first 10 pages via pypdf)."""
    svc = _drive_service()
    meta = svc.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "")

    if mime in _GOOGLE_DOC_MIMES:
        data = svc.files().export_media(fileId=file_id, mimeType=_GOOGLE_DOC_MIMES[mime]).execute()
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)

    if mime in _TEXT_MIMES or mime.startswith("text/"):
        data = svc.files().get_media(fileId=file_id).execute()
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)

    if mime == "application/pdf":
        from pypdf import PdfReader
        data = svc.files().get_media(fileId=file_id).execute()
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(p.extract_text() or "" for p in reader.pages[:10])

    return f"[Cannot read file type: {mime}. File name: {meta.get('name', 'unknown')}]"


@tool
def upload_file_to_drive(local_path: str, parent_folder_id: str, filename: str) -> str:
    """Upload a local file to a Google Drive folder. Returns the new file ID."""
    from googleapiclient.http import MediaFileUpload
    svc = _drive_service()
    result = svc.files().create(
        body={"name": filename, "parents": [parent_folder_id]},
        media_body=MediaFileUpload(local_path, resumable=True),
        fields="id",
    ).execute()
    return f"Uploaded '{filename}' to Drive (id: {result['id']})."
```

- [ ] **Step 4: Create `ta/tools/docs.py`**

```python
# ta/tools/docs.py
from functools import lru_cache

from googleapiclient.discovery import build
from langchain_core.tools import tool
from langgraph.types import interrupt

from ta.config import Settings
from ta.google_auth import get_credentials


@lru_cache(maxsize=1)
def _docs_service():
    settings = Settings()
    creds = get_credentials(settings.google_client_secret_path, settings.google_token_path)
    return build("docs", "v1", credentials=creds)


@tool
def get_doc_text(document_id: str) -> str:
    """Return the full plain text content of a Google Docs document."""
    svc = _docs_service()
    doc = svc.documents().get(documentId=document_id).execute()
    texts = []
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            for pe in element["paragraph"].get("elements", []):
                if "textRun" in pe:
                    texts.append(pe["textRun"].get("content", ""))
    return "".join(texts)


@tool
def add_doc_comment(document_id: str, anchor_text: str, comment_text: str) -> str:
    """Add a comment to a Google Docs document anchored to a specific text passage.
    Requires confirmation. anchor_text must be an exact substring of the document."""
    confirmed = interrupt({
        "action": "add_doc_comment",
        "details": (
            f"Add comment to doc {document_id}\n"
            f"Anchor: '{anchor_text[:80]}'\nComment: '{comment_text[:120]}'"
        ),
    })
    if not confirmed:
        return "Comment cancelled."

    svc = _docs_service()
    doc = svc.documents().get(documentId=document_id).execute()
    char_offset = 0
    anchor_start = None
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            for pe in element["paragraph"].get("elements", []):
                if "textRun" in pe:
                    run_text = pe["textRun"].get("content", "")
                    idx = run_text.find(anchor_text)
                    if idx != -1 and anchor_start is None:
                        anchor_start = char_offset + idx
                    char_offset += len(run_text)

    if anchor_start is None:
        return f"Anchor text '{anchor_text[:40]}' not found in document. Comment not added."

    from ta.tools.drive import _drive_service
    drive_svc = _drive_service()
    anchor_end = anchor_start + len(anchor_text)
    try:
        result = drive_svc.comments().create(
            fileId=document_id,
            body={
                "content": comment_text,
                "anchor": f'{{"r": [{{"startIndex": {anchor_start}, "endIndex": {anchor_end}}}]}}',
            },
            fields="id",
        ).execute()
        return f"Comment added (id: {result['id']})."
    except Exception as exc:
        return f"Comment posting note: {exc}"
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_tools_drive.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ta/tools/drive.py ta/tools/docs.py tests/test_tools_drive.py
git commit -m "feat: Drive file reader and Docs inline comment tools"
```

---

## Task 7: AI Grading Tools

**Files:**
- Create: `ta/tools/grading.py`
- Test: `tests/test_tools_grading.py`

- [ ] **Step 1: Write failing tests**

```python
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
            "  - name: Correctness\n    weight: 0.5\n    max_points: 50\n    description: Is it correct?\n"
            "  - name: Style\n    weight: 0.5\n    max_points: 50\n    description: Is it clean?\n"
        )
        from ta.tools.grading import load_rubric
        parsed = json.loads(load_rubric.invoke({"rubric_path": str(f)}))
        assert len(parsed) == 2 and parsed[0]["name"] == "Correctness"

    def test_error_on_missing_file(self, tmp_path):
        from ta.tools.grading import load_rubric
        result = load_rubric.invoke({"rubric_path": str(tmp_path / "missing.yaml")})
        assert "error" in result.lower() or "not found" in result.lower()
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_tools_grading.py -v
```

- [ ] **Step 3: Create `ta/tools/grading.py`**

```python
# ta/tools/grading.py
import json
import re
from functools import lru_cache
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.types import interrupt

from ta.config import Settings

GRADING_SYSTEM_PROMPT = """You are an expert teaching assistant grading student submissions.
Evaluate the submission against the provided rubric criteria.
Return ONLY valid JSON with this exact schema:
{
  "criteria_scores": {"CriteriaName": score_float},
  "score": total_float,
  "max_score": max_float,
  "feedback_text": "narrative feedback for the student",
  "inline_comments": []
}
Do not include any text outside the JSON object."""


@lru_cache(maxsize=1)
def _get_llm():
    settings = Settings()
    return ChatNVIDIA(model=settings.nvidia_model, api_key=settings.nvidia_api_key)


def _extract_json(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    return match.group(1).strip() if match else text.strip()


@tool
def load_rubric(rubric_path: str) -> str:
    """Load a grading rubric from a YAML file. Returns a JSON array of criteria objects."""
    path = Path(rubric_path)
    if not path.exists():
        return f"Error: Rubric file not found at '{rubric_path}'."
    with path.open() as f:
        data = yaml.safe_load(f)
    return json.dumps(data.get("criteria", []), indent=2)


@tool
def analyze_submission(submission_text: str, rubric_json: str, assignment_type: str) -> str:
    """Use the NVIDIA LLM to evaluate a student submission against a rubric.
    assignment_type: 'code' | 'report' | 'documentation' | 'diagram'
    Returns a JSON GradeResult."""
    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=GRADING_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Assignment type: {assignment_type}\n\n"
            f"Rubric:\n{rubric_json}\n\n"
            f"Submission:\n```\n{submission_text[:8000]}\n```\n\n"
            "Return only the JSON grade result."
        )),
    ])
    parsed = json.loads(_extract_json(response.content))
    return json.dumps(parsed, indent=2)


@tool
def post_grade(
    course_id: str, coursework_id: str, student_id: str, score: float, private_comment: str
) -> str:
    """Post a numeric grade and private comment to a student's Classroom submission.
    Requires instructor confirmation."""
    confirmed = interrupt({
        "action": "post_grade",
        "details": (
            f"Post grade {score} pts to student {student_id}\n"
            f"Assignment: {coursework_id} in course {course_id}\n"
            f"Comment: {private_comment[:120]}"
        ),
    })
    if not confirmed:
        return f"Grade for student {student_id} cancelled."

    from googleapiclient.discovery import build
    from ta.google_auth import get_credentials
    settings = Settings()
    creds = get_credentials(settings.google_client_secret_path, settings.google_token_path)
    svc = build("classroom", "v1", credentials=creds)

    subs = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id, userId=student_id)
        .execute()
    )
    submission_id = subs["studentSubmissions"][0]["id"]
    svc.courses().courseWork().studentSubmissions().patch(
        courseId=course_id, courseWorkId=coursework_id, id=submission_id,
        updateMask="assignedGrade,draftGrade",
        body={"assignedGrade": score, "draftGrade": score},
    ).execute()
    svc.courses().courseWork().studentSubmissions().return_(
        courseId=course_id, courseWorkId=coursework_id, body={"ids": [submission_id]}
    ).execute()
    return f"Grade {score} posted for student {student_id} (submission {submission_id})."


@tool
def post_private_comment(
    course_id: str, coursework_id: str, submission_id: str, comment_text: str
) -> str:
    """Add a private comment to a student's Classroom submission. Requires confirmation."""
    confirmed = interrupt({
        "action": "post_private_comment",
        "details": f"Add private comment to submission {submission_id}:\n{comment_text[:200]}",
    })
    if not confirmed:
        return "Private comment cancelled."
    from googleapiclient.discovery import build
    from ta.google_auth import get_credentials
    settings = Settings()
    creds = get_credentials(settings.google_client_secret_path, settings.google_token_path)
    svc = build("classroom", "v1", credentials=creds)
    svc.courses().courseWork().studentSubmissions().modifyAttachments(
        courseId=course_id, courseWorkId=coursework_id, id=submission_id,
        body={"addAttachments": []},
    ).execute()
    return f"Private comment added to submission {submission_id}."


@tool
def batch_grade_assignment(
    course_id: str, coursework_id: str, rubric_path: str, assignment_type: str
) -> str:
    """Grade ALL TURNED_IN submissions for an assignment using a YAML rubric.
    Fetches each submission's Drive files and analyzes with NVIDIA LLM.
    Returns a summary table. Grades are NOT posted — call post_grade for each student."""
    from ta.tools.classroom import _classroom_service
    from ta.tools.drive import get_drive_file_text

    rubric_json = load_rubric.invoke({"rubric_path": rubric_path})
    if rubric_json.startswith("Error"):
        return rubric_json

    svc = _classroom_service()
    subs_response = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id)
        .execute()
    )
    turned_in = [
        s for s in subs_response.get("studentSubmissions", [])
        if s.get("state") == "TURNED_IN"
    ]
    if not turned_in:
        return "No TURNED_IN submissions found."

    lines = []
    for sub in turned_in:
        file_ids = [
            a["driveFile"]["id"]
            for a in sub.get("assignmentSubmission", {}).get("attachments", [])
            if "driveFile" in a
        ]
        submission_text = "\n".join(
            get_drive_file_text.invoke({"file_id": fid}) for fid in file_ids
        )
        if not submission_text.strip():
            lines.append(f"- Student {sub['userId']}: No readable file attached — skipped.")
            continue
        try:
            grade = json.loads(analyze_submission.invoke({
                "submission_text": submission_text,
                "rubric_json": rubric_json,
                "assignment_type": assignment_type,
            }))
            lines.append(
                f"- Student {sub['userId']}: {grade['score']}/{grade['max_score']} pts\n"
                f"  {grade['feedback_text'][:100]}..."
            )
        except Exception as exc:
            lines.append(f"- Student {sub['userId']}: Grading failed — {exc}")

    return (
        f"Grading complete ({len(turned_in)} submissions):\n"
        + "\n".join(lines)
        + "\n\nCall post_grade for each student to publish grades."
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_tools_grading.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ta/tools/grading.py tests/test_tools_grading.py
git commit -m "feat: AI grading tools with NVIDIA LLM analysis and batch grading"
```

---

## Task 8: Assemble Tools & Build Agent

**Files:**
- Modify: `ta/tools/__init__.py`
- Create: `ta/agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_agent.py -v
```

- [ ] **Step 3: Replace `ta/tools/__init__.py`**

```python
# ta/tools/__init__.py
from ta.tools.classroom import (
    create_assignment,
    create_material,
    get_submission,
    get_submission_status,
    list_assignments,
    list_courses,
    list_students,
    post_announcement,
)
from ta.tools.docs import add_doc_comment, get_doc_text
from ta.tools.drive import get_drive_file_text, upload_file_to_drive
from ta.tools.grading import (
    analyze_submission,
    batch_grade_assignment,
    load_rubric,
    post_grade,
    post_private_comment,
)

ALL_TOOLS = [
    # Classroom — read
    list_courses,
    list_students,
    list_assignments,
    get_submission_status,
    get_submission,
    # Classroom — write (confirmation required)
    post_announcement,
    create_assignment,
    create_material,
    # Grading
    load_rubric,
    analyze_submission,
    batch_grade_assignment,
    post_grade,
    post_private_comment,
    # Drive
    get_drive_file_text,
    upload_file_to_drive,
    # Docs
    get_doc_text,
    add_doc_comment,
]
```

- [ ] **Step 4: Create `ta/agent.py`**

```python
# ta/agent.py
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from ta.config import Settings
from ta.state import TAState
from ta.tools import ALL_TOOLS

SYSTEM_PROMPT = """You are a Teaching Assistant (TA) agent for Google Classroom.

CAPABILITIES:
- Post announcements, assignments, and study materials to courses
- Check student submission status and fetch submitted work from Drive
- Grade submissions using YAML rubrics with NVIDIA AI analysis (code, reports, docs, diagrams)
- Post grades and feedback back to students

WORKFLOW GUIDELINES:
1. Identify the active course before performing operations. Ask for course ID if unclear.
2. DESTRUCTIVE actions (posting grades, announcements, creating assignments) automatically pause
   and ask the instructor for confirmation before executing.
3. Grading workflow: load_rubric → batch_grade_assignment → review summary → post_grade per student.
4. Use get_submission to get Drive file IDs, then get_drive_file_text to read content.
5. Show student IDs alongside names in all roster and status outputs.
"""


def build_agent(settings: Settings):
    """Build and compile the LangGraph ReAct TA agent."""
    llm = ChatNVIDIA(model=settings.nvidia_model, api_key=settings.nvidia_api_key)
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        state_schema=TAState,
        prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_agent.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add ta/tools/__init__.py ta/agent.py tests/test_agent.py
git commit -m "feat: assemble ALL_TOOLS and compile LangGraph ReAct agent"
```

---

## Task 9: CLI REPL & Entrypoint

**Files:**
- Create: `ta/cli.py`
- Modify: `main.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from langgraph.types import Command


class TestRunRepl:
    def test_exits_without_calling_graph(self):
        mock_graph = MagicMock()
        with patch("builtins.input", side_effect=["exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        mock_graph.stream.assert_not_called()

    def test_sends_user_message_to_graph(self):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([{"messages": [AIMessage(content="Courses listed!")]}])
        with patch("builtins.input", side_effect=["list courses", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        state_input = mock_graph.stream.call_args[0][0]
        assert state_input["messages"][0].content == "list courses"

    def test_interrupt_yes_resumes_with_true(self):
        mock_graph = MagicMock()
        interrupt_chunk = {"__interrupt__": [MagicMock(value={"action": "post_announcement", "details": "Post?"})]}
        resume_chunk = {"messages": [AIMessage(content="Posted.")]}
        mock_graph.stream.side_effect = [iter([interrupt_chunk]), iter([resume_chunk])]
        with patch("builtins.input", side_effect=["post it", "y", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume is True

    def test_interrupt_no_resumes_with_false(self):
        mock_graph = MagicMock()
        mock_graph.stream.side_effect = [
            iter([{"__interrupt__": [MagicMock(value={"action": "post_grade", "details": "Post?"})]}]),
            iter([{"messages": [AIMessage(content="Cancelled.")]}]),
        ]
        with patch("builtins.input", side_effect=["grade", "n", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume is False
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 3: Create `ta/cli.py`**

```python
# ta/cli.py
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def _print_ai(content: str) -> None:
    console.print(Panel(Text(content, style="white"), title="[bold blue]TA Agent[/bold blue]", border_style="blue"))


def _print_chunk(chunk: dict) -> None:
    for msg in chunk.get("messages", []):
        content = getattr(msg, "content", None)
        msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
        if msg_type in ("ai", "assistant") and content and isinstance(content, str) and content.strip():
            _print_ai(content)


def run_repl(graph, config: dict) -> None:
    """Run the interactive CLI REPL for the TA agent."""
    console.print(Panel(
        "[bold green]Classroom TA Agent[/bold green] ready.\n"
        "Type your request and press Enter. Type [bold]exit[/bold] to quit.\n\n"
        "[dim]Examples:[/dim]\n"
        "  List my courses\n"
        "  Grade all submissions for assignment 987 using rubric rubrics/hw1.yaml\n"
        "  Post announcement: 'Midterm next Friday at 10am'",
        title="Welcome", border_style="green",
    ))

    while True:
        try:
            user_input = input("\n[You]: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break

        try:
            for chunk in graph.stream({"messages": [HumanMessage(content=user_input)]}, config, stream_mode="values"):
                if "__interrupt__" in chunk:
                    data = chunk["__interrupt__"][0].value
                    console.print(f"\n[bold yellow]⚠ CONFIRMATION REQUIRED[/bold yellow]")
                    console.print(f"[yellow]Action:[/yellow] {data.get('action', '')}")
                    console.print(f"[yellow]Details:[/yellow]\n{data.get('details', '')}")
                    confirmed = input("\nProceed? [y/N]: ").strip().lower() == "y"
                    for resume_chunk in graph.stream(Command(resume=confirmed), config, stream_mode="values"):
                        _print_chunk(resume_chunk)
                else:
                    _print_chunk(chunk)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
```

- [ ] **Step 4: Replace `main.py`**

```python
# main.py
import uuid

from ta.agent import build_agent
from ta.cli import run_repl
from ta.config import Settings
from ta.google_auth import get_credentials


def main() -> None:
    settings = Settings()
    get_credentials(settings.google_client_secret_path, settings.google_token_path)
    graph = build_agent(settings)
    run_repl(graph, {"configurable": {"thread_id": str(uuid.uuid4())}})


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run all tests**

```bash
uv run pytest -v
```

Expected: All tests across all modules PASS.

- [ ] **Step 6: Run ruff**

```bash
uv run ruff check ta/ tests/ main.py
```

Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add ta/cli.py main.py tests/test_cli.py
git commit -m "feat: CLI REPL with interrupt confirmation and rich output"
```

---

## Task 10: Documentation & First Run

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Classroom TA Agent

AI Teaching Assistant for Google Classroom, powered by LangGraph + NVIDIA NIM.

## Features
- Post announcements, assignments, and study materials
- Grade submissions with AI rubric analysis (code, reports, documentation, diagrams)
- Add inline feedback to Google Docs submissions
- All write actions require explicit instructor confirmation

## Setup

### 1. Install
```bash
uv sync
```

### 2. Google credentials
Follow the Prerequisites in the implementation plan. Place `client_secret.json` at `credentials/client_secret.json`.

### 3. Environment
```bash
cp .env.example .env   # then add your NVIDIA API key from build.nvidia.com
```

### 4. Run
```bash
uv run python main.py
```
First run opens a browser for Google OAuth2. Token cached for future runs.

## Rubric format
```yaml
criteria:
  - name: Correctness
    weight: 0.40
    max_points: 40
    description: Does the code produce correct output?
```
```

- [ ] **Step 2: Final commit**

```bash
git add README.md
git commit -m "docs: README with setup guide and rubric format"
```

---

## Verification

### Automated (no real APIs needed)

```bash
uv run pytest -v --tb=short
```

Expected: All 20+ tests pass across `test_auth`, `test_state`, `test_tools_classroom`, `test_tools_grading`, `test_tools_drive`, `test_agent`, `test_cli`.

```bash
uv run ruff check ta/ tests/ main.py
```

Expected: No errors.

### Manual end-to-end (requires real credentials)

1. `uv run python main.py` → browser opens for OAuth2 → authorize → REPL starts
2. `list my courses` → real Google Classroom course list appears
3. `list students in course [id]` → real student roster
4. `show submission status for assignment [id] in course [id]` → TURNED_IN / NEW states
5. `post announcement 'Test from TA agent' to course [id]` → confirmation prompt → `y` → appears in Classroom
6. `grade all submissions for assignment [id] in course [id] using rubric rubrics/example_rubric.yaml` → LLM analysis runs → summary shown
7. `exit` → clean shutdown
