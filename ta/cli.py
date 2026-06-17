# ta/cli.py
import asyncio
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

# Global lock to prevent background tasks from clobbering the console/Live display
_CONSOLE_LOCK = asyncio.Lock()


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
        self.any_output = False  # reasoning, answer, tool notice, or fallback shown
        self._answer_buf = ""
        self._answer_title = "💬 TA Agent"
        self._live: Live | None = None

    async def on_chunk(self, chunk: AIMessageChunk, metadata: dict | None) -> None:
        if not isinstance(chunk, AIMessageChunk):
            return
        node = (metadata or {}).get("langgraph_node", "")
        tag = "" if node in _MAIN_NODES else f"[{node}] "
        reasoning = _chunk_reasoning(chunk)
        if reasoning:
            self.any_output = True
            async with _CONSOLE_LOCK:
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
                async with _CONSOLE_LOCK:
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
            self.any_output = True
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

    async def finish(self) -> None:
        """Close any open stream section — call before prompts, notices, errors."""
        async with _CONSOLE_LOCK:
            self._close_current()


async def _handle_update_async(payload: dict, renderer: StreamRenderer) -> None:
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
                await renderer.finish()
                renderer.any_output = True
                async with _CONSOLE_LOCK:
                    console.print(f"⚙ {tc.get('name', '?')}...", style="dim", markup=False)
            content = getattr(msg, "content", None)
            if (
                not tool_calls
                and not renderer.streamed_answer
                and isinstance(content, str)
                and content.strip()
            ):
                await renderer.finish()
                renderer.any_output = True
                async with _CONSOLE_LOCK:
                    console.print(Panel(
                        _md(content), title=Text("💬 TA Agent", style="bold blue"),
                        title_align="left", border_style="blue", padding=(0, 1),
                    ))


async def _prompt_confirmations_async(interrupts) -> dict:
    """Collect y/N decisions for one or more pending interrupts asynchronously."""
    resume_values: dict = {}
    if len(interrupts) == 1:
        intr = interrupts[0]
        data = intr.value
        console.print("\n[bold yellow]⚠ CONFIRMATION REQUIRED[/bold yellow]")
        console.print(f"[yellow]Action:[/yellow] {data.get('action', '')}")
        console.print("[yellow]Details:[/yellow]")
        console.print(data.get("details", ""), markup=False, highlight=False)
        answer = await asyncio.to_thread(input, "\nProceed? [y/N]: ")
        confirmed = answer.strip().lower() == "y"
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
        choice = await asyncio.to_thread(input,
            f"\nConfirm all {len(interrupts)}? "
            "[y=all / n=cancel all / one=one-by-one]: "
        )
        choice = choice.strip().lower()
        if choice == "y":
            resume_values = {intr.id: True for intr in interrupts}
        elif choice == "one":
            for intr in interrupts:
                d = intr.value
                console.print(f"\nAction: {d.get('action', '')}", markup=False)
                console.print("Details:", markup=False)
                console.print(str(d.get("details", "")), markup=False, highlight=False)
                ok_answer = await asyncio.to_thread(input, "Proceed? [y/N]: ")
                ok = ok_answer.strip().lower() == "y"
                resume_values[intr.id] = ok
        else:
            resume_values = {intr.id: False for intr in interrupts}
    return resume_values


# Slash commands and the natural-language capability "modules" the agent exposes.
# Used for both autocomplete and /help.
_SLASH_COMMANDS = {
    "/help": "Show help; use /help <module> for a capability area",
    "/ids": "Show RAW Classroom IDs for the active account (/ids <course_id> for one)",
    "/account": "Show or switch Google account (/account <alias>)",
    "/provider": "Switch LLM provider (/provider <nvidia|google>)",
    "/think on": "Enable model reasoning (slower; shows raw thinking)",
    "/think off": "Disable model reasoning (faster)",
    "/reset": "Fully reset the conversation context",
    "/clear": "Clear conversation history (alias for /reset)",
    "/history show": "Show the messages list for the current thread",
    "/history clear": "Clear the messages list (alias for /reset)",
    "/compress": "Summarize conversation history and clear messages to save tokens",
    "/summarize": "Generate a summary of the current conversation and save to memory",
    "/memory show": "Show the active conversation memory/summary",
    "/memory set": "Manually set the memory summary (/memory set <text>)",
    "/memory clear": "Clear the memory summary",
    "/skills list": "List available skills/subagents",
    "/skills info": "Show detailed info for a skill (/skills info <name>)",
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
        "Switch between configured Google accounts.",
        'Ask: "switch to my other account" · "which account am I using"',
    ]),
}

