# main.py
import uuid

from ta.agent import build_agent
from ta.cli import run_repl
from ta.config import Settings
from ta.google_auth import get_credentials


def main() -> None:
    settings = Settings()
    get_credentials(settings.google_client_secret_path, settings.google_token_path)
    graph = build_agent(settings)
    run_repl(graph, {"configurable": {"thread_id": str(uuid.uuid4())}})


if __name__ == "__main__":
    main()
