# TA Agent Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Nemotron 3 Ultra native reasoning, live token streaming with visible raw thinking in the CLI, a universal input-rewrite protocol, and expanded Classroom admin tools (edit/delete posts, topics, grade export).

**Architecture:** The LangGraph deep agent (`deepagents.create_deep_agent`) keeps its shape; `ChatNVIDIA` gains sampling + reasoning kwargs sourced from `Settings`. The CLI switches from `stream_mode="updates"` to `stream_mode=["messages", "updates"]` — "messages" drives a `StreamRenderer` (raw thinking dim grey, answer plain), "updates" keeps the `interrupt()` confirmation gate and emits tool notices. New Classroom tools follow the existing `@tool` + `_classroom_service` + `interrupt()` pattern.

**Tech Stack:** Python 3.13, LangGraph ≥1.2, deepagents ≥0.6.8, langchain-nvidia-ai-endpoints ≥1.4.0, google-api-python-client, rich, openpyxl, pytest.

**Spec:** `docs/superpowers/specs/2026-06-12-ta-agent-rework-design.md`

**Runner:** No uv.lock — use the project venv directly (Windows):
- Tests: `.venv\Scripts\python -m pytest <path> -v`
- Lint: `.venv\Scripts\python -m ruff check .`

---

### Task 0: Commit the uncommitted baseline

The working tree carries uncommitted work from a prior session (multi-account support, office tools, session state). Commit it as-is so subsequent task commits stay clean.

**Files:**
- Modify: none (git only)

- [ ] **Step 1: Run the full suite to record baseline state**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: all tests pass. If anything fails, note the failure in the commit message body — do NOT fix it in this task.

- [ ] **Step 2: Commit everything pending**

```bash
git add -A
git commit -m "feat: multi-account support, office tools, session state (pre-rework baseline)"
```

---

### Task 1: Reasoning settings in `Settings`

