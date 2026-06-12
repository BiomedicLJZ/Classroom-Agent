# Improvements v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pagination everywhere, real Drive-comment feedback, persistent SQLite memory, retries, token-revocation recovery, DRAFT-default + scheduled posts, xlsx grade import, live Markdown rendering with prompt_toolkit input and /think toggle, uv lockfile + CI.

**Architecture:** All Classroom list calls flow through one `_collect_pages` helper. Grade feedback reuses the Drive `comments().create` mechanism already proven in `add_doc_comment`. The CLI's `StreamRenderer` swaps raw answer printing for a `rich.live.Live(Markdown(...))` region; `run_repl` takes a `make_graph(thinking)` factory so `/think` rebuilds the agent against the same SQLite checkpointer and thread.

**Tech Stack:** Existing stack + `langgraph-checkpoint-sqlite`, `tenacity`, `prompt-toolkit`. `zoneinfo` (stdlib) for scheduling. GitHub Actions + `astral-sh/setup-uv`.

**Spec:** `docs/superpowers/specs/2026-06-12-improvements-v2-design.md`

**Runner:** `.venv\Scripts\python -m pytest <path> -v` / `.venv\Scripts\python -m ruff check .`
**Deps:** add with `uv add <pkg>` (updates pyproject + uv.lock + syncs the venv in one step).

---

### Task 1: Pagination helper + classroom list tools

**Files:**
- Modify: `ta/tools/classroom.py`
- Test: `tests/test_classroom_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classroom_admin.py`:

```python
class TestPagination:
    def test_list_students_follows_page_tokens(self):
        svc = _service_mock()
        list_call = svc.courses().students().list
        list_call.return_value.execute.side_effect = [
            {
                "students": [{
                    "userId": "s1",
                    "profile": {"name": {"fullName": "Ana"}, "emailAddress": "a@x.mx"},
                }],
                "nextPageToken": "tok2",
            },
            {
                "students": [{
                    "userId": "s2",
                    "profile": {"name": {"fullName": "Beto"}, "emailAddress": "b@x.mx"},
                }],
            },
        ]
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import list_students
            result = list_students.func(course_id="c1")
        assert "Ana" in result and "Beto" in result
        assert list_call.call_count == 2
        assert list_call.call_args_list[1].kwargs["pageToken"] == "tok2"

    def test_list_announcements_follows_page_tokens(self):
        svc = _service_mock()
        list_call = svc.courses().announcements().list
        list_call.return_value.execute.side_effect = [
            {"announcements": [{"id": "a1", "state": "PUBLISHED", "text": "One"}],
             "nextPageToken": "t2"},
            {"announcements": [{"id": "a2", "state": "DRAFT", "text": "Two"}]},
        ]
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import list_announcements
            result = list_announcements.func(course_id="c1")
        assert "a1" in result and "a2" in result
        assert list_call.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py::TestPagination -v`
Expected: FAIL — `list_call.call_count == 2` is 1 (single page fetched today).

- [ ] **Step 3: Implement**

In `ta/tools/classroom.py`, add below `_classroom_service`:

```python
def _collect_pages(make_request, items_key: str) -> list:
    """Follow nextPageToken until exhausted. make_request(page_token) must return
    an executable API request for that page."""
    items: list = []
    token = None
    while True:
        response = make_request(token).execute(num_retries=3)
        items.extend(response.get(items_key, []))
        token = response.get("nextPageToken")
        if not token:
            return items
```

Then replace the single-page fetches (keep each tool's formatting/empty-message
logic identical, only the fetch changes):

`list_students` — replace
```python
    response = svc.courses().students().list(courseId=course_id).execute()
    students = response.get("students", [])
```
with
```python
    students = _collect_pages(
        lambda tok: svc.courses().students().list(courseId=course_id, pageToken=tok),
        "students",
    )
```

`list_assignments` — replace the `courseWork().list(...).execute()` +
`response.get("courseWork", [])` pair with
```python
    items = _collect_pages(
        lambda tok: svc.courses().courseWork().list(courseId=course_id, pageToken=tok),
        "courseWork",
    )
```

`get_submission_status` — replace the `studentSubmissions().list(...).execute()` +
`response.get("studentSubmissions", [])` pair with
```python
    subs = _collect_pages(
        lambda tok: svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id, pageToken=tok),
        "studentSubmissions",
    )
```

`list_announcements` — replace the try/except fetch body with
```python
    try:
        items = _collect_pages(
            lambda tok: svc.courses().announcements().list(
                courseId=course_id, orderBy="updateTime desc", pageSize=50, pageToken=tok
            ),
            "announcements",
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
```
(and drop the now-unused `response =` / `items = response.get(...)` lines)

`list_materials` — same shape:
```python
    try:
        items = _collect_pages(
            lambda tok: svc.courses().courseWorkMaterials().list(
                courseId=course_id, pageSize=50, pageToken=tok
            ),
            "courseWorkMaterial",
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
```

`list_invitations` — locate its fetch (`svc.invitations().list(courseId=...)`)
and wrap identically with items_key `"invitations"`:
```python
    invitations = _collect_pages(
        lambda tok: svc.invitations().list(courseId=course_id, pageToken=tok),
        "invitations",
    )
```

- [ ] **Step 4: Run tests to verify they pass (full admin + tools files)**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py tests/test_tools_classroom.py -v`
Expected: ALL PASS (existing single-page mocks return no nextPageToken → loop exits after one page).

- [ ] **Step 5: Commit**

```bash
git add ta/tools/classroom.py tests/test_classroom_admin.py
git commit -m "feat: paginate all classroom list calls"
```

---

### Task 2: Pagination in grading fetches

**Files:**
- Modify: `ta/tools/grading.py`
- Test: existing `tests/test_grading.py` + `tests/test_tools_grading.py` (safety net)

- [ ] **Step 1: Refactor `export_grades` fetches**

Replace:
```python
    roster = svc.courses().students().list(courseId=course_id).execute().get("students", [])
    coursework = (
        svc.courses().courseWork().list(courseId=course_id).execute().get("courseWork", [])
    )
```
with:
```python
    roster = _collect_pages(
        lambda tok: svc.courses().students().list(courseId=course_id, pageToken=tok),
        "students",
    )
    coursework = _collect_pages(
        lambda tok: svc.courses().courseWork().list(courseId=course_id, pageToken=tok),
        "courseWork",
    )
