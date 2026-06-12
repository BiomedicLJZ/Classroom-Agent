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
    for node_name, node_update in chunk.items():
        if node_name.startswith("__") or not isinstance(node_update, dict):
            continue
        for msg in node_update.get("messages", []):
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
                for chunk in graph.stream(stream_input, config, stream_mode="updates"):
                    if "__interrupt__" in chunk:
                        got_interrupt = True
                        interrupts = chunk["__interrupt__"]
                        resume_values: dict = {}
                        if len(interrupts) == 1:
                            intr = interrupts[0]
                            data = intr.value
                            console.print("\n[bold yellow]⚠ CONFIRMATION REQUIRED[/bold yellow]")
                            console.print(f"[yellow]Action:[/yellow] {data.get('action', '')}")
                            console.print(f"[yellow]Details:[/yellow]\n{data.get('details', '')}")
                            confirmed = input("\nProceed? [y/N]: ").strip().lower() == "y"
                            resume_values = {intr.id: confirmed}
                        else:
                            console.print(
                                f"\n[bold yellow]⚠ {len(interrupts)} CONFIRMATIONS REQUIRED[/bold yellow]"
                            )
                            for i, intr in enumerate(interrupts, 1):
                                d = intr.value
                                console.print(
                                    f"  [dim]{i}.[/dim] [yellow]{d.get('action', '')}[/yellow] — "
                                    f"{d.get('details', '')[:80]}"
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
                                    console.print(
                                        f"\n[yellow]Action:[/yellow] {d.get('action', '')}"
                                    )
                                    console.print(
                                        f"[yellow]Details:[/yellow] {d.get('details', '')}"
                                    )
                                    ok = input("Proceed? [y/N]: ").strip().lower() == "y"
                                    resume_values[intr.id] = ok
                            else:
                                resume_values = {intr.id: False for intr in interrupts}
                        stream_input = Command(resume=resume_values)
                        break  # close the paused generator; restart with Command
                    else:
                        _print_chunk(chunk)
                if not got_interrupt:
                    break  # no interrupt this round — turn is complete
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