**Files:**
- Modify: `ta/config.py`
- Test: `tests/test_auth.py` (class `TestSettings`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_auth.py` inside `class TestSettings`:

```python
    def test_reasoning_defaults(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        settings = Settings()
        assert settings.nvidia_temperature == 1.0
        assert settings.nvidia_top_p == 0.95
        assert settings.nvidia_max_tokens == 16384
        assert settings.nvidia_reasoning_budget == 16384
        assert settings.nvidia_enable_thinking is True

    def test_reasoning_overridable_from_env(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setenv("NVIDIA_TEMPERATURE", "0.3")
        monkeypatch.setenv("NVIDIA_ENABLE_THINKING", "false")
        settings = Settings()
        assert settings.nvidia_temperature == 0.3
        assert settings.nvidia_enable_thinking is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py::TestSettings -v`
Expected: 2 new tests FAIL with `AttributeError: 'Settings' object has no attribute 'nvidia_temperature'`

- [ ] **Step 3: Implement the fields**

In `ta/config.py`, replace:

```python
    nvidia_api_key: str
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
```

with:

```python
    nvidia_api_key: str
    nvidia_model: str = "nvidia/nemotron-3-ultra-550b-a55b"
    nvidia_temperature: float = 1.0
    nvidia_top_p: float = 0.95
    nvidia_max_tokens: int = 16384
    nvidia_reasoning_budget: int = 16384
    nvidia_enable_thinking: bool = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/config.py tests/test_auth.py
git commit -m "feat: add Nemotron reasoning/sampling settings"
```

---

### Task 2: `build_agent` passes reasoning kwargs; legacy thinking prefixes removed

**Files:**
- Modify: `ta/agent.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_agent.py` inside `class TestBuildAgent`:

```python
    def test_llm_configured_with_reasoning(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        with patch("ta.agent.ChatNVIDIA") as mock_llm_cls, \
             patch("ta.agent.create_deep_agent") as mock_create:
            mock_llm_cls.return_value = MagicMock()
            mock_create.return_value = MagicMock()
            from ta.agent import build_agent
            from ta.config import Settings
            build_agent(Settings())
            kwargs = mock_llm_cls.call_args.kwargs
            assert kwargs["temperature"] == 1.0
            assert kwargs["top_p"] == 0.95
            assert kwargs["max_tokens"] == 16384
            assert kwargs["reasoning_budget"] == 16384
            assert kwargs["chat_template_kwargs"] == {"enable_thinking": True}

    def test_prompts_have_no_legacy_thinking_toggle(self):
        from ta.agent import _GRADING_SUBAGENT_PROMPT, SYSTEM_PROMPT
        assert "detailed thinking" not in SYSTEM_PROMPT.lower()
        assert "detailed thinking" not in _GRADING_SUBAGENT_PROMPT.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: `test_llm_configured_with_reasoning` FAILS with `KeyError: 'temperature'`; `test_prompts_have_no_legacy_thinking_toggle` FAILS on assert.

- [ ] **Step 3: Implement**

In `ta/agent.py`:

a) Replace line 61 (`llm = ChatNVIDIA(model=settings.nvidia_model, api_key=settings.nvidia_api_key)`) with:

```python
    llm = ChatNVIDIA(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        temperature=settings.nvidia_temperature,
        top_p=settings.nvidia_top_p,
        max_tokens=settings.nvidia_max_tokens,
        reasoning_budget=settings.nvidia_reasoning_budget,
        chat_template_kwargs={"enable_thinking": settings.nvidia_enable_thinking},
    )
```

b) In `SYSTEM_PROMPT`, change the first line `"""detailed thinking on` → `"""\` (the prompt then starts directly with "You are a Teaching Assistant...").

c) In `_GRADING_SUBAGENT_PROMPT`, change the first line `"""detailed thinking off` → `"""\` (starts directly with "You are a grading specialist...").

- [ ] **Step 4: Verify ChatNVIDIA accepts the kwargs (constructor smoke test, no network)**

Run:
```
.venv\Scripts\python -c "from langchain_nvidia_ai_endpoints import ChatNVIDIA; ChatNVIDIA(model='nvidia/nemotron-3-ultra-550b-a55b', api_key='nvapi-fake', temperature=1.0, top_p=0.95, max_tokens=16384, reasoning_budget=16384, chat_template_kwargs={'enable_thinking': True}); print('ok')"
```
Expected: `ok`.
**Fallback if pydantic rejects a kwarg:** pass the rejected ones through the payload instead — `ChatNVIDIA(..., extra_body={"reasoning_budget": ..., "chat_template_kwargs": {...}})` — and adjust the test assertions to check `extra_body`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add ta/agent.py tests/test_agent.py
git commit -m "feat: enable Nemotron 3 reasoning in main agent, drop legacy thinking toggles"
```

---

### Task 3: Grading LLM gets the same reasoning config; content-shape guard

**Files:**
- Modify: `ta/tools/grading.py`
- Create: `tests/test_grading.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_grading.py`:

```python
# tests/test_grading.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage


class TestGradingLLM:
    def test_get_llm_uses_reasoning_settings(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
        from ta.tools import grading
        grading._get_llm.cache_clear()
        with patch("ta.tools.grading.ChatNVIDIA") as mock_cls:
            mock_cls.return_value = MagicMock()
            grading._get_llm()
            kwargs = mock_cls.call_args.kwargs
            assert kwargs["temperature"] == 1.0
            assert kwargs["reasoning_budget"] == 16384
            assert kwargs["chat_template_kwargs"] == {"enable_thinking": True}
        grading._get_llm.cache_clear()

    def test_grading_prompt_no_legacy_toggle(self):
        from ta.tools.grading import GRADING_SYSTEM_PROMPT
        assert "detailed thinking" not in GRADING_SYSTEM_PROMPT.lower()

    def test_analyze_submission_handles_block_content(self):
        grade_json = '{"criteria_scores": {"Q": 5.0}, "score": 5.0, "max_score": 5.0, "feedback_text": "ok", "inline_comments": []}'
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = AIMessage(
            content=[{"type": "text", "text": grade_json}]
        )
        with patch("ta.tools.grading._get_llm", return_value=fake_llm):
            from ta.tools.grading import analyze_submission
            result = analyze_submission.func(
                submission_text="print('hi')", rubric_json="[]", assignment_type="code"
            )
        assert '"score": 5.0' in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py -v`
Expected: `test_get_llm_uses_reasoning_settings` FAILS (`KeyError: 'temperature'`), `test_grading_prompt_no_legacy_toggle` FAILS, `test_analyze_submission_handles_block_content` FAILS (TypeError — regex on list).

- [ ] **Step 3: Implement**

In `ta/tools/grading.py`:

a) Replace `_get_llm`:

```python
@lru_cache(maxsize=1)
def _get_llm():
    settings = Settings()
    return ChatNVIDIA(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        temperature=settings.nvidia_temperature,
        top_p=settings.nvidia_top_p,
        max_tokens=settings.nvidia_max_tokens,
        reasoning_budget=settings.nvidia_reasoning_budget,
        chat_template_kwargs={"enable_thinking": settings.nvidia_enable_thinking},
    )
```

b) In `GRADING_SYSTEM_PROMPT`, change the first line `"""detailed thinking off` → `"""\`.

c) Add below `_extract_json`:

```python
def _as_text(content) -> str:
    """Normalize LLM content to a string — newer providers may return content blocks."""
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return content or ""
```

d) In `analyze_submission`, replace `parsed = json.loads(_extract_json(response.content))` with:

```python
    parsed = json.loads(_extract_json(_as_text(response.content)))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/tools/grading.py tests/test_grading.py
git commit -m "feat: reasoning config for grading LLM, normalize block content"
```

---

### Task 4: CLI streaming — raw thinking + live tokens + preserved confirmations

**Files:**
- Modify: `ta/cli.py` (full rewrite below)
- Test: `tests/test_cli.py`

- [ ] **Step 1: Update existing tests to the tuple stream format and write new ones**

Replace the entire content of `tests/test_cli.py` with:

```python
# tests/test_cli.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command


