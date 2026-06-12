# Mejoras v2 — Markdown vivo, paginación, feedback real, robustez, draft/scheduled, import, infra

**Fecha:** 2026-06-12
**Estado:** Aprobado por el instructor (Leonardo)
**Base:** rework 2026-06-12 (`docs/superpowers/specs/2026-06-12-ta-agent-rework-design.md`), HEAD `80b133d`

## Objetivos

A. Respuestas renderizadas como Markdown (tablas, listas, código) en vivo durante el stream.
B. Paginación completa en todas las llamadas list de Google Classroom.
C. Feedback de calificación entregado de verdad (Drive comments); eliminar el tool no-op.
D. Robustez: memoria persistente SQLite, retries con backoff, recuperación de token revocado.
E. UX: DRAFT default, posts programados, import de calificaciones desde xlsx, prompt_toolkit, /think toggle.
F. Infra: uv.lock + CI GitHub Actions.

## No-objetivos

- Comentarios privados nativos de Classroom (la API no los expone — C es el sustituto).
- Render Markdown del razonamiento (queda crudo gris a propósito).
- Multilínea avanzada en REPL (solo historial + edición de línea).

---

## A. Markdown en vivo — `ta/cli.py`

- `StreamRenderer` acumula tokens de respuesta en `self._answer_buf`.
- Al entrar a sección "answer": crea `rich.live.Live(Markdown(""), console=console, refresh_per_second=8, vertical_overflow="visible")` y lo inicia; cada token → `live.update(Markdown(buf))`.
- `finish()` detiene el Live (si activo) antes de prompts/avisos/errores; deja el render final impreso.
- Thinking: sin cambio (crudo, gris, token a token).
- Fallback de `_handle_update` (texto AI no streameado): imprime `Markdown(content)` estático.
- Tests: tokens que forman tabla MD → capsys contiene glifos de borde (`│` o `─`) y el contenido; thinking sigue apareciendo antes; no doble impresión se mantiene.

## B. Paginación — `ta/tools/classroom.py`, `ta/tools/grading.py`

Helper module-level en classroom.py:

```python
def _collect_pages(make_request, items_key: str) -> list:
    """Follow nextPageToken until exhausted. make_request(page_token) returns
    an executable API request."""
    items, token = [], None
    while True:
        response = make_request(token).execute(num_retries=3)
        items.extend(response.get(items_key, []))
        token = response.get("nextPageToken")
        if not token:
            return items
```

Aplicado a: `list_students`, `list_assignments`, `get_submission_status`,
`list_announcements`, `list_materials`, `list_invitations`, y en grading:
roster/coursework/submissions de `export_grades`, submissions de
`batch_grade_assignment`. Test: dos páginas mockeadas → items de ambas.

## C. Feedback vía Drive — `ta/tools/grading.py`

- `post_grade(course_id, coursework_id, student_id, score, feedback="")`:
  1. Confirmación (interrupt) muestra score + feedback completo.
  2. Patch de `assignedGrade`/`draftGrade` + `return_` (como hoy).
  3. Si `feedback`: obtiene la submission, toma el primer attachment Drive y crea
     un comment vía Drive API (`drive.comments().create(fileId=..., body={"content": feedback}, fields="id")` —
     mismo mecanismo que `add_doc_comment` en `ta/tools/docs.py`).
  4. Sin attachment Drive → retorna "feedback NOT delivered (no Drive file); deliver manually: <texto>".
- `post_private_comment` se elimina de `grading.py` y de `ALL_TOOLS`.
- `SYSTEM_PROMPT` (REWRITE PROTOCOL, nota final): reemplaza la mención de
  `post_private_comment` por "feedback se entrega como comentario en el archivo
  Drive de la entrega vía post_grade(feedback=...)".
- `batch_grade_assignment`: el mensaje final ya dirige a `post_grade` — sin cambio.
- Tests: feedback con Doc → comment creado con texto; sin attachment → mensaje honesto; tool ausente de ALL_TOOLS.

## D. Robustez

### D1. Memoria persistente
- Dep nueva: `langgraph-checkpoint-sqlite`.
- `ta/agent.py`: `build_agent(settings, checkpointer=None)`; default
  `SqliteSaver(sqlite3.connect("checkpoints.db", check_same_thread=False))` si None.
- `main.py`: argparse con `--thread NAME`; default `f"cli-{date.today().isoformat()}"`.
- `.gitignore`: `checkpoints.db`.
- Test: build_agent acepta checkpointer inyectado; default crea SqliteSaver (mock/patch).

### D2. Retries
- Dep nueva: `tenacity`.
- `analyze_submission`: `@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=30), reraise=True)` sobre la llamada LLM (función interna `_invoke_llm`).
- Google: `.execute(num_retries=3)` en todas las llamadas (el cliente reintenta solo transitorios 5xx/429).
- Test: LLM falla 2 veces → tercera pasa.

### D3. Token revocado
- `ta/google_auth.py`: `from google.auth.exceptions import RefreshError`; el
  `creds.refresh(Request())` en try/except → en RefreshError borra el token file
  y cae al flujo `InstalledAppFlow` (browser).
