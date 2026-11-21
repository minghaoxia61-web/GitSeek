"""Parsing of model replies into scaffold actions (mini-SWE-agent style, bash-first).

Bash fences execute, diff fences patch, ``VIEW`` lines peek at files, and ``TEST`` lines
select final verification. ``FINISH:`` requests verification; later text is ignored.
"""

import re
from dataclasses import dataclass

FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")
VIEW_LINE_RE = re.compile(r"^[ \t]*VIEW[ \t]+(\S+)(?:[ \t]+(\d+)(?:[ \t]+(\d+))?)?[ \t]*$")
TEST_LINE_RE = re.compile(r"^[ \t]*TEST[ \t]+(\S.*)$")
FINISH_RE = re.compile(r"^[ \t]*FINISH[:：][ \t]*(.*)$")

OUTPUT_CHAR_LIMIT = 4000


@dataclass(frozen=True)
class AgentAction:
    kind: str  # "bash" | "patch" | "view" | "test" | "finish"
    payload: str = ""
    start_line: int | None = None
    end_line: int | None = None
    order: int = 0


def parse_actions(text: str) -> tuple[list[AgentAction], bool]:
    """Return ordered actions; anything after the FINISH line is ignored."""
    found: list[AgentAction] = []
    fence = ""
    language = ""
    body: list[str] = []
    fence_order = 0
    offset = 0
    tool_languages = {
        "bash": "bash", "sh": "bash", "shell": "bash", "diff": "patch", "patch": "patch",
    }

    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        order = offset
        offset += len(raw_line)
        fence_match = FENCE_RE.fullmatch(line)
        if fence:
            if (
                fence_match
                and fence_match.group(1)[0] == fence[0]
                and len(fence_match.group(1)) >= len(fence)
                and not fence_match.group(2).strip()
            ):
                if language in tool_languages:
                    kind = tool_languages[language]
                    payload = "".join(body)
                    found.append(AgentAction(
                        kind=kind,
                        payload=payload if kind == "patch" else payload.strip(),
                        order=fence_order,
                    ))
                fence = ""
            else:
                body.append(raw_line)
            continue
        if fence_match:
            fence = fence_match.group(1)
            language = fence_match.group(2).strip()
            body = []
            fence_order = order
            continue

        # Code samples, including unknown or unclosed fences, cannot issue protocol actions.
        if match := FINISH_RE.fullmatch(line):
            found.append(AgentAction(kind="finish", payload=match.group(1).strip(), order=order))
            return found, True
        if match := VIEW_LINE_RE.fullmatch(line):
            found.append(AgentAction(
                kind="view",
                payload=match.group(1),
                start_line=int(match.group(2)) if match.group(2) else None,
                end_line=int(match.group(3)) if match.group(3) else None,
                order=order,
            ))
        elif match := TEST_LINE_RE.fullmatch(line):
            found.append(AgentAction(kind="test", payload=match.group(1).strip(), order=order))

    return found, False


def truncate(text: str, limit: int = OUTPUT_CHAR_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n… [输出截断，共 {len(text)} 字符]"


def format_tool_output(round_no: int, outputs: list[tuple[str, str]]) -> str:
    """Build the user-side tool-result block consumed by the next model turn."""
    parts = [f"<tool_output round=\"{round_no}\">"]
    for tool, output in outputs:
        parts.append(f'<tool name="{tool}">\n{truncate(output)}\n</tool>')
    parts.append("</tool_output>")
    return "\n".join(parts)