_SKILL_DETAILS = {
    "grading_agent": {
        "title": "✅ Grading Agent",
        "description": "Batch-grades all TURNED_IN submissions for an assignment using a YAML rubric.",
        "tools": ["load_rubric", "analyze_submission", "get_drive_file_text", "get_submission_status", "get_submission", "list_students", "read_word_file", "read_excel_file", "read_pptx_file"],
        "prompt": "Evaluate student submissions against rubric criteria, outputting structured JSON grades and feedback. Highlights inline comments on Google Docs."
    },
    "content_agent": {
        "title": "📎 Content Agent",
        "description": "Creates teaching materials (lesson plans, study guides, slides, rubrics) and organizes files locally.",
        "tools": ["write_word_file", "append_to_word_file", "write_pptx_file", "write_excel_file", "append_excel_rows", "write_text_file", "write_notebook_file", "export_to_pdf", "read_notebook_file", "read_text_file", "list_office_files", "list_files", "read_word_file", "read_pptx_file", "read_excel_file", "setup_course_workspace", "get_workspace_resource_path", "list_workspace_contents", "load_syllabus", "upload_file_to_drive"],
        "prompt": "Takes rough ideas or syllabus objectives and expands them into complete academic artifacts (Word, Slides, PDF, Notebooks) in structured course directories."
    },
    "planning_agent": {
        "title": "🗂 Planning Agent",
        "description": "Maps out entire semesters (curriculum mapping) and synchronizes them with Google Classroom.",
        "tools": ["save_syllabus", "load_syllabus", "setup_course_workspace", "list_workspace_contents", "list_topics", "create_topic", "list_assignments", "create_assignment", "update_assignment", "post_announcement", "create_material", "upload_file_to_drive", "list_course_ids"],
        "prompt": "Generates week-by-week syllabus JSON structures, builds corresponding local course workspaces, and synchronizes them with Google Classroom topics and draft coursework."
    },
    "time_agent": {
        "title": "🕒 Time Agent",
        "description": "Manages Google Calendar and provides weekly briefings.",
        "tools": ["get_weekly_briefing", "list_calendar_events", "create_calendar_event", "list_course_ids", "list_assignments"],
        "prompt": "Compiles upcoming calendar events and Classroom coursework deadlines into cohesive weekly briefings and manages scheduling."
    }
}

