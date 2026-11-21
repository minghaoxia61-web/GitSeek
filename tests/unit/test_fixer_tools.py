import pytest

from packages.agent_core.tools import format_tool_output, parse_actions, truncate


def test_parses_bash_patch_view_test_and_finish_in_order():
    text = (
        "Let me look first.\n"
        "VIEW src/app.py 10 20\n"
        "```bash\necho hi\n```\n"
        "```diff\n--- a/x.py\n+++ b/x.py\n@@\n```\n"
        "TEST python -m pytest -q\n"
        "FINISH: done fixing\n"
        "```bash\necho after-finish\n```\n"
        "VIEW ignored.py\nTEST false\nFINISH: ignored summary\n"
    )
    actions, finished = parse_actions(text)
    assert finished
    assert [action.kind for action in actions] == ["view", "bash", "patch", "test", "finish"]
    view = actions[0]
    assert view.payload == "src/app.py"
    assert view.start_line == 10 and view.end_line == 20
    assert actions[2].payload == "--- a/x.py\n+++ b/x.py\n@@\n"
    assert actions[3].payload == "python -m pytest -q"
    assert actions[-1].payload == "done fixing"
    assert [action.order for action in actions] == sorted(action.order for action in actions)
    assert text[actions[0].order:].startswith("VIEW src/app.py")
    assert text[actions[3].order:].startswith("TEST python")


@pytest.mark.parametrize("language,kind", [
    ("bash", "bash"), ("sh", "bash"), ("shell", "bash"),
    ("diff", "patch"), ("patch", "patch"),
    ("python", None), ("text", None), ("", None),
])
@pytest.mark.parametrize("fence", ["```", "````", "~~~"])
def test_protocol_lines_inside_any_fenced_block_are_not_actions(language, kind, fence):
    body = "FINISH: not done\nVIEW secret.py 1 2\nTEST false\n"
    text = f"{fence}{language}\n{body}{fence}\nVIEW real.py\nTEST pytest\nFINISH: real end"
    actions, finished = parse_actions(text)
    assert finished
    expected = ["view", "test", "finish"]
    if kind:
        expected.insert(0, kind)
        assert actions[0].payload == (body if kind == "patch" else body.strip())
    assert [action.kind for action in actions] == expected
    assert [action.payload for action in actions[-3:]] == ["real.py", "pytest", "real end"]


@pytest.mark.parametrize("language", ["bash", "diff", "python", ""])
def test_unclosed_fence_does_not_leak_protocol_lines(language):
    actions, finished = parse_actions(
        f"VIEW real.py\n```{language}\nFINISH: fake\nVIEW fake.py\nTEST false\n"
    )
    assert not finished
    assert [action.kind for action in actions] == ["view"]
    assert actions[0].payload == "real.py"


def test_nested_tool_fences_in_longer_documentation_fence_are_ignored():
    actions, finished = parse_actions(
        "````markdown\n```bash\ndangerous-command\n```\n"
        "FINISH: example\nVIEW example.py\nTEST example\n````\nTEST pytest"
    )
    assert not finished
    assert [(action.kind, action.payload) for action in actions] == [("test", "pytest")]


def test_inline_backticks_do_not_close_a_bash_fence():
    command = "printf '```'\nFINISH: still part of bash\nVIEW fake.py\nTEST false"
    actions, finished = parse_actions(f"```bash\n{command}\n```\nFINISH: real end")
    assert finished
    assert [action.kind for action in actions] == ["bash", "finish"]
    assert actions[0].payload == command


def test_bash_heredoc_protocol_lines_are_preserved_as_payload():
    command = "cat <<'EOF'\nVIEW a.py\nTEST false\nFINISH: sample\nEOF"
    actions, finished = parse_actions(f"```bash\n{command}\n```")
    assert not finished
    assert len(actions) == 1
    assert actions[0].kind == "bash" and actions[0].payload == command


def test_crlf_indentation_and_chinese_finish_separator():
    actions, finished = parse_actions(
        "  ```sh\r\ninspect\r\n  ```\r\n\tVIEW app.py 4\r\n"
        "  TEST python -m pytest 'tests/test app.py'\r\nFINISH： done\r\nTEST ignored\r\n"
    )
    assert finished
    assert [action.kind for action in actions] == ["bash", "view", "test", "finish"]
    assert actions[1].start_line == 4 and actions[1].end_line is None
    assert actions[2].payload == "python -m pytest 'tests/test app.py'"
    assert actions[-1].payload == "done"


@pytest.mark.parametrize("text", [
    "I need more information.", "TEST", "TEST   ", "VIEW\napp.py", "TEST\npytest",
    "Use TEST pytest to verify", "We can FINISH: done", "Use `VIEW file.py` here",
])
def test_prose_or_incomplete_protocol_returns_no_actions(text):
    actions, finished = parse_actions(text)
    assert actions == []
    assert not finished


def test_patch_payload_keeps_whitespace_and_final_newline_for_git_apply():
    patch = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new  \n"
    actions, finished = parse_actions(f"```diff\n{patch}```\n")
    assert not finished
    assert len(actions) == 1 and actions[0].payload == patch


def test_truncate_appends_marker():
    assert truncate("x" * 30, limit=10).endswith("字符]")
    assert truncate("short", limit=10) == "short"


def test_format_tool_output_wraps_blocks():
    block = format_tool_output(2, [("run_bash", "exit=0\nhello")])
    assert '<tool_output round="2">' in block
    assert '<tool name="run_bash">' in block
    assert block.endswith("</tool_output>")