```
and extend the function's lazy import line
`from ta.tools.classroom import _classroom_service` to
`from ta.tools.classroom import _classroom_service, _collect_pages`.

Inside its per-coursework loop replace:
```python
        subs = (
            svc.courses().courseWork().studentSubmissions()
            .list(courseId=course_id, courseWorkId=cw["id"])
            .execute()
            .get("studentSubmissions", [])
        )
```
with:
```python
        subs = _collect_pages(
            lambda tok, cw_id=cw["id"]: svc.courses().courseWork().studentSubmissions()
            .list(courseId=course_id, courseWorkId=cw_id, pageToken=tok),
            "studentSubmissions",
        )
```

- [ ] **Step 2: Refactor `batch_grade_assignment` fetch**

Extend its lazy import `from ta.tools.classroom import _classroom_service` to
include `_collect_pages`, then replace:
```python
    subs_response = (
        svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id)
        .execute()
    )
    turned_in = [
        s for s in subs_response.get("studentSubmissions", [])
        if s.get("state") == "TURNED_IN"
    ]
```
with:
```python
    all_subs = _collect_pages(
        lambda tok: svc.courses().courseWork().studentSubmissions()
        .list(courseId=course_id, courseWorkId=coursework_id, pageToken=tok),
        "studentSubmissions",
    )
    turned_in = [s for s in all_subs if s.get("state") == "TURNED_IN"]
```

- [ ] **Step 3: Run the grading test files**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py tests/test_tools_grading.py -v`
Expected: ALL PASS (mocks have no nextPageToken → single iteration).

- [ ] **Step 4: Commit**

```bash
git add ta/tools/grading.py
git commit -m "feat: paginate grading roster/coursework/submission fetches"
```

---

### Task 3: Real feedback via Drive; remove phantom post_private_comment

**Files:**
- Modify: `ta/tools/grading.py`, `ta/tools/__init__.py`, `ta/agent.py`, `tests/test_agent.py`
- Test: `tests/test_grading.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_grading.py`:

```python
class TestPostGradeFeedback:
    def _svc_with_submission(self, with_file=True):
        sub = {"id": "sub1", "userId": "s1"}
        if with_file:
            sub["assignmentSubmission"] = {
                "attachments": [{"driveFile": {"id": "file9"}}]
            }
        svc = MagicMock()
        (svc.courses().courseWork().studentSubmissions()
         .list().execute.return_value) = {"studentSubmissions": [sub]}
        return svc

    def test_feedback_posted_to_drive_file(self):
        svc = self._svc_with_submission(with_file=True)
        drive = MagicMock()
        with patch("ta.tools.grading.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc), \
             patch("ta.tools.drive._drive_service", return_value=drive):
            from ta.tools.grading import post_grade
            result = post_grade.func(
                course_id="c1", coursework_id="w1", student_id="s1",
                score=9.0, feedback="Buen trabajo, revisa la sección 2.",
            )
        kwargs = drive.comments().create.call_args.kwargs
        assert kwargs["fileId"] == "file9"
        assert kwargs["body"]["content"] == "Buen trabajo, revisa la sección 2."
        assert "Feedback posted" in result

    def test_no_drive_file_reports_honestly(self):
        svc = self._svc_with_submission(with_file=False)
        drive = MagicMock()
        with patch("ta.tools.grading.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc), \
             patch("ta.tools.drive._drive_service", return_value=drive):
            from ta.tools.grading import post_grade
            result = post_grade.func(
                course_id="c1", coursework_id="w1", student_id="s1",
                score=9.0, feedback="Texto de feedback",
            )
        drive.comments().create.assert_not_called()
        assert "NOT delivered" in result
        assert "Texto de feedback" in result

    def test_post_private_comment_removed(self):
        from ta.tools import ALL_TOOLS
        assert "post_private_comment" not in [t.name for t in ALL_TOOLS]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py::TestPostGradeFeedback -v`
Expected: first two FAIL (old post_grade signature has `private_comment`, no Drive
delivery), third FAILS (tool still registered).

- [ ] **Step 3: Implement in `ta/tools/grading.py`**

a) Replace the entire `post_grade` function with:

```python
def _deliver_feedback(submission: dict, feedback: str) -> str:
    """Post feedback as a comment on the first Drive file of a submission."""
    file_ids = [
        a["driveFile"]["id"]
        for a in submission.get("assignmentSubmission", {}).get("attachments", [])
        if "driveFile" in a
    ]
    if not file_ids:
        return f"Feedback NOT delivered (no Drive file attached); deliver manually:\n{feedback}"
    from ta.tools.drive import _drive_service
    drive_svc = _drive_service(get_active_account())
    try:
        drive_svc.comments().create(
            fileId=file_ids[0], body={"content": feedback}, fields="id"
        ).execute(num_retries=3)
    except Exception as exc:
        return f"Feedback NOT delivered ({exc}); deliver manually:\n{feedback}"
    return "Feedback posted as a comment on the submitted Drive file."


def _post_one_grade(
    svc, course_id: str, coursework_id: str, student_id: str, score: float, feedback: str
) -> str:
    """Patch grade + return submission + deliver feedback. Shared by post_grade
    and import_grades — caller is responsible for the confirmation gate."""
    from ta.tools.classroom import _collect_pages
    subs = _collect_pages(
        lambda tok: svc.courses().courseWork().studentSubmissions().list(
            courseId=course_id, courseWorkId=coursework_id,
            userId=student_id, pageToken=tok,
        ),
        "studentSubmissions",
    )
    if not subs:
        return f"No submission found for student {student_id}."
    submission = subs[0]
    submission_id = submission["id"]
    svc.courses().courseWork().studentSubmissions().patch(
        courseId=course_id, courseWorkId=coursework_id, id=submission_id,
        updateMask="assignedGrade,draftGrade",
        body={"assignedGrade": score, "draftGrade": score},
    ).execute(num_retries=3)
    svc.courses().courseWork().studentSubmissions().return_(
        courseId=course_id, courseWorkId=coursework_id, body={"ids": [submission_id]}
    ).execute(num_retries=3)
    msg = f"Grade {score} posted for student {student_id} (submission {submission_id})."
    if feedback:
        msg += " " + _deliver_feedback(submission, feedback)
    return msg


@tool
def post_grade(
    course_id: str, coursework_id: str, student_id: str, score: float, feedback: str = ""
) -> str:
    """Post a numeric grade to a student's Classroom submission. feedback (optional)
    is delivered as a comment on the student's submitted Drive file — the Classroom
    API has no private comments. If the submission has no Drive attachment, the
    feedback is returned for manual delivery. Requires instructor confirmation."""
    details = (
        f"Post grade {score} pts to student {student_id}\n"
        f"Assignment: {coursework_id} in course {course_id}"
    )
    if feedback:
        details += f"\n\nFeedback (goes to the submitted Drive file):\n{feedback}"
    confirmed = interrupt({"action": "post_grade", "details": details})
    if not confirmed:
        return f"Grade for student {student_id} cancelled."
    from ta.tools.classroom import _classroom_service
    svc = _classroom_service(get_active_account())
    return _post_one_grade(svc, course_id, coursework_id, student_id, score, feedback)
```

