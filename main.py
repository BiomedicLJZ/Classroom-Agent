# main.py
import argparse
import asyncio
from datetime import date

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from ta.agent import build_agent
from ta.cli import render_startup_banner, run_repl_async
from ta.config import Settings
from ta.google_auth import get_credentials
from ta.session import get_active_account

async def main_async():
    parser = argparse.ArgumentParser(description="Classroom TA Agent")
    parser.add_argument(
        "--thread",
        default=f"cli-{date.today().isoformat()}",
        help="Conversation thread id (default: one per day, resumes within the day)",
    )
    args = parser.parse_args()

    settings = Settings()
    get_credentials(get_active_account())

    async with aiosqlite.connect("checkpoints.db") as conn:
        checkpointer = AsyncSqliteSaver(conn)

        def make_graph(thinking: bool, provider: str | None = None):
            return build_agent(settings, checkpointer=checkpointer, enable_thinking=thinking, provider=provider)

        await run_repl_async(
            make_graph,
            {"configurable": {"thread_id": args.thread}},
            initial_thinking=settings.nvidia_enable_thinking,
            on_start=render_startup_banner,
        )

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()

