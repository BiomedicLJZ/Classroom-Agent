# tests/test_cli.py
import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

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


async def _async_iter(items):
    for item in items:
        yield item

def _factory(mock_graph):
    """make_graph stand-in that always returns the same mock graph."""
    return lambda thinking, provider=None: mock_graph


def _run(mock_graph, prompts, confirms=()):
    """Drive run_repl: main inputs via PromptSession, y/N answers via input()."""
    from ta.cli import run_repl
    with patch("ta.cli.PromptSession") as mock_ps_cls, \
         patch("builtins.input", side_effect=list(confirms)):
        
        mock_ps = mock_ps_cls.return_value
        # prompt_async must be an AsyncMock returning our strings
        mock_ps.prompt_async = AsyncMock(side_effect=list(prompts))
        
        run_repl(_factory(mock_graph), CFG)


class TestRunRepl:
    def test_exits_without_calling_graph(self):
        mock_graph = MagicMock()
        _run(mock_graph, ["exit"])
        mock_graph.astream.assert_not_called()

    def test_sends_user_message_and_uses_both_stream_modes(self):
        mock_graph = MagicMock()
        mock_graph.astream.return_value = _async_iter(
            [_update({"agent": {"messages": [AIMessage(content="Courses listed!")]}})]
        )
        _run(mock_graph, ["list courses", "exit"])
        args, kwargs = mock_graph.astream.call_args
        assert args[0]["messages"][0].content == "list courses"
        assert kwargs["stream_mode"] == ["messages", "updates"]

    def test_streams_reasoning_before_answer(self, capsys):
        mock_graph = MagicMock()
        mock_graph.astream.return_value = _async_iter([
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
        mock_graph.astream.return_value = _async_iter([
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
        mock_graph.astream.return_value = _async_iter([
            _chunk(text="UNIQUE42"),
            _update({"agent": {"messages": [AIMessage(content="UNIQUE42")]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert out.count("UNIQUE42") == 1

    def test_unstreamed_ai_update_is_printed_as_fallback(self, capsys):
        mock_graph = MagicMock()
        mock_graph.astream.return_value = _async_iter([
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
        mock_graph.astream.return_value = _async_iter([
            _update({"agent": {"messages": [ai_with_tool]}}),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "list_courses" in out
        assert "⚙" in out

    def test_subagent_tokens_tagged(self, capsys):
        mock_graph = MagicMock()
        mock_graph.astream.return_value = _async_iter([
            _chunk(text="SUBTOKEN", node="tools"),
        ])
        _run(mock_graph, ["hi", "exit"])
        out = capsys.readouterr().out
        assert "SUBTOKEN" in out
        assert "[tools]" in out

    def test_interrupt_yes_resumes_with_true(self):
        mock_graph = MagicMock()
        mock_graph.astream.side_effect = [
            _async_iter([_update({"__interrupt__": [MagicMock(
                value={"action": "post_announcement", "details": "Post?"}, id="intr-1"
            )]})]),
            _async_iter([_update({"agent": {"messages": [AIMessage(content="Posted.")]}})]),
        ]
        _run(mock_graph, ["post it", "exit"], confirms=["y"])
        cmd = mock_graph.astream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"intr-1": True}

    def test_interrupt_no_resumes_with_false(self):
        mock_graph = MagicMock()
        mock_graph.astream.side_effect = [
            _async_iter([_update({"__interrupt__": [MagicMock(
                value={"action": "post_grade", "details": "Post?"}, id="intr-2"
            )]})]),
            _async_iter([_update({"agent": {"messages": [AIMessage(content="Cancelled.")]}})]),
        ]
        _run(mock_graph, ["grade", "exit"], confirms=["n"])
        cmd = mock_graph.astream.call_args_list[1][0][0]
        assert isinstance(cmd, Command) and cmd.resume == {"intr-2": False}

    def test_multiple_interrupts_confirm_all(self):
        mock_graph = MagicMock()
        mock_graph.astream.side_effect = [
            _async_iter([_update({"__interrupt__": [
                MagicMock(value={"action": "post_grade", "details": "A"}, id="i1"),
                MagicMock(value={"action": "post_grade", "details": "B"}, id="i2"),
            ]})]),
            _async_iter([_update({"agent": {"messages": [AIMessage(content="Done.")]}})]),
        ]
        _run(mock_graph, ["grade all", "exit"], confirms=["y"])
        cmd = mock_graph.astream.call_args_list[1][0][0]
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


class TestDefensiveStream:
    def test_non_tuple_stream_items_do_not_crash(self, capsys):
        class Bad:  # not a (mode, payload) tuple; not iterable
            pass

        mock_graph = MagicMock()
        mock_graph.astream.return_value = _async_iter([
            ("messages", Bad()),   # bad payload inside messages mode
            Bad(),                  # bad top-level item (the Overwrite case)
            _chunk(text="OKTOKEN"),
        ])
        _run(mock_graph, ["switch to uniat", "exit"])
        out = capsys.readouterr().out
        assert "OKTOKEN" in out
        assert "Error:" not in out  # no crash surfaced


class TestIdsAndAccounts:
    def test_render_ids_prints_full_raw_id(self, capsys):
        from ta import cli
        svc = MagicMock()
        svc.courses().list().execute.return_value = {
            "courses": [{"id": "866213548099", "name": "IA", "section": "X"}]
        }
        with patch("ta.tools.classroom._classroom_service", return_value=svc):
            cli.render_ids("")
        out = capsys.readouterr().out
        assert "866213548099" in out  # full 12-digit ID, never abbreviated

    def test_render_accounts_lists_when_no_alias(self, capsys):
        from ta import cli
        acct = MagicMock()
        acct.client_secret_path = "credentials/x.json"
        with patch("ta.tools.accounts.Settings") as mock_settings:
            mock_settings.return_value.accounts = {"cugdl": acct, "uniat": acct}
            cli.render_accounts("")
        out = capsys.readouterr().out
        assert "cugdl" in out and "uniat" in out

    def test_ids_command_does_not_call_graph(self):
        mock_graph = MagicMock()
        with patch("ta.cli.render_ids") as r:
            _run(mock_graph, ["/ids", "exit"])
        mock_graph.stream.assert_not_called()
        r.assert_called_once()

    def test_account_command_does_not_call_graph(self):
        mock_graph = MagicMock()
        with patch("ta.cli.render_accounts") as r:
            _run(mock_graph, ["/account uniat", "exit"])
        mock_graph.stream.assert_not_called()
        r.assert_called_once_with(" uniat")


class TestSlashCompleter:
    def _complete(self, text):
        from prompt_toolkit.completion import CompleteEvent
        from prompt_toolkit.document import Document

        from ta.cli import SlashCompleter
        doc = Document(text, len(text))
        return [c.text for c in SlashCompleter().get_completions(doc, CompleteEvent())]

    def test_suggests_think_commands(self):
        texts = self._complete("/th")
        assert "/think on" in texts and "/think off" in texts

    def test_suggests_help(self):
        assert "/help" in self._complete("/he")

    def test_suggests_modules_after_help(self):
        assert "grading" in self._complete("/help gr")

    def test_suggests_ids_and_account(self):
        texts = self._complete("/")
        assert "/ids" in texts and "/account" in texts

    def test_suggests_account_aliases(self):
        with patch("ta.config.Settings.accounts", new_callable=PropertyMock) as mock_accounts:
            mock_accounts.return_value = {"cugdl": MagicMock(), "uniat": MagicMock()}
            assert "uniat" in self._complete("/account un")

    def test_no_completion_for_plain_text(self):
        assert self._complete("list my courses") == []


class TestHelp:
    def test_general_help_lists_modules_and_commands(self, capsys):
        from ta.cli import render_help
        render_help("")
        out = capsys.readouterr().out
        assert "grading" in out and "/think" in out and "/help" in out

    def test_module_help_detail(self, capsys):
        from ta.cli import render_help
        render_help("grading")
        out = capsys.readouterr().out.lower()
        assert "rubric" in out or "grade" in out

    def test_unknown_module(self, capsys):
        from ta.cli import render_help
        render_help("zzz")
        out = capsys.readouterr().out.lower()
        assert "unknown" in out


class TestHelpCommand:
    def test_help_command_does_not_call_graph(self, capsys):
        mock_graph = MagicMock()
        _run(mock_graph, ["/help", "exit"])
        mock_graph.stream.assert_not_called()
        assert "grading" in capsys.readouterr().out


class TestThinkToggle:
    def test_think_off_rebuilds_graph_and_routes_next_turn(self):
        built = []

        def make_graph(thinking, provider=None):
            g = MagicMock()
            g.thinking = thinking
            g.astream.return_value = _async_iter([])
            built.append(g)
            return g

        from ta.cli import run_repl
        with patch("ta.cli.PromptSession") as mock_ps_cls, \
             patch("builtins.input", side_effect=[]):
            mock_ps = mock_ps_cls.return_value
            mock_ps.prompt_async = AsyncMock(side_effect=["/think off", "hola", "exit"])
            run_repl(make_graph, CFG, initial_thinking=True)

        assert [g.thinking for g in built] == [True, False]
        built[0].astream.assert_not_called()
        built[1].astream.assert_called_once()