def _chunk(text="", reasoning="", node="agent"):
    """Build a ('messages', (AIMessageChunk, metadata)) stream item."""
    kwargs = {"reasoning_content": reasoning} if reasoning else {}
    return (
        "messages",
        (AIMessageChunk(content=text, additional_kwargs=kwargs), {"langgraph_node": node}),
    )


def _update(payload):
    return ("updates", payload)


class TestRunRepl:
    def test_exits_without_calling_graph(self):
        mock_graph = MagicMock()
        with patch("builtins.input", side_effect=["exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        mock_graph.stream.assert_not_called()

    def test_sends_user_message_and_uses_both_stream_modes(self):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter(
            [_update({"agent": {"messages": [AIMessage(content="Courses listed!")]}})]
        )
        with patch("builtins.input", side_effect=["list courses", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        args, kwargs = mock_graph.stream.call_args
        assert args[0]["messages"][0].content == "list courses"
        assert kwargs["stream_mode"] == ["messages", "updates"]

    def test_streams_reasoning_before_answer(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(reasoning="THINKBIT"),
            _chunk(text="ANSWERBIT"),
        ])
        with patch("builtins.input", side_effect=["hi", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        out = capsys.readouterr().out
        assert "THINKBIT" in out
        assert "ANSWERBIT" in out
        assert out.index("THINKBIT") < out.index("ANSWERBIT")
        assert "thinking" in out

    def test_streamed_answer_not_reprinted_from_updates(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="UNIQUE42"),
            _update({"agent": {"messages": [AIMessage(content="UNIQUE42")]}}),
        ])
        with patch("builtins.input", side_effect=["hi", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        out = capsys.readouterr().out
        assert out.count("UNIQUE42") == 1

    def test_unstreamed_ai_update_is_printed_as_fallback(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _update({"agent": {"messages": [AIMessage(content="FALLBACK77")]}}),
        ])
        with patch("builtins.input", side_effect=["hi", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
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
        with patch("builtins.input", side_effect=["hi", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        out = capsys.readouterr().out
        assert "list_courses" in out
        assert "⚙" in out

    def test_subagent_tokens_tagged(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="SUBTOKEN", node="tools"),
        ])
        with patch("builtins.input", side_effect=["hi", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        out = capsys.readouterr().out
        assert "SUBTOKEN" in out
        assert "[tools]" in out

    def test_interrupt_yes_resumes_with_true(self):
        mock_graph = MagicMock()
        interrupt_item = _update({
            "__interrupt__": [MagicMock(
                value={"action": "post_announcement", "details": "Post?"}, id="intr-1"
            )]
        })
        resume_item = _update({"agent": {"messages": [AIMessage(content="Posted.")]}})
        mock_graph.stream.side_effect = [iter([interrupt_item]), iter([resume_item])]
        with patch("builtins.input", side_effect=["post it", "y", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
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
        with patch("builtins.input", side_effect=["grade", "n", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
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
        with patch("builtins.input", side_effect=["grade all", "y", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"i1": True, "i2": True}
```

- [ ] **Step 2: Run tests to verify the new ones fail**

Run: `.venv\Scripts\python -m pytest tests/test_cli.py -v`
Expected: `test_exits_without_calling_graph` passes; everything else FAILS (current code expects plain dict chunks, not tuples; no stream_mode list; no reasoning display).

- [ ] **Step 3: Rewrite `ta/cli.py`**

Replace the entire file content with:

```python
# ta/cli.py
from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command
from rich.console import Console
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
    """Live token display: raw thinking in dim grey first, answer plain after."""

    def __init__(self) -> None:
        self.section: str | None = None  # None | "thinking" | "answer"
        self.streamed_answer = False  # any answer tokens shown this turn

    def on_chunk(self, chunk: AIMessageChunk, metadata: dict | None) -> None:
        if not isinstance(chunk, AIMessageChunk):
            return
        node = (metadata or {}).get("langgraph_node", "")
        tag = "" if node in _MAIN_NODES else f"[{node}] "
        reasoning = _chunk_reasoning(chunk)
        if reasoning:
            self._enter_section("thinking", f"🧠 {tag}thinking", "bold magenta")
            console.print(
                reasoning, style="grey50 italic", end="",
                soft_wrap=True, markup=False, highlight=False,
            )
        text = _chunk_text(chunk)
        if text:
            self._enter_section("answer", f"💬 {tag}TA Agent", "bold blue")
            self.streamed_answer = True
            console.print(text, end="", soft_wrap=True, markup=False, highlight=False)

    def _enter_section(self, name: str, header: str, style: str) -> None:
        if self.section == name:
            return
        if self.section is not None:
            console.print()  # close the in-progress streamed line
        console.print(f"\n{header}", style=style, markup=False)
        self.section = name

    def finish(self) -> None:
        """Close any open stream section — call before prompts, notices, errors."""
        if self.section is not None:
            console.print()
        self.section = None


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
                console.print(content, markup=False, highlight=False)


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


def run_repl(graph, config: dict) -> None:
    """Run the interactive CLI REPL for the TA agent."""
    console.print(Panel(
        "[bold green]Classroom TA Agent[/bold green] ready.\n"
        "Type your request and press Enter. Type [bold]exit[/bold] to quit.\n"
        "Raw model reasoning streams in grey before each answer.\n\n"
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_cli.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/cli.py tests/test_cli.py
git commit -m "feat: live token streaming with visible raw reasoning in CLI"
```

---

### Task 5: REWRITE PROTOCOL in system prompt; confirmations show full text

**Files:**
- Modify: `ta/agent.py`, `ta/tools/classroom.py`
- Test: `tests/test_agent.py`, Create: `tests/test_classroom_admin.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_agent.py` in `class TestBuildAgent`:

```python
    def test_system_prompt_has_rewrite_protocol(self):
        from ta.agent import SYSTEM_PROMPT
        assert "REWRITE PROTOCOL" in SYSTEM_PROMPT
```

Create `tests/test_classroom_admin.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py::TestBuildAgent::test_system_prompt_has_rewrite_protocol tests/test_classroom_admin.py -v`
Expected: all 4 FAIL (no REWRITE PROTOCOL; details truncated/missing description).

- [ ] **Step 3: Implement**

a) In `ta/agent.py`, append to `SYSTEM_PROMPT` (before the closing `"""`):

```python

REWRITE PROTOCOL (applies to ALL student-facing text):
Never deliver instructor input verbatim. For every announcement, assignment title
and description, material description, grading feedback, and private comment:
1. Fix spelling, grammar, and punctuation.
2. Rewrite in a warm, professional instructor voice.
3. Structure it — assignments get learning objectives, step-by-step instructions,
   and submission criteria; announcements get short clear paragraphs or bullets.
4. Preserve the input language (Spanish stays Spanish, English stays English).
5. Expand rough notes into complete, polished content.
Deliver the improved version through the API tool; the confirmation gate shows the
full final text so the instructor approves with a single y/N.
NOTE: the Classroom API has no public comments on posts. For "comment on an
assignment" requests, offer post_private_comment per student or an announcement
referencing the assignment.
```

b) In `ta/tools/classroom.py` `post_announcement`, replace:

```python
    suffix = "..." if len(text) > 200 else ""
    confirmed = interrupt({
        "action": "post_announcement",
        "details": f"Post announcement to course {course_id}:\n\n{text[:200]}{suffix}",
    })
```

with:

```python
    confirmed = interrupt({
        "action": "post_announcement",
        "details": f"Post announcement to course {course_id}:\n\n{text}",
    })
```

c) In `create_assignment`, replace the interrupt block with:

```python
    confirmed = interrupt({
        "action": "create_assignment",
        "details": (
            f"Create assignment '{title}' in course {course_id}\n"
            f"Max points: {max_points}, Due: {due_date} {due_time}\n\n"
            f"Description:\n{description}"
        ),
    })
```

d) In `create_material`, replace the interrupt block with:

```python
    confirmed = interrupt({
        "action": "create_material",
        "details": (
            f"Post material '{title}' to course {course_id}\n\n"
            f"Description:\n{description}"
        ),
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py tests/test_classroom_admin.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/agent.py ta/tools/classroom.py tests/test_agent.py tests/test_classroom_admin.py
git commit -m "feat: universal rewrite protocol + full-text confirmation details"
```

---

### Task 6: `update_assignment` + `delete_assignment`

**Files:**
- Modify: `ta/tools/classroom.py`
- Test: `tests/test_classroom_admin.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_classroom_admin.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py -v`
Expected: new tests FAIL with `ImportError: cannot import name 'update_assignment'`.

- [ ] **Step 3: Implement in `ta/tools/classroom.py`** (append at end of file)

```python
@tool
def update_assignment(
    course_id: str,
    coursework_id: str,
    title: str = "",
    description: str = "",
    due_date: str = "",
    due_time: str = "",
    max_points: float = -1,
    state: str = "",
    topic_id: str = "",
) -> str:
    """Update fields of an existing assignment. Only provided (non-empty) fields change.
    due_date: YYYY-MM-DD. due_time: HH:MM (24h). state: PUBLISHED or DRAFT.
    topic_id: assign the coursework to a topic (see list_topics). Requires confirmation."""
    body: dict = {}
    mask: list[str] = []
    if title:
        body["title"] = title
        mask.append("title")
    if description:
        body["description"] = description
        mask.append("description")
    if due_date:
        year, month, day = map(int, due_date.split("-"))
        body["dueDate"] = {"year": year, "month": month, "day": day}
        mask.append("dueDate")
    if due_time:
        hour, minute = map(int, due_time.split(":"))
        body["dueTime"] = {"hours": hour, "minutes": minute}
        mask.append("dueTime")
    if max_points >= 0:
        body["maxPoints"] = max_points
        mask.append("maxPoints")
    if state:
        body["state"] = state.upper()
        mask.append("state")
    if topic_id:
        body["topicId"] = topic_id
        mask.append("topicId")
    if not mask:
        return "Nothing to update — provide at least one field."
    details = f"Update assignment {coursework_id} in course {course_id}\nFields: {', '.join(mask)}"
    if description:
        details += f"\n\nNew description:\n{description}"
    confirmed = interrupt({"action": "update_assignment", "details": details})
    if not confirmed:
        return "Assignment update cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = (
            svc.courses().courseWork()
            .patch(
                courseId=course_id, id=coursework_id,
                updateMask=",".join(mask), body=body,
            )
            .execute()
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"assignment {coursework_id}")
    return f"Assignment {result['id']} updated ({', '.join(mask)})."


@tool
def delete_assignment(course_id: str, coursework_id: str) -> str:
    """Permanently delete an assignment and its submissions. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_assignment",
        "details": f"PERMANENTLY delete assignment {coursework_id} from course {course_id}",
    })
    if not confirmed:
        return "Assignment deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.courses().courseWork().delete(courseId=course_id, id=coursework_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"assignment {coursework_id}")
    return f"Assignment {coursework_id} deleted."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/tools/classroom.py tests/test_classroom_admin.py
git commit -m "feat: update_assignment and delete_assignment tools"
```

---

### Task 7: Announcements & materials — list / update / delete

**Files:**
- Modify: `ta/tools/classroom.py`
- Test: `tests/test_classroom_admin.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_classroom_admin.py`:

```python
class TestAnnouncementAdmin:
    def test_list_announcements(self):
        svc = _service_mock()
        svc.courses().announcements().list().execute.return_value = {
            "announcements": [
                {"id": "a1", "state": "PUBLISHED", "text": "Hello class"},
            ]
        }
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import list_announcements
            result = list_announcements.func(course_id="c1")
        assert "a1" in result and "Hello class" in result

    def test_update_announcement_patches_text(self):
        svc = _service_mock()
        patch_call = svc.courses().announcements().patch
        patch_call().execute.return_value = {"id": "a1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import update_announcement
            update_announcement.func(course_id="c1", announcement_id="a1", text="New text")
        kwargs = patch_call.call_args.kwargs
        assert kwargs["updateMask"] == "text"
        assert kwargs["body"] == {"text": "New text"}

    def test_delete_announcement_cancelled(self):
        svc = _service_mock()
        with patch("ta.tools.classroom.interrupt", return_value=False), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import delete_announcement
            result = delete_announcement.func(course_id="c1", announcement_id="a1")
        assert "cancelled" in result.lower()
        svc.courses().announcements().delete.assert_not_called()


class TestMaterialAdmin:
    def test_list_materials(self):
        svc = _service_mock()
        svc.courses().courseWorkMaterials().list().execute.return_value = {
            "courseWorkMaterial": [
                {"id": "m1", "state": "PUBLISHED", "title": "Slides week 1"},
            ]
        }
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import list_materials
            result = list_materials.func(course_id="c1")
        assert "m1" in result and "Slides week 1" in result

    def test_update_material_patches_title_and_description(self):
        svc = _service_mock()
        patch_call = svc.courses().courseWorkMaterials().patch
        patch_call().execute.return_value = {"id": "m1"}
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import update_material
            update_material.func(
                course_id="c1", material_id="m1", title="T2", description="D2"
            )
        kwargs = patch_call.call_args.kwargs
        assert kwargs["updateMask"] == "title,description"
        assert kwargs["body"] == {"title": "T2", "description": "D2"}

    def test_delete_material_confirmed(self):
        svc = _service_mock()
        with patch("ta.tools.classroom.interrupt", return_value=True), \
             patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import delete_material
            result = delete_material.func(course_id="c1", material_id="m1")
        svc.courses().courseWorkMaterials().delete.assert_called_once_with(
            courseId="c1", id="m1"
        )
        assert "deleted" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py -v`
Expected: new tests FAIL with ImportError.

- [ ] **Step 3: Implement in `ta/tools/classroom.py`** (append; note the API quirk — the materials list response key is `courseWorkMaterial`, singular)

```python
@tool
def list_announcements(course_id: str) -> str:
    """List announcements in a course with their IDs, newest first."""
    svc = _classroom_service(get_active_account())
    try:
        response = svc.courses().announcements().list(
            courseId=course_id, orderBy="updateTime desc", pageSize=20
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    items = response.get("announcements", [])
    if not items:
        return f"No announcements in course {course_id}."
    lines = [
        f"- [{a['id']}] ({a.get('state', '?')}) {a.get('text', '')[:80]}" for a in items
    ]
    return f"Announcements ({len(lines)}):\n" + "\n".join(lines)


@tool
def update_announcement(
    course_id: str, announcement_id: str, text: str = "", state: str = ""
) -> str:
    """Update an announcement's text and/or state (PUBLISHED or DRAFT).
    Only provided (non-empty) fields change. Requires confirmation."""
    body: dict = {}
    mask: list[str] = []
    if text:
        body["text"] = text
        mask.append("text")
    if state:
        body["state"] = state.upper()
        mask.append("state")
    if not mask:
        return "Nothing to update — provide text and/or state."
    details = f"Update announcement {announcement_id} in course {course_id}"
    if text:
        details += f"\n\nNew text:\n{text}"
    confirmed = interrupt({"action": "update_announcement", "details": details})
    if not confirmed:
        return "Announcement update cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = (
            svc.courses().announcements()
            .patch(
                courseId=course_id, id=announcement_id,
                updateMask=",".join(mask), body=body,
            )
            .execute()
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"announcement {announcement_id}")
    return f"Announcement {result['id']} updated."


@tool
def delete_announcement(course_id: str, announcement_id: str) -> str:
    """Permanently delete an announcement. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_announcement",
        "details": f"PERMANENTLY delete announcement {announcement_id} from course {course_id}",
    })
    if not confirmed:
        return "Announcement deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.courses().announcements().delete(courseId=course_id, id=announcement_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"announcement {announcement_id}")
    return f"Announcement {announcement_id} deleted."


@tool
def list_materials(course_id: str) -> str:
    """List courseWork materials in a course with their IDs."""
    svc = _classroom_service(get_active_account())
    try:
        response = svc.courses().courseWorkMaterials().list(
            courseId=course_id, pageSize=20
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    items = response.get("courseWorkMaterial", [])
    if not items:
        return f"No materials in course {course_id}."
    lines = [
        f"- [{m['id']}] ({m.get('state', '?')}) {m.get('title', 'Untitled')}" for m in items
    ]
    return f"Materials ({len(lines)}):\n" + "\n".join(lines)


@tool
def update_material(
    course_id: str, material_id: str, title: str = "", description: str = ""
) -> str:
    """Update a material's title and/or description. Only provided (non-empty)
    fields change. Requires confirmation."""
    body: dict = {}
    mask: list[str] = []
    if title:
        body["title"] = title
        mask.append("title")
    if description:
        body["description"] = description
        mask.append("description")
    if not mask:
        return "Nothing to update — provide title and/or description."
    details = f"Update material {material_id} in course {course_id}"
    if description:
        details += f"\n\nNew description:\n{description}"
    confirmed = interrupt({"action": "update_material", "details": details})
    if not confirmed:
        return "Material update cancelled."
    svc = _classroom_service(get_active_account())
    try:
        result = (
            svc.courses().courseWorkMaterials()
            .patch(
                courseId=course_id, id=material_id,
                updateMask=",".join(mask), body=body,
            )
            .execute()
        )
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"material {material_id}")
    return f"Material {result['id']} updated."


@tool
def delete_material(course_id: str, material_id: str) -> str:
    """Permanently delete a courseWork material. Requires confirmation."""
    confirmed = interrupt({
        "action": "delete_material",
        "details": f"PERMANENTLY delete material {material_id} from course {course_id}",
    })
    if not confirmed:
        return "Material deletion cancelled."
    svc = _classroom_service(get_active_account())
    try:
        svc.courses().courseWorkMaterials().delete(courseId=course_id, id=material_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id, resource=f"material {material_id}")
    return f"Material {material_id} deleted."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/tools/classroom.py tests/test_classroom_admin.py
git commit -m "feat: announcement and material list/update/delete tools"
```

---

### Task 8: Topics — list / create

**Files:**
- Modify: `ta/tools/classroom.py`
- Test: `tests/test_classroom_admin.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_classroom_admin.py`:

```python
class TestTopics:
    def test_list_topics(self):
        svc = _service_mock()
        svc.courses().topics().list().execute.return_value = {
            "topic": [{"topicId": "t1", "name": "Unit 1"}]
        }
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import list_topics
            result = list_topics.func(course_id="c1")
        assert "t1" in result and "Unit 1" in result

    def test_create_topic(self):
        svc = _service_mock()
        svc.courses().topics().create().execute.return_value = {
            "topicId": "t2", "name": "Unit 2"
        }
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.classroom import create_topic
            result = create_topic.func(course_id="c1", name="Unit 2")
        create_kwargs = svc.courses().topics().create.call_args.kwargs
        assert create_kwargs["courseId"] == "c1"
        assert create_kwargs["body"] == {"name": "Unit 2"}
        assert "t2" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py::TestTopics -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement in `ta/tools/classroom.py`** (append; topics list response key is `topic`, singular)

```python
@tool
def list_topics(course_id: str) -> str:
    """List topics in a course (topicId + name). Use topicId with update_assignment
    to organize coursework under a topic."""
    svc = _classroom_service(get_active_account())
    try:
        response = svc.courses().topics().list(courseId=course_id).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    topics = response.get("topic", [])
    if not topics:
        return f"No topics in course {course_id}."
    lines = [f"- [{t['topicId']}] {t.get('name', 'Unnamed')}" for t in topics]
    return f"Topics ({len(lines)}):\n" + "\n".join(lines)


@tool
def create_topic(course_id: str, name: str) -> str:
    """Create a new topic in a course. Low-risk — no confirmation required."""
    svc = _classroom_service(get_active_account())
    try:
        result = svc.courses().topics().create(
            courseId=course_id, body={"name": name}
        ).execute()
    except HttpError as exc:
        return _http_error_msg(exc, course_id=course_id)
    return f"Topic created: [{result['topicId']}] {result['name']}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_classroom_admin.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/tools/classroom.py tests/test_classroom_admin.py
git commit -m "feat: topic list/create tools"
```

---

### Task 9: `export_grades` to Excel

**Files:**
- Modify: `ta/tools/grading.py`
- Test: `tests/test_grading.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_grading.py`:

```python
class TestExportGrades:
    def test_exports_matrix_to_xlsx(self, tmp_path):
        svc = MagicMock()
        svc.courses().students().list().execute.return_value = {
            "students": [
                {
                    "userId": "s1",
                    "profile": {
                        "name": {"fullName": "Ana López"},
                        "emailAddress": "ana@school.mx",
                    },
                },
                {
                    "userId": "s2",
                    "profile": {
                        "name": {"fullName": "Beto Ruiz"},
                        "emailAddress": "beto@school.mx",
                    },
                },
            ]
        }
        svc.courses().courseWork().list().execute.return_value = {
            "courseWork": [{"id": "w1", "title": "HW1"}, {"id": "w2", "title": "HW2"}]
        }
        svc.courses().courseWork().studentSubmissions().list().execute.side_effect = [
            {"studentSubmissions": [
                {"userId": "s1", "assignedGrade": 9.5},
                {"userId": "s2"},  # ungraded
            ]},
            {"studentSubmissions": [
                {"userId": "s1", "assignedGrade": 8.0},
                {"userId": "s2", "assignedGrade": 10.0},
            ]},
        ]
        out = tmp_path / "grades.xlsx"
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            from ta.tools.grading import export_grades
            result = export_grades.func(course_id="c1", output_path=str(out))

        assert out.exists()
        from openpyxl import load_workbook
        ws = load_workbook(out)["Grades"]
        rows = list(ws.values)
        assert rows[0] == ("Student", "Email", "HW1", "HW2")
        assert rows[1] == ("Ana López", "ana@school.mx", 9.5, 8.0)
        assert rows[2] == ("Beto Ruiz", "beto@school.mx", None, 10.0)
        assert "2 students" in result
```

Note: write ungraded cells as `None` (not `""`) so the read-back is `None` and the spreadsheet stays clean.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py::TestExportGrades -v`
Expected: FAIL with ImportError.

- [ ] **Step 3: Implement in `ta/tools/grading.py`** (append at end)

```python
@tool
def export_grades(course_id: str, output_path: str) -> str:
    """Export all grades for a course to an .xlsx file: one row per student, one
    column per assignment, cell = assignedGrade (empty when not graded yet)."""
    from openpyxl import Workbook

    from ta.tools.classroom import _classroom_service

    svc = _classroom_service(get_active_account())
    roster = svc.courses().students().list(courseId=course_id).execute().get("students", [])
    coursework = (
        svc.courses().courseWork().list(courseId=course_id).execute().get("courseWork", [])
    )
    if not roster:
        return f"No students in course {course_id}."
    if not coursework:
        return f"No coursework in course {course_id}."

    grades: dict[str, dict[str, float]] = {}
    for cw in coursework:
        subs = (
            svc.courses().courseWork().studentSubmissions()
            .list(courseId=course_id, courseWorkId=cw["id"])
            .execute()
            .get("studentSubmissions", [])
        )
        for sub in subs:
            if "assignedGrade" in sub:
                grades.setdefault(sub["userId"], {})[cw["id"]] = sub["assignedGrade"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Grades"
    ws.append(["Student", "Email"] + [cw.get("title", cw["id"]) for cw in coursework])
    for student in roster:
        profile = student.get("profile", {})
        row = [
            profile.get("name", {}).get("fullName", "Unknown"),
            profile.get("emailAddress", ""),
        ]
        student_grades = grades.get(student["userId"], {})
        row += [student_grades.get(cw["id"]) for cw in coursework]
        ws.append(row)
    wb.save(output_path)
    return (
        f"Grades exported: {len(roster)} students × {len(coursework)} assignments "
        f"→ {output_path}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_grading.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/tools/grading.py tests/test_grading.py
git commit -m "feat: export_grades tool — course grade matrix to xlsx"
```

---

### Task 10: Register all new tools in `ALL_TOOLS`

**Files:**
- Modify: `ta/tools/__init__.py`
- Test: `tests/test_agent.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_agent.py`, replace `test_all_tools_registered` and `test_minimum_tool_count` with:

```python
    def test_all_tools_registered(self):
        from ta.tools import ALL_TOOLS
        names = [t.name for t in ALL_TOOLS]
        for expected in [
            "list_courses", "post_announcement", "create_assignment",
            "get_submission_status", "analyze_submission", "batch_grade_assignment",
            "load_rubric", "post_grade", "get_drive_file_text", "get_doc_text",
            "add_doc_comment",
            # rework additions
            "update_assignment", "delete_assignment",
            "list_announcements", "update_announcement", "delete_announcement",
            "list_materials", "update_material", "delete_material",
            "list_topics", "create_topic", "export_grades",
        ]:
            assert expected in names, f"Missing tool: {expected}"

    def test_minimum_tool_count(self):
        from ta.tools import ALL_TOOLS
        assert len(ALL_TOOLS) >= 43
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_agent.py -v`
Expected: `test_all_tools_registered` FAILS (`Missing tool: update_assignment`).

- [ ] **Step 3: Implement in `ta/tools/__init__.py`**

Extend the classroom import to:

```python
from ta.tools.classroom import (
    create_assignment,
    create_material,
    create_topic,
    delete_announcement,
    delete_assignment,
    delete_invitation,
    delete_material,
    get_submission,
    get_submission_status,
    invite_user,
    list_announcements,
    list_assignments,
    list_courses,
    list_invitations,
    list_materials,
    list_students,
    list_topics,
    post_announcement,
    update_announcement,
    update_assignment,
    update_material,
)
```

Extend the grading import to include `export_grades`:

```python
from ta.tools.grading import (
    analyze_submission,
    batch_grade_assignment,
    export_grades,
    load_rubric,
    post_grade,
    post_private_comment,
)
```

In `ALL_TOOLS`, after the `# Classroom — write (confirmation required)` group entries, add:

```python
    # Classroom — admin (rework)
    update_assignment,
    delete_assignment,
    list_announcements,
    update_announcement,
    delete_announcement,
    list_materials,
    update_material,
    delete_material,
    list_topics,
    create_topic,
```

and in the `# Grading` group add `export_grades,` after `post_grade,`.

- [ ] **Step 4: Run full suite**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/tools/__init__.py tests/test_agent.py
git commit -m "feat: register admin and export tools in ALL_TOOLS"
```

---

### Task 11: OAuth scopes for topics and materials

**Files:**
- Modify: `ta/google_auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_auth.py` (new class at the end):

```python
class TestScopes:
    def test_scopes_include_topics_and_materials(self):
        assert "https://www.googleapis.com/auth/classroom.topics" in SCOPES
        assert "https://www.googleapis.com/auth/classroom.courseworkmaterials" in SCOPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py::TestScopes -v`
Expected: FAIL on assert.

- [ ] **Step 3: Implement in `ta/google_auth.py`**

Add two entries to `SCOPES` (after the announcements scope):

```python
    "https://www.googleapis.com/auth/classroom.topics",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python -m pytest tests/test_auth.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add ta/google_auth.py tests/test_auth.py
git commit -m "feat: add topics and courseworkmaterials OAuth scopes"
```

---

### Task 12: README re-auth note, full verification, optional live smoke test

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document re-auth + new features in README**

Append to `README.md`:

```markdown
## Re-authentication required (June 2026 rework)

The agent now requests two additional OAuth scopes (`classroom.topics`,
`classroom.courseworkmaterials`). Existing tokens are missing them — Classroom
calls will fail with 403 until you re-authenticate:

1. Delete `credentials/token.json` (and `credentials/uniat_token.json` if present).
2. Run the agent; the browser consent flow will re-run once per account.

## Reasoning & streaming

- Nemotron 3 Ultra thinking is ON by default. Raw reasoning streams in dim grey
  before each answer. Tune via `.env`: `NVIDIA_TEMPERATURE`, `NVIDIA_TOP_P`,
  `NVIDIA_MAX_TOKENS`, `NVIDIA_REASONING_BUDGET`, `NVIDIA_ENABLE_THINKING`.
- Every student-facing text you type is improved/rewritten before posting; the
  confirmation prompt shows the full final text.
```

- [ ] **Step 2: Full suite + lint**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: ALL PASS

Run: `.venv\Scripts\python -m ruff check .`
Expected: no errors (fix any reported issue before committing).

- [ ] **Step 3: Optional live smoke test (real NVIDIA call — requires network + .env key; run manually)**

```
.venv\Scripts\python -c "from ta.config import Settings; from langchain_nvidia_ai_endpoints import ChatNVIDIA; s = Settings(); llm = ChatNVIDIA(model=s.nvidia_model, api_key=s.nvidia_api_key, temperature=s.nvidia_temperature, top_p=s.nvidia_top_p, max_tokens=512, reasoning_budget=256, chat_template_kwargs={'enable_thinking': True}); [print(repr(c.additional_kwargs.get('reasoning_content')), '|', repr(c.content)) for c in llm.stream('Say hi in one word')]"
```

Expected: early chunks show reasoning text in the first column, later chunks show the answer in the second. **If reasoning arrives in a different shape** (e.g. typed content blocks), `_chunk_reasoning` in `ta/cli.py` already handles dict-block lists — verify the displayed output, and only adjust `_chunk_reasoning` if both paths miss it.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: re-auth instructions and reasoning/streaming notes"
```

---

## Spec coverage map

| Spec section | Tasks |
|---|---|
| 1. Modelo con razonamiento | 1, 2, 3 |
| 2. Streaming CLI | 4 |
| 3. Reescritura universal | 5 |
| 4. Herramientas admin + scopes | 6, 7, 8, 9, 10, 11 |
| 5. Tests | every task (TDD) |
| Riesgo 1 (chunk shape) | 4 (defensive parser), 12 (live smoke) |
| Riesgo 2 (re-auth) | 11, 12 |