b) Delete the entire `post_private_comment` function.

c) The old `post_grade` imported `build`/`get_credentials` inside the function —
those go away with it. `batch_grade_assignment` uses `_classroom_service`, so
nothing else needs the inline `build` import.

- [ ] **Step 4: Deregister + prompt note**

In `ta/tools/__init__.py`: remove `post_private_comment` from the grading import
block and from `ALL_TOOLS`.

In `ta/agent.py` `SYSTEM_PROMPT`, replace:
```
NOTE: the Classroom API has no public comments on posts. For "comment on an
assignment" requests, offer post_private_comment per student or an announcement
referencing the assignment.
```
with:
```
NOTE: the Classroom API has no public comments on posts and no private comments.
Grading feedback is delivered as a comment on the student's submitted Drive file
via post_grade(feedback=...). For "comment on an assignment" requests, offer that
or an announcement referencing the assignment.
```

In `tests/test_agent.py`, change `test_minimum_tool_count` to `assert len(ALL_TOOLS) >= 42`
(one tool removed; Task 8 restores 43).

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py tests/test_agent.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ta/tools/grading.py ta/tools/__init__.py ta/agent.py tests/test_grading.py tests/test_agent.py
git commit -m "feat: deliver grade feedback via Drive comments, drop phantom private-comment tool"
```

---

### Task 4: Persistent SQLite memory

**Files:**
- Modify: `ta/agent.py`, `main.py`, `.gitignore`, `pyproject.toml` (via uv)
- Test: `tests/test_agent.py`

- [ ] **Step 1: Add the dependency**

Run: `uv add langgraph-checkpoint-sqlite`
Expected: pyproject + uv.lock updated, package installed into `.venv`.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_agent.py` inside `TestBuildAgent`:

```python
    def test_build_agent_accepts_injected_checkpointer(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        fake_cp = MagicMock()
        with patch("ta.agent.ChatNVIDIA"), \
             patch("ta.agent.create_deep_agent") as mock_create:
            from ta.agent import build_agent
            from ta.config import Settings
            build_agent(Settings(), checkpointer=fake_cp)
            assert mock_create.call_args.kwargs["checkpointer"] is fake_cp

    def test_build_agent_defaults_to_sqlite(self, monkeypatch, tmp_path):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.chdir(tmp_path)  # checkpoints.db lands in tmp, not the repo
        with patch("ta.agent.ChatNVIDIA"), \
             patch("ta.agent.create_deep_agent") as mock_create:
            from ta.agent import build_agent
            from ta.config import Settings
            build_agent(Settings())
            from langgraph.checkpoint.sqlite import SqliteSaver
            assert isinstance(mock_create.call_args.kwargs["checkpointer"], SqliteSaver)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py -v -k "checkpointer or sqlite"`
Expected: FAIL — `build_agent() got an unexpected keyword argument 'checkpointer'`.

- [ ] **Step 4: Implement**

`ta/agent.py`:
- Remove `from langgraph.checkpoint.memory import InMemorySaver` (line 4).
- Change `def build_agent(settings: Settings):` to
  `def build_agent(settings: Settings, checkpointer=None):` and add at the top of
  the function body:

```python
    if checkpointer is None:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
        checkpointer = SqliteSaver(
            sqlite3.connect("checkpoints.db", check_same_thread=False)
        )
```
- In the `create_deep_agent(...)` call replace `checkpointer=InMemorySaver(),`
  with `checkpointer=checkpointer,`.

`main.py` — replace the whole file with:

```python
# main.py
import argparse
from datetime import date

from ta.agent import build_agent
from ta.cli import run_repl
from ta.config import Settings
from ta.google_auth import get_credentials


def main() -> None:
    parser = argparse.ArgumentParser(description="Classroom TA Agent")
    parser.add_argument(
        "--thread",
        default=f"cli-{date.today().isoformat()}",
        help="Conversation thread id (default: one per day, resumes within the day)",
    )
    args = parser.parse_args()

    settings = Settings()
    get_credentials("cugdl")
    graph = build_agent(settings)
    run_repl(graph, {"configurable": {"thread_id": args.thread}})


if __name__ == "__main__":
    main()
```
(Task 9 reworks main.py again for the `/think` factory.)

`.gitignore`: run `Add-Content .gitignore "checkpoints.db"`

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ta/agent.py main.py .gitignore pyproject.toml uv.lock tests/test_agent.py
git commit -m "feat: persistent sqlite conversation memory with daily threads"
```

---

### Task 5: Retries with tenacity

**Files:**
- Modify: `ta/tools/grading.py`, `pyproject.toml` (via uv)
- Test: `tests/test_grading.py`

- [ ] **Step 1: Add the dependency**

Run: `uv add tenacity`

- [ ] **Step 2: Write the failing test**

Append to `tests/test_grading.py` inside `TestGradingLLM`:

```python
    def test_analyze_submission_retries_on_transient_failure(self):
        import tenacity

        from ta.tools import grading
        grade_json = (
            '{"criteria_scores": {}, "score": 1.0, "max_score": 1.0, '
            '"feedback_text": "x", "inline_comments": []}'
        )
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = [
            RuntimeError("429 Too Many Requests"),
            RuntimeError("timeout"),
            AIMessage(content=grade_json),
        ]
        grading._invoke_llm.retry.wait = tenacity.wait_none()  # no sleeping in tests
        with patch("ta.tools.grading._get_llm", return_value=fake_llm):
            from ta.tools.grading import analyze_submission
            result = analyze_submission.func(
                submission_text="x", rubric_json="[]", assignment_type="code"
            )
        assert '"score": 1.0' in result
        assert fake_llm.invoke.call_count == 3
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py -v -k retries`
Expected: FAIL — `AttributeError: module ... has no attribute '_invoke_llm'`.

- [ ] **Step 4: Implement in `ta/tools/grading.py`**

Add import at top: `from tenacity import retry, stop_after_attempt, wait_exponential`

Add below `_get_llm`:

```python
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=30), reraise=True)
def _invoke_llm(messages: list):
    """LLM call with backoff — the free NVIDIA endpoint rate-limits bursts."""
    return _get_llm().invoke(messages)
