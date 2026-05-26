# ta/cli.py
from langchain_core.messages import HumanMessage
from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def _print_ai(content: str) -> None:
    console.print(Panel(
        Text(content, style="white"),
        title="[bold blue]TA Agent[/bold blue]",
        border_style="blue",
    ))


def _print_chunk(chunk: dict) -> None:
    for msg in chunk.get("messages", []):
        content = getattr(msg, "content", None)
        msg_type = getattr(msg, "type", None) or getattr(msg, "role", None)
        is_ai = msg_type in ("ai", "assistant")
        if is_ai and content and isinstance(content, str) and content.strip():
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
            # stream_input starts as the user message; becomes Command(resume=...) after each
            # interrupt so we can handle multiple consecutive confirmations in one turn.
            stream_input: dict | Command = {
                "messages": [HumanMessage(content=user_input)]
            }
            while True:
                got_interrupt = False
                for chunk in graph.stream(stream_input, config, stream_mode="values"):
                    if "__interrupt__" in chunk:
                        got_interrupt = True
                        data = chunk["__interrupt__"][0].value
                        console.print("\n[bold yellow]⚠ CONFIRMATION REQUIRED[/bold yellow]")
                        console.print(f"[yellow]Action:[/yellow] {data.get('action', '')}")
                        console.print(f"[yellow]Details:[/yellow]\n{data.get('details', '')}")
                        confirmed = input("\nProceed? [y/N]: ").strip().lower() == "y"
                        stream_input = Command(resume=confirmed)
                        break  # close the paused generator; restart with Command
                    else:
                        _print_chunk(chunk)
                if not got_interrupt:
                    break  # no interrupt this round — turn is complete
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
