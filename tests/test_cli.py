# tests/test_cli.py
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Command

CFG = {"configurable": {"thread_id": "t"}}


def _chunk(text="", reasoning="", node="agent"):
    """Build a ('messages', (AIMessageChunk, metadata)) stream item."""
    kwargs = {"reasoning_content": reasoning} if reasoning else {}
    return (
        "messages",
        (AIMessageChunk(content=text, additional_kwargs=kwargs), {"langgraph_node": node}),
    )


def _update(payload):
    return ("updates", payload)


def _factory(mock_graph):
    """make_graph stand-in that always returns the same mock graph."""
    return lambda thinking: mock_graph


def _run(mock_graph, prompts, confirms=()):
    """Drive run_repl: main inputs via PromptSession, y/N answers via input()."""
    from ta.cli import run_repl
    with patch("ta.cli.PromptSession") as mock_ps, \
         patch("builtins.input", side_effect=list(confirms)):
        mock_ps.return_value.prompt.side_effect = list(prompts)
        run_repl(_factory(mock_graph), CFG)


class TestRunRepl:
    def test_exits_without_calling_graph(self):
        mock_graph = MagicMock()
        _run(mock_graph, ["exit"])
        mock_graph.stream.assert_not_called()

    def test_sends_user_message_and_uses_both_stream_modes(self):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter(
            [_update({"agent": {"messages": [AIMessage(content="Courses listed!")]}})]
        )
        _run(mock_graph, ["list courses", "exit"])
        args, kwargs = mock_graph.stream.call_args
        assert args[0]["messages"][0].content == "list courses"
        assert kwargs["stream_mode"] == ["messages", "updates"]

    def test_streams_reasoning_before_answer(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(reasoning="THINKBIT"),
            _chunk(text="ANSWERBIT"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "THINKBIT" in out
        assert "ANSWERBIT" in out
        assert out.index("THINKBIT") < out.index("ANSWERBIT")
        assert "thinking" in out

    def test_answer_markdown_table_renders_with_borders(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="| Curso | Alumnos |\n"),
            _chunk(text="| --- | --- |\n"),
            _chunk(text="| IA101 | 30 |\n"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "IA101" in out and "30" in out
        assert "│" in out or "─" in out  # box-drawing glyphs from the table render

    def test_streamed_answer_not_reprinted_from_updates(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="UNIQUE42"),
            _update({"agent": {"messages": [AIMessage(content="UNIQUE42")]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert out.count("UNIQUE42") == 1

    def test_unstreamed_ai_update_is_printed_as_fallback(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _update({"agent": {"messages": [AIMessage(content="FALLBACK77")]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
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
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "list_courses" in out
        assert "⚙" in out

    def test_subagent_tokens_tagged(self, capsys):
        mock_graph = MagicMock()
        mock_graph.stream.return_value = iter([
            _chunk(text="SUBTOKEN", node="tools"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "SUBTOKEN" in out
        assert "[tools]" in out

    def test_interrupt_yes_resumes_with_true(self):
        mock_graph = MagicMock()
        mock_graph.stream.side_effect = [
            iter([_update({"__interrupt__": [MagicMock(
                value={"action": "post_announcement", "details": "Post?"}, id="intr-1"
            )]})]),
            iter([_update({"agent": {"messages": [AIMessage(content="Posted.")]}})]),
        ]
        _run(mock_graph, ["post it", "exit"], confirms=["y"])
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
        _run(mock_graph, ["grade", "exit"], confirms=["n"])
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
        _run(mock_graph, ["grade all", "exit"], confirms=["y"])
        cmd = mock_graph.stream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"i1": True, "i2": True}


class TestStartupBanner:
    def test_render_startup_banner_lists_courses(self, capsys):
        from ta import cli
        svc = MagicMock()
        svc.courses().list().execute.return_value = {
            "courses": [{"id": "C9", "name": "IA", "section": "B"}]
        }
        with patch("ta.tools.classroom._classroom_service", return_value=svc), \
             patch("ta.session.get_active_account", return_value="cugdl"):
            cli.render_startup_banner()
        out = capsys.readouterr().out
        assert "C9" in out and "IA" in out

    def test_render_startup_banner_degrades_on_error(self, capsys):
        from ta import cli
        with patch("ta.tools.classroom._classroom_service",
                   side_effect=RuntimeError("no creds")):
            cli.render_startup_banner()  # must not raise
        out = capsys.readouterr().out
        assert "Could not load courses" in out


class TestThinkToggle:
    def test_think_off_rebuilds_graph_and_routes_next_turn(self):
        built = []

        def make_graph(thinking):
            g = MagicMock()
            g.thinking = thinking
            g.stream.return_value = iter([])
            built.append(g)
            return g

        from ta.cli import run_repl
        with patch("ta.cli.PromptSession") as mock_ps, \
             patch("builtins.input", side_effect=[]):
            mock_ps.return_value.prompt.side_effect = ["/think off", "hola", "exit"]
            run_repl(make_graph, CFG, initial_thinking=True)

        assert [g.thinking for g in built] == [True, False]
        built[0].stream.assert_not_called()
        built[1].stream.assert_called_once()