- Test: refresh lanza RefreshError → flow browser invocado y token reescrito.

## E. UX

### E1. DRAFT default + E2. Scheduled
- `post_announcement(course_id, text, state="DRAFT", scheduled_time="")`,
  `create_assignment(..., state="DRAFT", scheduled_time="")`,
  `create_material(..., state="DRAFT")`.
- `scheduled_time` formato `"YYYY-MM-DD HH:MM"` hora local (`America/Mexico_City`,
  `zoneinfo` stdlib) → body `scheduledTime` en UTC RFC3339 (`...Z`) y fuerza `state="DRAFT"`
  (requisito de la API; Classroom publica solo a la hora).
- Confirmación muestra estado y hora programada.
- `SYSTEM_PROMPT`: documenta flujo draft→publicar (`update_*(state="PUBLISHED")`) y scheduling.
- Tests: body con `state: DRAFT` default; `scheduled_time="2026-06-15 08:00"` →
  `scheduledTime == "2026-06-15T14:00:00Z"` (UTC-6); state forzado a DRAFT al programar.

### E3. import_grades — `ta/tools/grading.py`
- `import_grades(course_id, coursework_id, xlsx_path)`: lee xlsx (openpyxl),
  columnas por header: `Email` (req), `Grade` (req), `Feedback` (opcional).
- Resuelve email→userId con roster paginado; filas con email desconocido o grade
  no numérico se reportan y se saltan.
- UNA confirmación: "Post N grades to assignment X (rango min–max). Preview: 3 primeras filas".
- Por fila: patch grade + return_ + feedback a Drive (lógica de C, factorizada en
  helper `_post_one_grade(svc, course_id, coursework_id, user_id, score, feedback)`).
- Retorna resumen: posteados / saltados / feedback no entregado.
- Test: xlsx real en tmp_path con 2 alumnos + 1 email desconocido → 2 posteados, 1 reportado.

### E4. prompt_toolkit
- Dep nueva: `prompt-toolkit`.
- `ta/cli.py`: `PromptSession(history=FileHistory(".ta_history"))` solo para el
  input principal `[You]:` (las confirmaciones y/N quedan con `input()` —
  respuestas de una letra no necesitan historial).
- La sesión se crea dentro de `run_repl`, no en import-time.
- `.gitignore`: `.ta_history`.
- Tests: patch de `PromptSession.prompt` en lugar de `builtins.input` para el input principal.

### E5. /think toggle
- `build_agent` gana `enable_thinking: bool | None = None` (None → settings).
- `main.py`: crea checkpointer compartido + closure `make_graph(thinking: bool)`;
  `run_repl(make_graph, config, initial_thinking=settings.nvidia_enable_thinking)`.
- `run_repl`: intercepta `/think on` / `/think off` antes de mandar al grafo;
  reconstruye `graph = make_graph(flag)` y confirma en consola. Mismo checkpointer
  + mismo thread = conversación continúa.
- Firma nueva: `run_repl(make_graph: Callable[[bool], Any], config: dict, initial_thinking: bool = True)`.
- Tests: `/think off` → make_graph llamado con False; turno siguiente usa el nuevo grafo.

## F. Infra

- `pyproject.toml`: + `langgraph-checkpoint-sqlite`, `tenacity`, `prompt-toolkit`.
- `uv lock` ejecutado; `uv.lock` commiteado; venv sincronizado con `uv sync`.
- `.github/workflows/ci.yml`: on push/PR → `astral-sh/setup-uv@v7` → `uv sync` →
  `uv run pytest -q` → `uv run ruff check .` (Python 3.13 desde pyproject).
- README: sección desarrollo actualizada (uv sync).

## Orden de implementación

B (paginación) → C (feedback) → D1-D3 → E1+E2 (state/scheduled juntos, mismos tools)
→ E3 (import, reusa C) → A (markdown live) → E4 (prompt_toolkit, toca cli tests)
→ E5 (/think, toca main+cli) → F (deps/lock/CI/README al final).

Nota: D1, D2 y E4 requieren sus deps ANTES de sus tests — el paso de deps+`uv sync`
se ejecuta al inicio de F... corrección: las deps se agregan e instalan en el
primer task que las necesita (D1 instala langgraph-checkpoint-sqlite, D2 tenacity,
E4 prompt-toolkit); F solo consolida lockfile + CI.

## Riesgos

1. **Live + capsys en tests**: Rich Live escribe por el mismo console; en
   no-terminal el render final se imprime al stop. Asserts sobre el output final,
   no sobre frames intermedios.
2. **Drive comments en archivos no-Doc**: la API de comments funciona para
   cualquier archivo de Drive (Docs/Sheets/PDF); si el attachment es un link
   no-Drive, cae al mensaje honesto.
3. **prompt_toolkit en tests/CI**: requiere tty para features interactivas; los
   tests la parchean y no se instancia en import-time.
4. **SqliteSaver thread-safety**: `check_same_thread=False` requerido; REPL es
   single-thread, riesgo bajo.
