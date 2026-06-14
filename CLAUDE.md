# CLAUDE.md

Project guidance for Claude Code working in this repository.

## What this is

`agentes` — a LangGraph AI Teaching-Assistant agent for Google Classroom. The agent
(deepagents `create_deep_agent` + `ChatNVIDIA` running NVIDIA's free Nemotron 3 Ultra
endpoint) drafts and posts announcements/assignments/materials, manages rosters and
topics, and grades submissions against YAML rubrics. Runs as an interactive Rich CLI.

## Environment & commands

Standalone **uv** project (Python ≥ 3.13). `uv.lock` is committed — installs are
reproducible. The `.venv` was created by uv and has **no pip**.

- Install / sync: `uv sync --frozen`
- Add a dependency: `uv add <pkg>` (updates pyproject + uv.lock + venv)
- Tests: `uv run pytest -q` (Windows venv-direct: `.venv\Scripts\python -m pytest tests/ -q`)
- Lint: `uv run ruff check .` (line-length 100; rules E,F,I,UP,B,SIM)
- Run the app: `uv run python main.py [--thread NAME]`

## Architecture

```
main.py                # entry: argparse --thread, builds SqliteSaver, make_graph(thinking), run_repl
ta/
  __init__.py          # silences noisy NVIDIA integration warnings
  config.py            # Settings (pydantic-settings, .env); NVIDIA + account config
  google_auth.py       # OAuth2 per account; recovers from revoked tokens
  session.py           # module-level active account (cugdl | uniat)
  state.py             # TAState TypedDict
  agent.py             # build_agent: ChatNVIDIA + SYSTEM_PROMPT + grading subagent
  cli.py               # Rich REPL: token streaming, live Markdown, /think, /help, banner
  tools/
    classroom.py       # courses/roster/assignments/announcements/materials/topics + list_course_ids
    grading.py         # rubric load, AI analysis, post_grade (Drive feedback), export/import grades
    drive.py docs.py office.py accounts.py
tests/                 # pytest; every Google/NVIDIA call is mocked — no network, no real creds
```

## Conventions

- **TDD**: write the failing test in `tests/`, watch it fail, implement, watch it pass, commit.
  Tests mock `_classroom_service` / `_drive_service` / `_get_llm`; never hit the network.
- `@tool` functions return human-readable strings. All write actions call `interrupt()`
  for a single instructor confirmation; the confirmation `details` show the full final text.
- Classroom list calls paginate through `_collect_pages` (follow `nextPageToken`).
- New tools must be registered in `ta/tools/__init__.py` `ALL_TOOLS` and covered by a test.

## Product behaviors (intentional — don't "fix")

- **Reasoning is OFF by default.** Toggle per-session with `/think on|off`, or set
  `NVIDIA_ENABLE_THINKING=true` in `.env`.
- **Posts are DRAFT by default** (announcements/assignments/materials). Publish via
  `update_*` with `state="PUBLISHED"`, or pass `state="PUBLISHED"`/`scheduled_time` up front.
- **ID-first**: the agent never asks for or guesses IDs — it calls `list_course_ids()`
  to resolve them first.
- **Grading feedback** is delivered as a comment on the student's submitted Drive file
  (`post_grade(feedback=...)`) — the Classroom API has no private comments.
- Two accounts: `cugdl` (default) and `uniat`; switch with `switch_account`.

## Gotchas

- Classroom API list responses use **singular** keys: `topic` (topics), `courseWorkMaterial`
  (materials). Pagination keys differ from the resource name — check before assuming.
- Changing OAuth scopes invalidates existing tokens: delete `credentials/token.json`
  (and the uniat token) and re-run to re-consent.
- `pytest` resets `warnings.filters` per test; warning-suppression tests must re-install
  filters via `ta._install_nvidia_warning_filters()` before asserting.