async def generate_summary_for_messages(messages, existing_summary: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    from ta.tools.grading import _as_text, _get_llm
    
    llm = _get_llm()
    prompt = f"Current summary: {existing_summary}\n\nNew messages to integrate:\n"
    for m in messages[-20:]:
        role = getattr(m, "type", None) or getattr(m, "role", "unknown")
        content = getattr(m, "content", "")
        prompt += f"{role}: {content}\n"
        
    system_msg = SystemMessage(content="You are a memory manager. Create a concise summary of the conversation so far, integrating new information into the existing summary.")
    human_msg = HumanMessage(content=prompt)
    
    response = await asyncio.to_thread(llm.invoke, [system_msg, human_msg])
    return _as_text(response.content)

async def handle_history_command(graph, config, arg: str):
    arg = arg.strip().lower()
    if arg == "show" or not arg:
        state = await graph.aget_state(config)
        messages = state.values.get("messages", [])
        if not messages:
            console.print("[dim]No conversation history in this thread.[/dim]")
            return
        
        table = Table(title="💬 Conversation History", border_style="grey39", header_style="bold cyan")
        table.add_column("Role", style="bright_yellow", no_wrap=True)
        table.add_column("Message", style="white")
        
        for m in messages:
            role = getattr(m, "type", None) or getattr(m, "role", "unknown")
            content = getattr(m, "content", "")
            if isinstance(content, list):
                content = str(content)
            if len(content) > 300:
                content = content[:300] + "..."
            table.add_row(role.upper(), content)
        console.print(table)

async def handle_memory_command(graph, config, arg: str):
    parts = arg.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "show"
    val = parts[1] if len(parts) > 1 else ""
    
    if subcmd == "show" or not arg:
        state = await graph.aget_state(config)
        summary = state.values.get("summary", "")
        if not summary:
            console.print("[dim]Memory is currently empty.[/dim]")
        else:
            console.print(Panel(summary, title="🧠 Active Conversation Memory", border_style="blue"))
    elif subcmd == "set":
        if not val:
            console.print("[yellow]Usage: /memory set <text>[/yellow]")
            return
        await graph.aupdate_state(config, {"summary": val})
        console.print("[green]Memory summary updated manually.[/green]")
    elif subcmd == "clear":
        await graph.aupdate_state(config, {"summary": None})
        console.print("[green]Memory summary cleared.[/green]")
    else:
        console.print("[yellow]Unknown memory command. Use: /memory [show|set <text>|clear][/yellow]")

def handle_skills_command(arg: str):
    parts = arg.strip().split(maxsplit=1)
    subcmd = parts[0].lower() if parts else "list"
    val = parts[1].strip() if len(parts) > 1 else ""
    
    if subcmd == "list" or not arg:
        table = Table(title="🧩 Classroom Agent Skills (Subagents)", border_style="grey39", header_style="bold cyan")
        table.add_column("Skill Name", style="bright_yellow", no_wrap=True)
        table.add_column("Description", style="white")
        for name, info in _SKILL_DETAILS.items():
            table.add_row(name, info["description"])
        console.print(table)
        console.print("[dim]Use [bold]/skills info <name>[/bold] to see details, system prompts, and tools.[/dim]")
    elif subcmd == "info":
        if not val:
            console.print("[yellow]Usage: /skills info <skill_name>[/yellow]")
            return
        if val not in _SKILL_DETAILS:
            console.print(f"[yellow]Unknown skill '{val}'. Available: {list(_SKILL_DETAILS.keys())}[/yellow]")
            return
        info = _SKILL_DETAILS[val]
        console.print(Panel(
            f"[bold cyan]Description:[/bold cyan] {info['description']}\n\n"
            f"[bold cyan]Prompt Objective:[/bold cyan] {info['prompt']}\n\n"
            f"[bold cyan]Registered Tools:[/bold cyan] {', '.join(info['tools'])}",
            title=info["title"], border_style="cyan", padding=(1, 2)
        ))
    else:
        console.print("[yellow]Unknown skills command. Use: /skills [list|info <name>][/yellow]")


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
        if text.startswith("/account "):
            partial = text[len("/account "):].lstrip()
            from ta.config import Settings
            for account in Settings().accounts:
                if account.startswith(partial):
                    yield Completion(
                        account, start_position=-len(partial),
                        display=account, display_meta="account",
                    )
            return
        if text.startswith("/provider "):
            partial = text[len("/provider "):].lstrip()
            for p in ("nvidia", "google"):
                if p.startswith(partial):
                    yield Completion(
                        p, start_position=-len(partial),
                        display=p, display_meta="provider",
                    )
            return
        if text.startswith("/history "):
            partial = text[len("/history "):].lstrip()
            for sub in ("show", "clear"):
                if sub.startswith(partial):
                    yield Completion(
                        sub, start_position=-len(partial),
                        display=sub, display_meta="history subcommand"
                    )
            return
        if text.startswith("/memory "):
            partial = text[len("/memory "):].lstrip()
            if partial.startswith("set "):
                return
            for sub in ("show", "set", "clear"):
                if sub.startswith(partial):
                    yield Completion(
                        sub, start_position=-len(partial),
                        display=sub, display_meta="memory subcommand"
                    )
            return
        if text.startswith("/skills "):
            partial = text[len("/skills "):].lstrip()
            if partial.startswith("info "):
                subpartial = partial[5:].lstrip()
                for skill in ("grading_agent", "content_agent", "planning_agent", "time_agent"):
                    if skill.startswith(subpartial):
                        yield Completion(
                            skill, start_position=-len(subpartial),
                            display=skill, display_meta="skill name"
                        )
            else:
                for sub in ("list", "info"):
                    if sub.startswith(partial):
                        yield Completion(
                            sub, start_position=-len(partial),
                            display=sub, display_meta="skills subcommand"
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
        cid = c.get("id") or c.get("courseId") or "MISSING"
        table.add_row(str(cid), c.get("name", "Unnamed"), c.get("section", ""))
    console.print(table)
    console.print(
        "[dim]Use a Course ID above, or run /ids <course_id> for that course's "
        "students / assignments / topics.[/dim]"
    )


def render_ids(course_id: str = "") -> None:
    """Print RAW Classroom IDs for the active account, verbatim — bypasses the LLM
    so the IDs are never abbreviated. /ids → courses; /ids <id> → one course's
    students/assignments/topics."""
    from ta.tools.classroom import list_course_ids
    result = list_course_ids.func(course_id.strip())
    # Ensure raw output is clear and not formatted away
    console.print(Panel(
        Text(result), title=Text("🆔 Raw Classroom IDs", style="bold cyan"),
        title_align="left", border_style="cyan", padding=(1, 2),
    ))


def render_accounts(alias: str = "") -> None:
    """Show or switch the active Google account deterministically (no LLM). With an
    alias, switch and re-show that account's course IDs."""
    from ta.tools.accounts import list_accounts, switch_account
    alias = alias.strip().lower()
    if not alias:
        console.print(Panel(
            Text(list_accounts.func()), title=Text("🔑 Accounts", style="bold cyan"),
            title_align="left", border_style="cyan", padding=(0, 1),
        ))
        return
    msg = switch_account.func(alias)
    if msg.startswith("Unknown"):
        console.print(f"[yellow]{msg}[/yellow]")
        return
    console.print(f"[dim]{msg}[/dim]")
    render_startup_banner()


_thread_locks: dict[str, asyncio.Lock] = {}

def get_thread_lock(thread_id: str) -> asyncio.Lock:
    if thread_id not in _thread_locks:
        _thread_locks[thread_id] = asyncio.Lock()
    return _thread_locks[thread_id]

async def _run_agent_stream(graph, user_input: str, config: dict, is_background: bool):
    """Run the graph stream, handling interrupts and rendering."""
    thread_id = config["configurable"].get("thread_id", "default")
    lock = get_thread_lock(thread_id)
    
    if lock.locked():
        async with _CONSOLE_LOCK:
            console.print(f"[dim]Thread {thread_id} is busy. Waiting for current task to finish...[/dim]")
            
    async with lock:
        renderer = StreamRenderer()
        if is_background:
            renderer._answer_title = "💬 TA Agent (BG)"
            
        try:
            stream_input: dict | Command = {
                "messages": [HumanMessage(content=user_input)]
            }
            while True:
                got_interrupt = False
                
                async for item in graph.astream(stream_input, config, stream_mode=["messages", "updates"]):
                    if not (isinstance(item, tuple) and len(item) == 2):
                        continue
                    mode, payload = item
                    if mode == "messages":
                        if isinstance(payload, tuple) and len(payload) == 2:
                            await renderer.on_chunk(*payload)
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if "__interrupt__" in payload:
                        await renderer.finish()
                        got_interrupt = True
                        resume_values = await _prompt_confirmations_async(payload["__interrupt__"])
                        stream_input = Command(resume=resume_values)
                        break
                    await _handle_update_async(payload, renderer)
                if not got_interrupt:
                    break
            await renderer.finish()
            if not renderer.any_output:
                async with _CONSOLE_LOCK:
                    console.print(
                        "[dim](Model returned no output. This model needs reasoning "
                        "ON to act on multi-turn requests — type [bold]/think on[/bold] "
                        "or rephrase.)[/dim]"
                    )
        except Exception as exc:
            await renderer.finish()
            async with _CONSOLE_LOCK:
                console.print(f"[bold red]Error:[/bold red] {exc}")


async def run_repl_async(
    make_graph: Callable, config: dict, initial_thinking: bool = True,
    on_start: Callable | None = None,
) -> None:
    """Asynchronous Interactive REPL."""
    thinking = initial_thinking
    from ta.config import Settings
    from ta.session import get_active_account

    # Derived thread_id based on account and provider
    base_thread = config["configurable"].get("thread_id", "default")
    provider = Settings().llm_provider
    reset_counter = 0

    last_alias = get_active_account()

    def _get_config():
        nonlocal last_alias
        last_alias = get_active_account()
        if reset_counter > 0:
            tid = f"{base_thread}-{last_alias}-{provider}-reset{reset_counter}"
        else:
            tid = f"{base_thread}-{last_alias}-{provider}"
        return {"configurable": {"thread_id": tid}}

    current_config = _get_config()
    graph = make_graph(thinking, provider=provider)
    session = PromptSession(
        history=FileHistory(".ta_history"),
        completer=SlashCompleter(),
        complete_while_typing=True,
    )

    reasoning_state = "on" if initial_thinking else "off"
    console.print(Panel(
        "[bold green]Classroom TA Agent (Async)[/bold green] ready.\n"
        "Type your request and press Enter. Type [bold]exit[/bold] to quit.\n"
        "Answers render as rich Markdown (tables, code, links).\n"
        "Type [bold]/[/bold] for command autocomplete; [bold]/help[/bold] lists everything.\n"
        "Use [bold]/btw <request>[/bold] to run in background.\n"
        "[bold]/ids[/bold] shows raw course IDs; [bold]/account <alias>[/bold] switches "
        "Google account.\n"
        f"[bold]/think on|off[/bold] toggles model reasoning (now [bold]{reasoning_state}[/bold]); "
        "raw reasoning streams in grey when on.\n\n"
        "[dim]Context/Memory Commands:[/dim]\n"
        "  [bold]/reset[/bold] or [bold]/clear[/bold] · Fully reset conversation history\n"
        "  [bold]/history show[/bold] · Display thread message history table\n"
        "  [bold]/summarize[/bold] · Manually trigger LLM memory summarization\n"
        "  [bold]/compress[/bold] · Summarize current thread and roll over to a fresh thread\n"
        "  [bold]/memory [show|set <text>|clear][/bold] · Manage active agent memory\n"
        "  [bold]/skills [list|info <name>][/bold] · View agent capabilities and tools",
        title="Welcome", border_style="green",
    ))
    if on_start is not None:
        on_start()

    active_tasks = []

    while True:
        try:
            # Re-check if account changed (e.g. by a previous tool call)
            if get_active_account() != last_alias:
                current_config = _get_config()
                graph = make_graph(thinking, provider=provider)
                console.print(f"[dim]Sync: Account changed to {last_alias}. New thread: {current_config['configurable']['thread_id']}[/dim]")

            # Use prompt_async to keep the loop alive for background rendering
            user_input = await session.prompt_async("\n[You]: ")
            user_input = user_input.strip()
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
        if user_input.lower() == "/ids" or user_input.lower().startswith("/ids "):
            render_ids(user_input[len("/ids"):])
            continue
        if user_input.lower() == "/account" or user_input.lower().startswith("/account "):
            render_accounts(user_input[len("/account"):])
            # Update config and graph for isolated account history
            current_config = _get_config()
            graph = make_graph(thinking, provider=provider)
            console.print(f"[dim]Switched to isolated thread: [bold]{current_config['configurable']['thread_id']}[/bold][/dim]")
            continue
        if user_input.lower() in ("/think on", "/think off"):
            thinking = user_input.lower().endswith("on")
            graph = make_graph(thinking, provider=provider)
            console.print(
                f"[dim]Reasoning {'enabled' if thinking else 'disabled'}.[/dim]"
            )
            continue
        if user_input.lower() == "/provider" or user_input.lower().startswith("/provider "):
            p = user_input[len("/provider"):].strip().lower()
            if p in ("nvidia", "google"):
                provider = p
                current_config = _get_config()
                graph = make_graph(thinking, provider=provider)
                console.print(f"[dim]LLM Provider switched to {p.upper()}. Thread isolated.[/dim]")
                continue
            else:
                console.print("[yellow]Usage: /provider <nvidia|google>[/yellow]")
                continue
        if user_input.lower() in ("/reset", "/clear", "/history clear"):
            reset_counter += 1
            current_config = _get_config()
            graph = make_graph(thinking, provider=provider)
            console.print(f"[green]Conversation context reset. Started new clean thread: [bold]{current_config['configurable']['thread_id']}[/bold][/green]")
            continue
        if user_input.lower() == "/history" or user_input.lower().startswith("/history "):
            arg = user_input[8:].strip()
            if arg.lower() == "clear":
                reset_counter += 1
                current_config = _get_config()
                graph = make_graph(thinking, provider=provider)
                console.print(f"[green]Conversation history cleared. New thread: [bold]{current_config['configurable']['thread_id']}[/bold][/green]")
            else:
                await handle_history_command(graph, current_config, arg)
            continue
        if user_input.lower() == "/summarize":
            state = await graph.aget_state(current_config)
            messages = state.values.get("messages", [])
            if not messages:
                console.print("[yellow]No conversation history to summarize.[/yellow]")
            else:
                existing_summary = state.values.get("summary", "") or ""
                console.print("[dim]Summarizing conversation history...[/dim]")
                try:
                    summary = await generate_summary_for_messages(messages, existing_summary)
                    await graph.aupdate_state(current_config, {"summary": summary})
                    console.print(Panel(summary, title="🧠 New Summary Saved to Thread Memory", border_style="green"))
                except Exception as e:
                    console.print(f"[bold red]Summarization failed:[/bold red] {e}")
            continue
        if user_input.lower() == "/compress":
            state = await graph.aget_state(current_config)
            messages = state.values.get("messages", [])
            if not messages:
                console.print("[yellow]No conversation history to compress.[/yellow]")
            else:
                existing_summary = state.values.get("summary", "") or ""
                console.print("[dim]Summarizing and compressing conversation history...[/dim]")
                try:
                    summary = await generate_summary_for_messages(messages, existing_summary)
                    reset_counter += 1
                    current_config = _get_config()
                    graph = make_graph(thinking, provider=provider)
                    await graph.aupdate_state(current_config, {"summary": summary})
                    console.print(f"[green]Thread rolled over to clean state. Message history cleared.[/green]")
                    console.print(Panel(summary, title="🧠 Compressed Summary Carried Over to New Thread", border_style="green"))
                except Exception as e:
                    console.print(f"[bold red]Compression failed:[/bold red] {e}")
            continue
        if user_input.lower() == "/memory" or user_input.lower().startswith("/memory "):
            arg = user_input[7:].strip()
            await handle_memory_command(graph, current_config, arg)
            continue
        if user_input.lower() == "/skills" or user_input.lower().startswith("/skills "):
            arg = user_input[7:].strip()
            handle_skills_command(arg)
            continue

        is_background = user_input.lower().startswith("/btw ")
        if is_background:
            user_input = user_input[5:].strip()
            console.print("[dim]Background task started...[/dim]")

        # Run the agent stream in an async task
        task = asyncio.create_task(_run_agent_stream(
            graph, user_input, current_config, is_background
        ))
        
        if not is_background:
            await task
        else:
            active_tasks.append(task)
            # Cleanup finished tasks
            active_tasks = [t for t in active_tasks if not t.done()]

    # Cleanup background tasks on exit
    for task in active_tasks:
        task.cancel()


def run_repl(
    make_graph: Callable, config: dict, initial_thinking: bool = True,
    on_start: Callable | None = None,
) -> None:
    """Wrapper to launch the async REPL."""
    asyncio.run(run_repl_async(make_graph, config, initial_thinking, on_start))
