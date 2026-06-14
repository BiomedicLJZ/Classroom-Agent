# Classroom TA Agent

AI Teaching Assistant for Google Classroom, powered by [LangGraph](https://github.com/langchain-ai/langgraph) + [NVIDIA NIM](https://build.nvidia.com).

## Features

- 📢 Post announcements, assignments, and study materials
- 📝 Grade submissions with AI rubric analysis (code, reports, documentation, diagrams)
- 💬 Add inline feedback to Google Docs submissions
- ✅ All write actions require explicit instructor confirmation before executing
- 🔄 Persistent conversation memory within a session (LangGraph checkpointer)

## Architecture

```
main.py
  └── ta/agent.py        # LangGraph create_react_agent + ChatNVIDIA LLM
        ├── ta/tools/    # 17 Google API tools (@tool decorated)
        │     ├── classroom.py   # Courses, students, assignments, announcements
        │     ├── drive.py       # File download/upload
        │     ├── docs.py        # Docs text + inline comments
        │     └── grading.py     # Rubric loader, AI analysis, grade posting
        ├── ta/state.py  # TAState TypedDict (conversation + grading session)
        └── ta/cli.py    # Rich REPL with interrupt confirmation flow
```

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Google Cloud credentials

1. Go to <https://console.cloud.google.com> → create a project named **ta-agent**
2. Enable **Google Classroom API**, **Google Drive API**, **Google Docs API**
3. OAuth consent screen → External → add your Google account as a test user
4. Add these scopes:

   ```
   https://www.googleapis.com/auth/classroom.courses.readonly
   https://www.googleapis.com/auth/classroom.coursework.students
   https://www.googleapis.com/auth/classroom.announcements
   https://www.googleapis.com/auth/classroom.topics
   https://www.googleapis.com/auth/classroom.courseworkmaterials
   https://www.googleapis.com/auth/classroom.rosters.readonly
   https://www.googleapis.com/auth/classroom.student-submissions.students.readonly
   https://www.googleapis.com/auth/drive
   https://www.googleapis.com/auth/documents
   ```

5. Credentials → Create OAuth client ID → Desktop app → download JSON
6. Save as `credentials/client_secret.json`

### 3. NVIDIA NIM API key

Sign up at <https://build.nvidia.com> and create an API key (starts with `nvapi-`).

### 4. Environment variables

```bash
cp .env.example .env
# Edit .env — fill in NVIDIA_API_KEY
```

`.env.example` contents:

```
NVIDIA_API_KEY=nvapi-YOUR_KEY_HERE
NVIDIA_MODEL=meta/llama-3.3-70b-instruct
GOOGLE_CLIENT_SECRET_PATH=credentials/client_secret.json
GOOGLE_TOKEN_PATH=credentials/token.json
```

### 5. Run

```bash
uv run python main.py
```

First run opens a browser for Google OAuth2 consent. The token is cached at
`credentials/token.json` for all future runs.

## Example session

```
[You]: list my courses
[You]: list students in course 123456
[You]: show submission status for assignment 789 in course 123456
[You]: grade all submissions for assignment 789 in course 123456 using rubric rubrics/example_rubric.yaml
[You]: post grade 87.5 for student abc123 in assignment 789 course 123456
⚠ CONFIRMATION REQUIRED
Action: post_grade
Details: Post grade 87.5 pts to student abc123 ...
Proceed? [y/N]: y
[You]: exit
```

## Rubric format

Place YAML rubric files in `rubrics/`. Example (`rubrics/example_rubric.yaml`):

```yaml
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
    description: Is the code readable, well-organized, and appropriately commented?
  - name: Documentation
    weight: 0.20
    max_points: 20
    description: Are functions documented with docstrings? Is there an explanatory README?
  - name: Design
    weight: 0.15
    max_points: 15
    description: Is the solution well-structured? Are abstractions appropriate?
```

## Development

```bash
# Run tests
uv run pytest -v

# Lint
uv run ruff check ta/ tests/ main.py
```

All 29 tests run without real API credentials (Google APIs and NVIDIA LLM are fully mocked).

## Re-authentication required (June 2026 rework)

The agent now requests two additional OAuth scopes (`classroom.topics`,
`classroom.courseworkmaterials`). Existing tokens are missing them — Classroom
calls will fail with 403 until you re-authenticate:

1. Delete `credentials/token.json` (and `credentials/uniat_token.json` if present).
2. Run the agent; the browser consent flow will re-run once per account.

Remember to add the two new scopes to the OAuth consent screen of your Google
Cloud project first (see Setup step 2).

## Reasoning & streaming

- Nemotron 3 Ultra thinking is **OFF by default** (faster replies). Turn it on for a
  session with `/think on`, or default it on with `NVIDIA_ENABLE_THINKING=true` in
  `.env`. When on, raw reasoning streams in dim grey before each answer.
- Tune via `.env`: `NVIDIA_TEMPERATURE`, `NVIDIA_TOP_P`, `NVIDIA_MAX_TOKENS`,
  `NVIDIA_REASONING_BUDGET`, `NVIDIA_ENABLE_THINKING`.
- Answers render as rich Markdown — coloured headings, monokai-highlighted code
  blocks, bordered tables, clickable links — inside a subtle answer panel.
- Noisy NVIDIA integration warnings (non-default kwargs, `max_tokens` deprecation,
  unknown model type) are silenced for clean output.
- Every student-facing text you type is improved/rewritten before posting; the
  confirmation prompt shows the full final text.

## Slash commands & help

- Type `/` for an autocomplete dropdown of slash commands.
- `/help` shows all slash commands plus the agent's capability modules (courses,
  roster, assignments, announcements, materials, topics, grading, drive, office,
  accounts). `/help <module>` shows that module's actions with example phrasings.
- `/think on|off` toggles model reasoning. `exit` quits.

## Course & object IDs

- On launch the CLI shows a table of your active courses **with their IDs** so you
  never have to guess one.
- Ask the agent for IDs anytime — it calls `list_course_ids()` (all courses) or
  `list_course_ids(course_id=...)` to dump that course's students, assignments, and
  topics, each with its raw ID. The agent resolves IDs itself before any operation.

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

## Tech stack

| Component | Library |
|---|---|
| Agent framework | LangGraph ≥ 1.2.1 (`create_react_agent`) |
| LLM | langchain-nvidia-ai-endpoints (`ChatNVIDIA`) |
| Google APIs | google-api-python-client, google-auth-oauthlib |
| CLI output | Rich |
| Rubric parsing | PyYAML |
| PDF reading | pypdf |
| Settings | pydantic-settings |
| Tests | pytest + pytest-mock |
