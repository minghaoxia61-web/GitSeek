"""Parsing of model replies into scaffold actions (mini-SWE-agent style, bash-first).

The tool space is deliberately tiny: bash fences execute, diff fences patch, ``VIEW`` lines
peek at files, and a ``FINISH:`` line ends the loop. Everything else is treated as prose.
"""

import re
from dataclasses import dataclass

BASH_BLOCK_RE = re.compile(r"```[ \t]*(?:bash|sh|shell)[ \t]*\r?\n(.*?)```", re.DOTALL)
PATCH_BLOCK_RE = re.compile(r"```[ \t]*(?:diff|patch)[ \t]*\r?\n(.*?)```", re.DOTALL)
VIEW_LINE_RE = re.compile(r"^[ \t]*VIEW\s+([^\s]+)(?:[ \t]+(\d+)[ \t]+(\d+))?[ \t]*$", re.MULTILINE)
FINISH_RE = re.compile(r"^[ \t]*FINISH[:：][ \t]*(.*)$", re.MULTILINE)

OUTPUT_CHAR_LIMIT = 4000


@dataclass(frozen=True)
class AgentAction:
    kind: str  # "bash" | "patch" | "view" | "finish"
    payload: str = ""
    start_line: int | None = None
    end_line: int | None = None
    order: int = 0


def parse_actions(text: str) -> tuple[list[AgentAction], bool]:
    """Return ordered actions; anything after the FINISH line is ignored."""
    found: list[AgentAction] = []

    def collect(regex: re.Pattern[str], kind: str) -> None:
        for match in regex.finditer(text):
            action = AgentAction(kind=kind, payload=match.group(1).strip(), order=match.start())
            found.append(action)

    collect(BASH_BLOCK_RE, "bash")
    collect(PATCH_BLOCK_RE, "patch")
    for match in VIEW_LINE_RE.finditer(text):
        start = int(match.group(2)) if match.group(2) else None
        end = int(match.group(3)) if match.group(3) else None
        action = AgentAction(
            kind="view",
            payload=match.group(1),
            start_line=start,
            end_line=end,
            order=match.start(),
        )
        found.append(action)

    finish_match = FINISH_RE.search(text)
    finished = finish_match is not None
    if finish_match:
        found = [action for action in found if action.order < finish_match.start()]
        finish = AgentAction(
            kind="finish",
            payload=finish_match.group(1).strip(),
            order=finish_match.start(),
        )
        found.append(finish)

    found.sort(key=lambda action: action.order)
    return found, finished


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
