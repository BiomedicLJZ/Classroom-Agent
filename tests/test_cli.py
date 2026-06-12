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
