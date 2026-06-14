# main.py
import argparse
import sqlite3
from datetime import date

from langgraph.checkpoint.sqlite import SqliteSaver

from ta.agent import build_agent
from ta.cli import render_startup_banner, run_repl
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
        on_start=render_startup_banner,
    )


if __name__ == "__main__":
    main()
