from packages.agent_core.tools import format_tool_output, parse_actions, truncate


def test_parses_bash_patch_view_and_finish_in_order():
    text = (
        "Let me look first.\n"
        "VIEW src/app.py 10 20\n"
        "```bash\necho hi\n```\n"
        "```diff\n--- a/x.py\n+++ b/x.py\n@@\n```\n"
        "FINISH: done fixing\n"
        "```bash\necho after-finish\n```\n"
    )
    actions, finished = parse_actions(text)
    assert finished
    kinds = [action.kind for action in actions]
    assert kinds == ["view", "bash", "patch", "finish"]
    view = actions[0]
    assert view.payload == "src/app.py"
    assert view.start_line == 10 and view.end_line == 20
    assert actions[-1].payload == "done fixing"


def test_no_actions_returns_empty():
    actions, finished = parse_actions("I need more information.")
    assert actions == []
    assert not finished


def test_patch_preserves_context_whitespace_and_final_newline():
    patch = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,2 @@\n-old\n+new\n \n"
    actions, finished = parse_actions(f"```diff\n{patch}```")
    assert not finished
    assert actions[0].payload == patch


def test_patch_without_final_newline_is_normalized():
    patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-old\n+new"
    actions, _ = parse_actions(f"```diff\n{patch}```")
    assert actions[0].payload == patch + "\n"


def test_truncate_appends_marker():
    assert truncate("x" * 30, limit=10).endswith("字符]")


def test_format_tool_output_wraps_blocks():
    block = format_tool_output(2, [("run_bash", "exit=0\nhello")])
    assert '<tool_output round="2">' in block
    assert '<tool name="run_bash">' in block
    assert block.endswith("</tool_output>")
