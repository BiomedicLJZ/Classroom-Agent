# ta/cli.py
import contextlib
import sys
from collections.abc import Callable

from langchain_core.messages import AIMessageChunk, HumanMessage
from langgraph.types import Command
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# Higher-contrast Markdown palette for the terminal: coloured headings, bright
# inline code, underlined links, subtle rules. Code blocks use the monokai theme
# (set per-Markdown below).
_THEME = Theme({
    "markdown.h1": "bold bright_white on grey23",
    "markdown.h2": "bold bright_cyan",
    "markdown.h3": "bold cyan",
    "markdown.h4": "bold blue",
    "markdown.item.bullet": "bold yellow",
    "markdown.item.number": "bold yellow",
    "markdown.link": "underline bright_blue",
    "markdown.link_url": "blue",
    "markdown.code": "bold bright_green on grey15",
    "markdown.block_quote": "italic grey70",
    "markdown.hr": "grey39",
    "repr.url": "underline bright_blue",
})

# Render emoji / box-drawing on legacy Windows code pages (cp1252) instead of
# raising UnicodeEncodeError. Must run before the Console reads the stream encoding.
with contextlib.suppress(AttributeError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

console = Console(theme=_THEME)

# Node names of the main deep-agent loop; anything else (subagents, tool-internal
# LLM calls) gets a visible [node] tag so the instructor knows who is talking.
_MAIN_NODES = {"agent", "model"}


def _md(text: str) -> Markdown:
    """Markdown with syntax-highlighted code blocks and clickable links."""
    return Markdown(
        text, code_theme="monokai", inline_code_theme="monokai", hyperlinks=True
    )


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
        self._answer_title = "💬 TA Agent"
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
                self.section = "answer"
                self._answer_buf = ""
                self._answer_title = f"💬 {tag}TA Agent"
                self._live = Live(
                    self._answer_panel(), console=console,
                    refresh_per_second=8, vertical_overflow="visible",
                )
                self._live.start()
            self.streamed_answer = True
            self._answer_buf += text
            if self._live is not None:
                self._live.update(self._answer_panel())

    def _answer_panel(self) -> Panel:
        return Panel(
            _md(self._answer_buf),
            title=Text(self._answer_title, style="bold blue"),
            title_align="left",
            border_style="blue",
            padding=(0, 1),
        )

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
                console.print(Panel(
                    _md(content), title=Text("💬 TA Agent", style="bold blue"),
                    title_align="left", border_style="blue", padding=(0, 1),
                ))


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


# Slash commands and the natural-language capability "modules" the agent exposes.
# Used for both autocomplete and /help.
_SLASH_COMMANDS = {
    "/help": "Show help; use /help <module> for a capability area",
    "/think on": "Enable model reasoning (slower; shows raw thinking)",
    "/think off": "Disable model reasoning (faster)",
}

_MODULE_HELP: dict[str, tuple[str, list[str]]] = {
    "courses": ("📚 Courses", [
        "See every course with its ID, or dump one course's object IDs.",
        'Ask: "list my courses" · "list IDs for course 9202"',
    ]),
    "roster": ("🎓 Roster", [
        "List students, invite users, manage pending invitations.",
        'Ask: "who is in course 9202" · "invite ana@x.mx as student to 9202"',
    ]),
    "assignments": ("📝 Assignments", [
        "Create / update / delete assignments and check submission status.",
        'Ask: "create an assignment about linked lists due Friday in 9202"',
    ]),
    "announcements": ("📢 Announcements", [
        "Post / edit / delete announcements (DRAFT by default; can schedule).",
        'Ask: "announce the midterm is next Friday 10am in 9202"',
    ]),
    "materials": ("📎 Materials", [
        "Post / edit / delete study materials (Drive files, links, videos).",
        'Ask: "post the slides drive:<id> to course 9202"',
    ]),
    "topics": ("🗂 Topics", [
        "List or create topics to organize the class stream.",
        'Ask: "create a topic \'Unit 3\' in 9202"',
    ]),
    "grading": ("✅ Grading", [
        "Grade submissions against a YAML rubric, post grades with Drive feedback,",
        "export grades to xlsx, or bulk-import grades from xlsx.",
        'Ask: "grade assignment 987 in 9202 with rubric rubrics/hw1.yaml"',
    ]),
    "drive": ("📁 Drive & Docs", [
        "Read submitted files, comment on Google Docs, upload files.",
        'Ask: "read the file drive:<id>"',
    ]),
    "office": ("📊 Office files", [
        "Read/write local .docx, .xlsx and .pptx for reports and bulk actions.",
        'Ask: "invite every student in D:/roster.xlsx to course 9202"',
    ]),
    "accounts": ("🔑 Accounts", [
        "Switch between the cugdl and uniat Google accounts.",
        'Ask: "switch to uniat" · "which account am I using"',
    ]),
}


class SlashCompleter(Completer):
    """Autocomplete for slash commands. After '/help ' it completes module names."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        if text.startswith("/help "):
            partial = text[len("/help "):].lstrip()
            for module in _MODULE_HELP:
                if module.startswith(partial):
                    yield Completion(
                        module, start_position=-len(partial),
                        display=module, display_meta="help topic",
                    )
            return
        for cmd, desc in _SLASH_COMMANDS.items():
            if cmd.startswith(text):
                yield Completion(
                    cmd, start_position=-len(text), display=cmd, display_meta=desc
                )


def render_help(arg: str = "") -> None:
    """Render help. Empty arg → slash commands + capability modules; a module name →
    that module's detail; anything else → an 'unknown topic' note."""
    arg = arg.strip().lower()
    if arg:
        if arg not in _MODULE_HELP:
            console.print(
                f"[yellow]Unknown help topic '{arg}'.[/yellow] "
                f"Available: {', '.join(_MODULE_HELP)}"
            )
            return
        title, lines = _MODULE_HELP[arg]
        console.print(Panel(
            _md("\n".join(lines)), title=Text(title, style="bold cyan"),
            title_align="left", border_style="cyan", padding=(0, 1),
        ))
        return

    cmd_table = Table(
        title="⌨ Slash commands", title_style="bold green",
        border_style="grey39", header_style="bold cyan",
    )
    cmd_table.add_column("Command", style="bright_yellow", no_wrap=True)
    cmd_table.add_column("What it does", style="white")
    for cmd, desc in _SLASH_COMMANDS.items():
        cmd_table.add_row(cmd, desc)
    cmd_table.add_row("exit", "Quit the agent")
    console.print(cmd_table)

    mod_table = Table(
        title="🧩 Capability modules — /help <module> for detail",
        title_style="bold green", border_style="grey39", header_style="bold cyan",
    )
    mod_table.add_column("Module", style="bright_yellow", no_wrap=True)
    mod_table.add_column("Summary", style="white")
    for module, (_title, lines) in _MODULE_HELP.items():
        mod_table.add_row(module, lines[0])
    console.print(mod_table)
    console.print(
        "[dim]Type what you want in plain language — the agent resolves IDs and "
        "drafts content for you.[/dim]"
    )


def render_startup_banner() -> None:
    """Best-effort: list the active account's courses with their IDs at launch so
    the instructor always has the IDs handy. Silently degrades on any error."""
    try:
        from ta.session import get_active_account
        from ta.tools.classroom import _classroom_service, _collect_pages
        svc = _classroom_service(get_active_account())
        courses = _collect_pages(
            lambda tok: svc.courses().list(courseStates=["ACTIVE"], pageToken=tok),
            "courses",
        )
    except Exception as exc:  # noqa: BLE001 — banner is non-critical
        console.print(f"[dim]Could not load courses: {exc}[/dim]")
        return
    if not courses:
        console.print("[dim]No active courses found for the current account.[/dim]")
        return
    table = Table(
        title="📚 Your active courses", title_style="bold green",
        border_style="grey39", header_style="bold cyan", expand=False,
    )
    table.add_column("Course ID", style="bright_yellow", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Section", style="grey70")
    for c in courses:
        table.add_row(str(c.get("id", "")), c.get("name", "Unnamed"), c.get("section", ""))
    console.print(table)
    console.print(
        "[dim]Use a Course ID above, or ask me to list IDs for a course to get "
        "students / assignments / topics.[/dim]"
    )


def run_repl(
    make_graph: Callable, config: dict, initial_thinking: bool = True,
    on_start: Callable | None = None,
) -> None:
    """Interactive REPL. make_graph(thinking: bool) builds the agent graph — the
    /think command rebuilds it against the same checkpointer, so the conversation
    thread continues with reasoning toggled. on_start() runs once after the welcome
    panel (used to show the course-ID banner)."""
    thinking = initial_thinking
    graph = make_graph(thinking)
    session = PromptSession(
        history=FileHistory(".ta_history"),
        completer=SlashCompleter(),
        complete_while_typing=True,
    )

    reasoning_state = "on" if initial_thinking else "off"
    console.print(Panel(
        "[bold green]Classroom TA Agent[/bold green] ready.\n"
        "Type your request and press Enter. Type [bold]exit[/bold] to quit.\n"
        "Answers render as rich Markdown (tables, code, links).\n"
        "Type [bold]/[/bold] for command autocomplete; [bold]/help[/bold] lists everything "
        "([bold]/help <module>[/bold] for detail).\n"
        f"[bold]/think on|off[/bold] toggles model reasoning (now [bold]{reasoning_state}[/bold]); "
        "raw reasoning streams in grey when on.\n\n"
        "[dim]Examples:[/dim]\n"
        "  List my courses\n"
        "  Grade all submissions for assignment 987 using rubric rubrics/hw1.yaml\n"
        "  Post announcement: 'Midterm next Friday at 10am'",
        title="Welcome", border_style="green",
    ))
    if on_start is not None:
        on_start()

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
        if user_input.lower() == "/help" or user_input.lower().startswith("/help "):
            render_help(user_input[len("/help"):])
            continue
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