```

In `analyze_submission`, replace:
```python
    llm = _get_llm()
    response = llm.invoke([
```
with:
```python
    response = _invoke_llm([
```
(the closing bracket of the message list stays as-is)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py tests/test_tools_grading.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ta/tools/grading.py pyproject.toml uv.lock tests/test_grading.py
git commit -m "feat: retry LLM grading calls with exponential backoff"
```

---

### Task 6: Recover from revoked refresh tokens

**Files:**
- Modify: `ta/google_auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Append inside `class TestGetCredentials` in `tests/test_auth.py`:

```python
    def test_refresh_error_triggers_browser_flow(self, tmp_path):
        from google.auth.exceptions import RefreshError

        token_file = tmp_path / "token.json"
        token_file.write_text("{}")

        stale = MagicMock(valid=False, expired=True, refresh_token="1//x")
        stale.refresh.side_effect = RefreshError("invalid_grant: revoked")
        fresh = MagicMock(valid=True)
        fresh.to_json.return_value = '{"token": "new"}'

        with (
            patch("ta.google_auth.Settings") as mock_settings_cls,
            patch("ta.google_auth.Credentials.from_authorized_user_file", return_value=stale),
            patch("ta.google_auth.Request"),
            patch("ta.google_auth.InstalledAppFlow") as mock_flow_cls,
        ):
            mock_flow_cls.from_client_secrets_file.return_value.run_local_server.return_value = fresh
            self._mock_settings(mock_settings_cls, "fake_secret.json", str(token_file))
            creds = get_credentials("cugdl")

        assert creds is fresh
        assert token_file.read_text() == '{"token": "new"}'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py -v -k refresh_error`
Expected: FAIL — `RefreshError` propagates uncaught.

- [ ] **Step 3: Implement in `ta/google_auth.py`**

Add import: `from google.auth.exceptions import RefreshError`

Replace:
```python
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())
```
with:
```python
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Token revoked or scopes changed — discard and re-run consent.
                Path(token_path).unlink(missing_ok=True)
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(token_path).write_text(creds.to_json())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py -v`
Expected: ALL PASS (the existing successful-refresh test still skips the browser flow).

- [ ] **Step 5: Commit**

```bash
git add ta/google_auth.py tests/test_auth.py
git commit -m "feat: auto-recover from revoked refresh tokens via browser re-consent"
```

---

### Task 7: DRAFT default + scheduled posts

**Files:**
- Modify: `ta/tools/classroom.py`, `ta/agent.py`
- Test: `tests/test_classroom_admin.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_classroom_admin.py`:

```python
class TestDraftAndScheduled:
    def test_post_announcement_drafts_by_default(self):
        svc = _service_mock()
        svc.courses().announcements().create().execute.return_value = {"id": "a1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import post_announcement
            post_announcement.func(course_id="c1", text="Hola")
        body = svc.courses().announcements().create.call_args.kwargs["body"]
        assert body["state"] == "DRAFT"
        assert "scheduledTime" not in body

    def test_scheduled_time_converts_to_utc_and_forces_draft(self):
        svc = _service_mock()
        svc.courses().announcements().create().execute.return_value = {"id": "a1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import post_announcement
            post_announcement.func(
                course_id="c1", text="Hola", state="PUBLISHED",
                scheduled_time="2026-06-15 08:00",
            )
        body = svc.courses().announcements().create.call_args.kwargs["body"]
        assert body["scheduledTime"] == "2026-06-15T14:00:00Z"  # CDMX is UTC-6
        assert body["state"] == "DRAFT"  # API requires DRAFT while scheduled

    def test_create_assignment_draft_default(self):
        svc = _service_mock()
        svc.courses().courseWork().create().execute.return_value = {"id": "w1", "title": "T"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import create_assignment
            create_assignment.func(
                course_id="c1", title="T", description="D", max_points=10.0,
                due_date="2026-06-20", due_time="23:59", materials_drive_ids=[],
            )
        body = svc.courses().courseWork().create.call_args.kwargs["body"]
        assert body["state"] == "DRAFT"

    def test_create_material_draft_default(self):
        svc = _service_mock()
        svc.courses().courseWorkMaterials().create().execute.return_value = {"id": "m1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import create_material
            create_material.func(
                course_id="c1", title="M", description="D",
                drive_file_ids=[], youtube_urls=[], link_urls=[],
            )
        body = svc.courses().courseWorkMaterials().create.call_args.kwargs["body"]
        assert body["state"] == "DRAFT"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py::TestDraftAndScheduled -v`
Expected: FAIL — bodies carry `"state": "PUBLISHED"`, no `scheduled_time` param.

- [ ] **Step 3: Implement in `ta/tools/classroom.py`**

a) Add at module level (below the existing imports):

```python
from datetime import datetime
from zoneinfo import ZoneInfo

_LOCAL_TZ = ZoneInfo("America/Mexico_City")


def _to_utc_rfc3339(local_str: str) -> str:
    """'YYYY-MM-DD HH:MM' Mexico City local time → RFC3339 UTC string."""
    local_dt = datetime.strptime(local_str, "%Y-%m-%d %H:%M").replace(tzinfo=_LOCAL_TZ)
    return local_dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
```

b) Replace `post_announcement` entirely with:

```python
@tool
def post_announcement(
    course_id: str, text: str, state: str = "DRAFT", scheduled_time: str = ""
) -> str:
    """Post an announcement to a course. Created as DRAFT by default — review in the
    Classroom UI and publish with update_announcement(state='PUBLISHED'), or pass
    state='PUBLISHED' to go live immediately. scheduled_time ('YYYY-MM-DD HH:MM',
    Mexico City local time) schedules automatic publication (state stays DRAFT until
    then, per API rules). Requires confirmation."""
    body: dict = {"text": text, "state": state.upper()}
    when = ""
    if scheduled_time:
        body["scheduledTime"] = _to_utc_rfc3339(scheduled_time)
        body["state"] = "DRAFT"
        when = f"\nScheduled: {scheduled_time} local → publishes automatically"
    confirmed = interrupt({
        "action": "post_announcement",
        "details": f"Post announcement ({body['state']}) to course {course_id}{when}:\n\n{text}",
    })
    if not confirmed:
        return "Announcement posting cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = svc.courses().announcements().create(
            courseId=course_id, body=body
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    return f"Announcement posted (id: {result['id']}, state: {body['state']})."
```

c) `create_assignment` — add `state: str = "DRAFT", scheduled_time: str = ""` as
the last two parameters and extend the docstring with the DRAFT/scheduling note.
Move the existing body construction (date parsing + body dict + materials block)
ABOVE the `interrupt(...)` call, change `"state": "PUBLISHED",` to
`"state": state.upper(),`, and right after the materials block add:

```python
    if scheduled_time:
        body["scheduledTime"] = _to_utc_rfc3339(scheduled_time)
        body["state"] = "DRAFT"
```

Update the confirmation details first line to
`f"Create assignment '{title}' ({body['state']}) in course {course_id}\n"`.

d) `create_material` — add `state: str = "DRAFT"` as the last parameter, extend
the docstring, replace `"state": "PUBLISHED",` with `"state": state.upper(),`.

e) In `ta/agent.py` `SYSTEM_PROMPT`, append after the REWRITE PROTOCOL block:

```
DRAFT WORKFLOW: announcements, assignments, and materials are created as DRAFT by
default. Tell the instructor to review them in the Classroom UI and publish with
update_assignment/update_announcement (state="PUBLISHED"), or create directly with
state="PUBLISHED" when explicitly asked. scheduled_time ("YYYY-MM-DD HH:MM",
Mexico City time) schedules automatic publication.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py tests/test_tools_classroom.py tests/test_agent.py -v`
Expected: ALL PASS (existing create tests don't assert state).

- [ ] **Step 5: Commit**

```bash
git add ta/tools/classroom.py ta/agent.py tests/test_classroom_admin.py
git commit -m "feat: DRAFT-by-default posts and scheduled publication"
```

---

### Task 8: import_grades from xlsx

**Files:**
- Modify: `ta/tools/grading.py`, `ta/tools/__init__.py`, `tests/test_agent.py`
- Test: `tests/test_grading.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grading.py`:

```python
class TestImportGrades:
    def test_imports_known_students_and_reports_unknown(self, tmp_path):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(["Email", "Grade", "Feedback"])
        ws.append(["ana@school.mx", 9.5, "Bien"])
        ws.append(["beto@school.mx", 8, ""])
        ws.append(["charlie@school.mx", 7, ""])  # not enrolled
        xlsx = tmp_path / "grades.xlsx"
        wb.save(xlsx)

        svc = MagicMock()
        svc.courses().students().list().execute.return_value = {
            "students": [
                {"userId": "u-ana", "profile": {"emailAddress": "ana@school.mx"}},
                {"userId": "u-beto", "profile": {"emailAddress": "beto@school.mx"}},
            ]
        }
        sub_list = svc.courses().courseWork().studentSubmissions().list().execute
        sub_list.side_effect = [
            {"studentSubmissions": [{
                "id": "sub-ana", "userId": "u-ana",
                "assignmentSubmission": {"attachments": [{"driveFile": {"id": "f-ana"}}]},
            }]},
            {"studentSubmissions": [{"id": "sub-beto", "userId": "u-beto"}]},
        ]
        drive = MagicMock()
        captured: list[dict] = []
        with patch("ta.tools.grading.interrupt",
                   side_effect=lambda p: captured.append(p) or True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc), \
             patch("ta.tools.drive._drive_service", return_value=drive):
            from ta.tools.grading import import_grades
            result = import_grades.func(
                course_id="c1", coursework_id="w1", xlsx_path=str(xlsx)
            )

        assert "Post 2 grades" in captured[0]["details"]
        assert "Imported 2 grades" in result
        assert "charlie@school.mx" in result and "not enrolled" in result
        patch_call = svc.courses().courseWork().studentSubmissions().patch
        assert patch_call.call_count == 2
        assert drive.comments().create.call_count == 1  # only Ana had feedback+file
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py::TestImportGrades -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement in `ta/tools/grading.py`** (append at end)

```python
@tool
def import_grades(course_id: str, coursework_id: str, xlsx_path: str) -> str:
    """Bulk-post grades for an assignment from an .xlsx file. Required header
    columns: 'Email', 'Grade'; optional 'Feedback' (delivered as a comment on each
    student's submitted Drive file). One confirmation covers the whole batch.
    Unknown emails and non-numeric grades are skipped and reported."""
    from openpyxl import load_workbook

    from ta.tools.classroom import _classroom_service, _collect_pages

    path = Path(xlsx_path)
    if not path.exists():
        return f"Error: file not found: {xlsx_path}"
    rows = list(load_workbook(path, read_only=True).active.values)
    if not rows:
        return "Error: empty spreadsheet."
    headers = [str(h).strip().lower() if h else "" for h in rows[0]]
    if "email" not in headers or "grade" not in headers:
        return "Error: spreadsheet must have 'Email' and 'Grade' header columns."
    email_i, grade_i = headers.index("email"), headers.index("grade")
    fb_i = headers.index("feedback") if "feedback" in headers else None

    svc = _classroom_service(get_active_account())
    roster = _collect_pages(
        lambda tok: svc.courses().students().list(courseId=course_id, pageToken=tok),
        "students",
    )
    email_to_id = {
        s.get("profile", {}).get("emailAddress", "").lower(): s["userId"]
        for s in roster
    }

    entries: list[tuple[str, str, float, str]] = []
    skipped: list[str] = []
    for row in rows[1:]:
        email = str(row[email_i] or "").strip().lower()
        if not email:
            continue
        user_id = email_to_id.get(email)
        if not user_id:
            skipped.append(f"{email}: not enrolled")
            continue
        try:
            score = float(row[grade_i])
        except (TypeError, ValueError):
            skipped.append(f"{email}: grade '{row[grade_i]}' is not numeric")
            continue
        feedback = str(row[fb_i] or "") if fb_i is not None else ""
        entries.append((email, user_id, score, feedback))

    if not entries:
        return "No valid rows to post.\n" + "\n".join(f"- SKIPPED {s}" for s in skipped)

    scores = [e[2] for e in entries]
    preview = "\n".join(f"  {e[0]} → {e[2]}" for e in entries[:3])
    confirmed = interrupt({
        "action": "import_grades",
        "details": (
            f"Post {len(entries)} grades to assignment {coursework_id} "
            f"in course {course_id}\n"
            f"Range: {min(scores)}–{max(scores)}\nFirst rows:\n{preview}"
        ),
    })
    if not confirmed:
        return "Grade import cancelled."

    results = []
    undelivered = 0
    for email, user_id, score, feedback in entries:
        msg = _post_one_grade(svc, course_id, coursework_id, user_id, score, feedback)
        if "NOT delivered" in msg:
            undelivered += 1
        results.append(f"- {email}: {msg}")
    summary = f"Imported {len(entries)} grades; {len(skipped)} skipped"
    if undelivered:
        summary += f"; {undelivered} feedback(s) undelivered"
    return summary + ".\n" + "\n".join(results + [f"- SKIPPED {s}" for s in skipped])
```

- [ ] **Step 4: Register**

`ta/tools/__init__.py`: add `import_grades` to the grading import block
(alphabetical: after `export_grades`) and to `ALL_TOOLS` in the Grading group.

`tests/test_agent.py`: restore `test_minimum_tool_count` to `>= 43` and add
`"import_grades"` to the expected-names list in `test_all_tools_registered`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py tests/test_agent.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ta/tools/grading.py ta/tools/__init__.py tests/test_grading.py tests/test_agent.py
git commit -m "feat: bulk grade import from xlsx with single batch confirmation"
```

---

### Task 9: CLI v2 — live Markdown, prompt_toolkit history, /think toggle

**Files:**
- Modify: `ta/cli.py` (full rewrite), `ta/agent.py`, `main.py`, `.gitignore`, `pyproject.toml` (via uv)
- Test: `tests/test_cli.py` (full rewrite), `tests/test_agent.py`

- [ ] **Step 1: Add the dependency**

Run: `uv add prompt-toolkit`

- [ ] **Step 2: Write the failing tests — replace ALL of `tests/test_cli.py` with:**

```python
# tests/test_cli.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command

CFG = {"configurable": {"thread_id": "t"}}


def _chunk(text="", reasoning="", node="agent"):
    """Build a ('messages', (AIMessageChunk, metadata)) stream item."""
    kwargs = {"reasoning_content": reasoning} if reasoning else {}
    return (
        "messages",
        (AIMessageChunk(content=text, additional_kwargs=kwargs), {"langgraph_node": node}),
    )


def _update(payload):
    return ("updates", payload)


def _factory(mock_graph):
    """make_graph stand-in that always returns the same mock graph."""
    return lambda thinking: mock_graph


def _run(mock_graph, prompts, confirms=()):
    """Drive run_repl: main inputs via PromptSession, y/N answers via input()."""
    from ta.cli import run_repl
    with patch("ta.cli.PromptSession") as mock_ps, \
         patch("builtins.input", side_effect=list(confirms)):
        mock_ps.return_value.prompt.side_effect = list(prompts)
        run_repl(_factory(mock_graph), CFG)


class TestRunRepl:
    def test_exits_without_calling_graph(self):
        mock_graph = MagicMock()
        _run(mock_graph, ["exit"])
        mock_graph.stream.assert_not_called()

    def test_sends_user_message_and_uses_both_stream_modes(self):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter(
            [_update({"agent": {"messages": [AIMessage(content="Courses listed!")]}})]
        )
        _run(mock_graph, ["list courses", "exit"])
        args, kwargs = mock_graph.stream.call_args
        assert args[0]["messages"][0].content == "list courses"
        assert kwargs["stream_mode"] == ["messages", "updates"]

    def test_streams_reasoning_before_answer(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(reasoning="THINKBIT"),
            _chunk(text="ANSWERBIT"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "THINKBIT" in out
        assert "ANSWERBIT" in out
        assert out.index("THINKBIT") < out.index("ANSWERBIT")
        assert "thinking" in out

    def test_answer_markdown_table_renders_with_borders(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="| Curso | Alumnos |\n"),
            _chunk(text="| --- | --- |\n"),
            _chunk(text="| IA101 | 30 |\n"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "IA101" in out and "30" in out
        assert "│" in out or "─" in out  # box-drawing glyphs from the table render

    def test_streamed_answer_not_reprinted_from_updates(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="UNIQUE42"),
            _update({"agent": {"messages": [AIMessage(content="UNIQUE42")]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert out.count("UNIQUE42") == 1

    def test_unstreamed_ai_update_is_printed_as_fallback(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _update({"agent": {"messages": [AIMessage(content="FALLBACK77")]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert out.count("FALLBACK77") == 1

    def test_tool_call_notice_printed(self, capsys):
        mock_graph = MagicMock()
        ai_with_tool = AIMessage(
            content="",
            tool_calls=[{"name": "list_courses", "args": {}, "id": "tc1"}],
        )
        mock_graph.stream.return_value = iter([
            _update({"agent": {"messages": [ai_with_tool]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "list_courses" in out
        assert "⚙" in out

    def test_subagent_tokens_tagged(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="SUBTOKEN", node="tools"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "SUBTOKEN" in out
        assert "[tools]" in out

    def test_interrupt_yes_resumes_with_true(self):
        mock_graph = MagicMock()
        mock_graph.stream.side_effect = [
            iter([_update({"__interrupt__": [MagicMock(
                value={"action": "post_announcement", "details": "Post?"}, id="intr-1"
            )]})]),
            iter([_update({"agent": {"messages": [AIMessage(content="Posted.")]}})]),
        ]
        _run(mock_graph, ["post it", "exit"], confirms=["y"])
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"intr-1": True}

    def test_interrupt_no_resumes_with_false(self):
        mock_graph = MagicMock()
        mock_graph.stream.side_effect = [
            iter([_update({"__interrupt__": [MagicMock(
                value={"action": "post_grade", "details": "Post?"}, id="intr-2"
            )]})]),
            iter([_update({"agent": {"messages": [AIMessage(content="Cancelled.")]}})]),
        ]
        _run(mock_graph, ["grade", "exit"], confirms=["n"])
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"intr-2": False}

    def test_multiple_interrupts_confirm_all(self):
        mock_graph = MagicMock()
        mock_graph.stream.side_effect = [
            iter([_update({"__interrupt__": [
                MagicMock(value={"action": "post_grade", "details": "A"}, id="i1"),
                MagicMock(value={"action": "post_grade", "details": "B"}, id="i2"),
            ]})]),
            iter([_update({"agent": {"messages": [AIMessage(content="Done.")]}})]),
        ]
        _run(mock_graph, ["grade all", "exit"], confirms=["y"])
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"i1": True, "i2": True}


class TestThinkToggle:
    def test_think_off_rebuilds_graph_and_routes_next_turn(self):
        built = []

        def make_graph(thinking):
            g = MagicMock()
            g.thinking = thinking
            g.stream.return_value = iter([])
            built.append(g)
            return g

        from ta.cli import run_repl
        with patch("ta.cli.PromptSession") as mock_ps, \
             patch("builtins.input", side_effect=[]):
            mock_ps.return_value.prompt.side_effect = ["/think off", "hola", "exit"]
            run_repl(make_graph, CFG, initial_thinking=True)

        assert [g.thinking for g in built] == [True, False]
        built[0].stream.assert_not_called()
        built[1].stream.assert_called_once()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_cli.py -v`
Expected: ALL FAIL — `run_repl` takes a graph, not a factory; no PromptSession in `ta.cli`.

- [ ] **Step 4: Rewrite `ta/cli.py`** — replace the entire file with:

```python
# ta/cli.py
from collections.abc import Callable

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

# Node names of the main deep-agent loop; anything else (subagents, tool-internal
# LLM calls) gets a visible [node] tag so the instructor knows who is talking.
_MAIN_NODES = {"agent", "model"}


def _chunk_reasoning(chunk: AIMessageChunk) -> str:
    """Raw reasoning tokens. NVIDIA NIM puts them in additional_kwargs
    ['reasoning_content']; some versions emit typed content blocks instead."""
    reasoning = chunk.additional_kwargs.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        return reasoning
    if isinstance(chunk.content, list):
        return "".join(
            block.get("reasoning_content") or block.get("reasoning") or ""
            for block in chunk.content
            if isinstance(block, dict) and "reasoning" in str(block.get("type", ""))
        )
    return ""


def _chunk_text(chunk: AIMessageChunk) -> str:
    if isinstance(chunk.content, str):
        return chunk.content
    if isinstance(chunk.content, list):
        return "".join(
            block.get("text", "")
            for block in chunk.content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


class StreamRenderer:
    """Raw thinking streams dim grey; the answer renders as live Markdown."""

    def __init__(self) -> None:
        self.section: str | None = None  # None | "thinking" | "answer"
        self.streamed_answer = False  # any answer tokens shown this turn
        self._answer_buf = ""
        self._live: Live | None = None

    def on_chunk(self, chunk: AIMessageChunk, metadata: dict | None) -> None:
        if not isinstance(chunk, AIMessageChunk):
            return
        node = (metadata or {}).get("langgraph_node", "")
        tag = "" if node in _MAIN_NODES else f"[{node}] "
        reasoning = _chunk_reasoning(chunk)
        if reasoning:
            if self.section != "thinking":
                self._close_current()
                console.print(f"\n🧠 {tag}thinking", style="bold magenta", markup=False)
                self.section = "thinking"
            console.print(
                reasoning, style="grey50 italic", end="",
                soft_wrap=True, markup=False, highlight=False,
            )
        text = _chunk_text(chunk)
        if text:
            if self.section != "answer":
                self._close_current()
                console.print(f"\n💬 {tag}TA Agent", style="bold blue", markup=False)
                self.section = "answer"
                self._answer_buf = ""
                self._live = Live(
                    Markdown(""), console=console,
                    refresh_per_second=8, vertical_overflow="visible",
                )
                self._live.start()
            self.streamed_answer = True
            self._answer_buf += text
            if self._live is not None:
                self._live.update(Markdown(self._answer_buf))

    def _close_current(self) -> None:
        if self.section == "answer" and self._live is not None:
            self._live.stop()  # leaves the final Markdown render on screen
            self._live = None
        elif self.section == "thinking":
            console.print()  # close the in-progress dim line
        self.section = None

    def finish(self) -> None:
        """Close any open stream section — call before prompts, notices, errors."""
        self._close_current()


def _handle_update(payload: dict, renderer: StreamRenderer) -> None:
    """Updates channel: tool-call notices + fallback for non-streamed AI text."""
    for node_name, node_update in payload.items():
        if node_name.startswith("__") or not isinstance(node_update, dict):
            continue
        for msg in node_update.get("messages", []):
            msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
            if msg_type not in ("ai", "assistant"):
                continue
            tool_calls = getattr(msg, "tool_calls", None) or []
            for tc in tool_calls:
                renderer.finish()
                console.print(f"⚙ {tc.get('name', '?')}...", style="dim", markup=False)
            content = getattr(msg, "content", None)
            if (
                not tool_calls
                and not renderer.streamed_answer
                and isinstance(content, str)
                and content.strip()
            ):
                renderer.finish()
                console.print(Markdown(content))


def _prompt_confirmations(interrupts) -> dict:
    """Collect y/N decisions for one or more pending interrupts."""
    resume_values: dict = {}
    if len(interrupts) == 1:
        intr = interrupts[0]
        data = intr.value
        console.print("\n[bold yellow]⚠ CONFIRMATION REQUIRED[/bold yellow]")
        console.print(f"[yellow]Action:[/yellow] {data.get('action', '')}")
        console.print("[yellow]Details:[/yellow]")
        console.print(data.get("details", ""), markup=False, highlight=False)
        confirmed = input("\nProceed? [y/N]: ").strip().lower() == "y"
        resume_values = {intr.id: confirmed}
    else:
        console.print(
            f"\n[bold yellow]⚠ {len(interrupts)} CONFIRMATIONS REQUIRED[/bold yellow]"
        )
        for i, intr in enumerate(interrupts, 1):
            d = intr.value
            console.print(
                f"  {i}. {d.get('action', '')} — {str(d.get('details', ''))[:80]}",
                markup=False, highlight=False,
            )
        choice = input(
            f"\nConfirm all {len(interrupts)}? "
            "[y=all / n=cancel all / one=one-by-one]: "
        ).strip().lower()
        if choice == "y":
            resume_values = {intr.id: True for intr in interrupts}
        elif choice == "one":
            for intr in interrupts:
                d = intr.value
                console.print(f"\nAction: {d.get('action', '')}", markup=False)
                console.print("Details:", markup=False)
                console.print(str(d.get("details", "")), markup=False, highlight=False)
                ok = input("Proceed? [y/N]: ").strip().lower() == "y"
                resume_values[intr.id] = ok
        else:
            resume_values = {intr.id: False for intr in interrupts}
    return resume_values


def run_repl(make_graph: Callable, config: dict, initial_thinking: bool = True) -> None:
    """Interactive REPL. make_graph(thinking: bool) builds the agent graph — the
    /think command rebuilds it against the same checkpointer, so the conversation
    thread continues with reasoning toggled."""
    thinking = initial_thinking
    graph = make_graph(thinking)
    session = PromptSession(history=FileHistory(".ta_history"))

    console.print(Panel(
        "[bold green]Classroom TA Agent[/bold green] ready.\n"
        "Type your request and press Enter. Type [bold]exit[/bold] to quit.\n"
        "Raw model reasoning streams in grey; answers render as Markdown.\n"
        "[bold]/think on|off[/bold] toggles model reasoning.\n\n"
        "[dim]Examples:[/dim]\n"
        "  List my courses\n"
        "  Grade all submissions for assignment 987 using rubric rubrics/hw1.yaml\n"
        "  Post announcement: 'Midterm next Friday at 10am'",
        title="Welcome", border_style="green",
    ))

    while True:
        try:
            user_input = session.prompt("\n[You]: ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if user_input.lower() in ("/think on", "/think off"):
            thinking = user_input.lower().endswith("on")
            graph = make_graph(thinking)
            console.print(
                f"[dim]Reasoning {'enabled' if thinking else 'disabled'}.[/dim]"
            )
            continue

        renderer = StreamRenderer()
        try:
            # stream_input starts as the user message; becomes Command(resume=...)
            # after each interrupt so consecutive confirmations work in one turn.
            stream_input: dict | Command = {
                "messages": [HumanMessage(content=user_input)]
            }
            while True:
                got_interrupt = False
                for mode, payload in graph.stream(
                    stream_input, config, stream_mode=["messages", "updates"]
                ):
                    if mode == "messages":
                        chunk, metadata = payload
                        renderer.on_chunk(chunk, metadata)
                        continue
                    if "__interrupt__" in payload:
                        renderer.finish()
                        got_interrupt = True
                        resume_values = _prompt_confirmations(payload["__interrupt__"])
                        stream_input = Command(resume=resume_values)
                        break  # close the paused generator; restart with Command
                    _handle_update(payload, renderer)
                if not got_interrupt:
                    break  # no interrupt this round — turn is complete
            renderer.finish()
        except Exception as exc:
            renderer.finish()
            console.print(f"[bold red]Error:[/bold red] {exc}")
```

- [ ] **Step 5: Thread the thinking override through `build_agent`**

In `ta/agent.py` change the signature to:

```python
def build_agent(settings: Settings, checkpointer=None, enable_thinking: bool | None = None):
```

and immediately before the `llm = ChatNVIDIA(` line add:

```python
    thinking = settings.nvidia_enable_thinking if enable_thinking is None else enable_thinking
```

then in the constructor replace
`chat_template_kwargs={"enable_thinking": settings.nvidia_enable_thinking},`
with `chat_template_kwargs={"enable_thinking": thinking},`.

Add to `tests/test_agent.py` inside `TestBuildAgent`:

```python
    def test_enable_thinking_override(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        with patch("ta.agent.ChatNVIDIA") as mock_llm_cls, \
             patch("ta.agent.create_deep_agent"):
            from ta.agent import build_agent
            from ta.config import Settings
            build_agent(Settings(), checkpointer=MagicMock(), enable_thinking=False)
            kwargs = mock_llm_cls.call_args.kwargs
            assert kwargs["chat_template_kwargs"] == {"enable_thinking": False}
```

- [ ] **Step 6: Rewire `main.py`** — replace the whole file with:

```python
# main.py
import argparse
import sqlite3
from datetime import date

from langgraph.checkpoint.sqlite import SqliteSaver

from ta.agent import build_agent
from ta.cli import run_repl
from ta.config import Settings
from ta.google_auth import get_credentials


def main() -> None:
    parser = argparse.ArgumentParser(description="Classroom TA Agent")
    parser.add_argument(
        "--thread",
        default=f"cli-{date.today().isoformat()}",
        help="Conversation thread id (default: one per day, resumes within the day)",
    )
    args = parser.parse_args()

    settings = Settings()
    get_credentials("cugdl")
    checkpointer = SqliteSaver(
        sqlite3.connect("checkpoints.db", check_same_thread=False)
    )

    def make_graph(thinking: bool):
        return build_agent(settings, checkpointer=checkpointer, enable_thinking=thinking)

    run_repl(
        make_graph,
        {"configurable": {"thread_id": args.thread}},
        initial_thinking=settings.nvidia_enable_thinking,
    )


if __name__ == "__main__":
    main()
```

`.gitignore`: run `Add-Content .gitignore ".ta_history"`

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_cli.py tests/test_agent.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add ta/cli.py ta/agent.py main.py .gitignore pyproject.toml uv.lock tests/test_cli.py tests/test_agent.py
git commit -m "feat: live Markdown answers, prompt history, /think toggle"
```

---

### Task 10: CI workflow, README, final verification

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v7
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -q
```

- [ ] **Step 2: README additions** — insert before the "Tech stack" section:

```markdown
## Memoria, comandos y flujo de publicación

- La conversación persiste en `checkpoints.db` (SQLite); hilo por día por defecto,
  `--thread NOMBRE` para hilos con nombre.
- `/think on|off` alterna el razonamiento del modelo sin reiniciar ni perder la conversación.
- Los posts se crean como **borrador** por defecto — revisa en la UI de Classroom y
  publica con `update_*` (`state="PUBLISHED"`), o pide publicación inmediata.
- `scheduled_time` ("YYYY-MM-DD HH:MM", hora de Ciudad de México) programa la
  publicación automática.
- Las respuestas se renderizan como Markdown (tablas, listas, código) en vivo.
- El feedback de calificaciones se entrega como comentario en el archivo Drive
  entregado (`post_grade(feedback=...)` / columna `Feedback` de `import_grades`).
- El historial del prompt se guarda en `.ta_history` (flechas ↑/↓).
```

- [ ] **Step 3: Verify lockfile is current**

Run: `uv lock`
Expected: resolves with no changes (uv add already maintained it).

- [ ] **Step 4: Full suite + lint**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: ALL PASS (~75 tests)

Run: `.venv\Scripts\python -m ruff check .`
Expected: clean (fix anything reported before committing).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml README.md uv.lock pyproject.toml
git commit -m "ci: GitHub Actions test+lint workflow; document v2 features"
```

---

## Spec coverage map

| Spec section | Tasks |
|---|---|
| A. Markdown en vivo | 9 |
| B. Paginación | 1, 2 |
| C. Feedback vía Drive | 3 (+8 reuses `_post_one_grade`) |
| D1. SQLite memory | 4 |
| D2. Retries | 5 (+`num_retries=3` woven through 1, 2, 3) |
| D3. RefreshError | 6 |
| E1+E2. Draft/scheduled | 7 |
| E3. import_grades | 8 |
| E4. prompt_toolkit | 9 |
| E5. /think | 9 |
| F. Lock + CI + README | 4/5/9 (uv add) + 10 |
