# tests/test_cli.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from langgraph.types import Command


class TestRunRepl:
    def test_exits_without_calling_graph(self):
        mock_graph = MagicMock()
        with patch("builtins.input", side_effect=["exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        mock_graph.stream.assert_not_called()

    def test_sends_user_message_to_graph(self):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([{"agent": {"messages": [AIMessage(content="Courses listed!")]}}])
        with patch("builtins.input", side_effect=["list courses", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        state_input = mock_graph.stream.call_args[0][0]
        assert state_input["messages"][0].content == "list courses"

    def test_interrupt_yes_resumes_with_true(self):
        mock_graph = MagicMock()
        interrupt_chunk = {
            "__interrupt__": [MagicMock(
                value={"action": "post_announcement", "details": "Post?"}, id="intr-1"
            )]
        }
        resume_chunk = {"agent": {"messages": [AIMessage(content="Posted.")]}}
        mock_graph.stream.side_effect = [iter([interrupt_chunk]), iter([resume_chunk])]
        with patch("builtins.input", side_effect=["post it", "y", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"intr-1": True}

    def test_interrupt_no_resumes_with_false(self):
        mock_graph = MagicMock()
        mock_graph.stream.side_effect = [
            iter([{"__interrupt__": [MagicMock(
                value={"action": "post_grade", "details": "Post?"}, id="intr-2"
            )]}]),
            iter([{"agent": {"messages": [AIMessage(content="Cancelled.")]}}]),
        ]
        with patch("builtins.input", side_effect=["grade", "n", "exit"]):
            from ta.cli import run_repl
            run_repl(mock_graph, {"configurable": {"thread_id": "t"}})
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"intr-2": False}
