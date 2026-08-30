"""Tree-sitter based Python chunking for the fixer-agent code index.

Falls back to a line-based scanner when tree-sitter is unavailable, so ingestion and tests
keep working in minimal environments.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_LINES = 300
MAX_FILE_BYTES = 200_000
MAX_REPO_CHUNKS = 3000

SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", "dist", "build",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".eggs",
}

try:  # pragma: no cover - exercised implicitly by dependency presence
    import tree_sitter_python
    from tree_sitter import Language, Parser

    _PARSER: "Parser | None" = Parser(Language(tree_sitter_python.language()))
except (ImportError, OSError):  # pragma: no cover
    _PARSER = None


@dataclass(frozen=True)
class CodeChunk:
    path: str
    name: str
    kind: str  # "function" | "class" | "module"
    start_line: int
    end_line: int
    content: str

    @property
    def summary(self) -> str:
        return chunk_summary(self.content)


def chunk_summary(content: str) -> str:
    """First docstring line, else the first meaningful code line."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    in_triple = False
    for line in lines[1:8] if len(lines) > 1 else lines:
        stripped = line
        if not in_triple and (stripped.startswith('"""') or stripped.startswith("'''")):
            quote = stripped[:3]
            inner = stripped[3:]
            if inner.endswith(quote) and len(inner) >= 3:
                inner = inner[:-3]
            inner = inner.strip()
            if inner:
                return inner[:200]
            in_triple = True
            continue
        if in_triple:
            if quote in stripped:
                in_triple = False
                inner = stripped.split(quote)[0].strip()
                if inner:
                    return inner[:200]
                continue
            inner = stripped.strip()
            if inner:
                return inner[:200]
            continue
        if stripped.startswith(("#", "import ", "from ")):
            continue
        return stripped[:200]
    return lines[0][:200] if lines else ""


def _node_name(node) -> str | None:  # noqa: ANN001 - tree-sitter Node
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    text = name_node.text
    return text.decode("utf-8", "ignore") if isinstance(text, bytes) else str(text)


def chunk_python_source(source: str, path: str) -> list[CodeChunk]:
    lines = source.splitlines()
    chunks: list[CodeChunk] = []

    def add(kind: str, name: str, start: int, end: int) -> None:
        if end < start:
            return
        span = end - start + 1
        if span > MAX_CHUNK_LINES:
            return
        content = "\n".join(lines[start - 1 : end])
        if not content.strip():
            return
        chunks.append(
            CodeChunk(
                path=path,
                name=name,
                kind=kind,
                start_line=start,
                end_line=end,
                content=content,
            )
        )

    if _PARSER is not None:
        tree = _PARSER.parse(source.encode("utf-8", "ignore"))
        for node in tree.root_node.named_children:
            definition = node
            if node.type == "decorated_definition":
                inner = [
                    child
                    for child in node.named_children
                    if child.type in {"function_definition", "class_definition"}
                ]
                if not inner:
                    continue
                definition = inner[0]
            if definition.type not in {"function_definition", "class_definition"}:
                continue
            name = _node_name(definition)
            if not name:
                continue
            kind = "function" if definition.type == "function_definition" else "class"
            start = node.start_point[0] + 1
            end = node.end_point[0] + 1
            add(kind, name, start, end)
        return chunks

    # Line-based fallback: top-level defs/classes.
    starts: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines, start=1):
        if line.startswith("def ") or line.startswith("async def "):
            name = line.split("(")[0].replace("async def", "").replace("def", "").strip()
            starts.append((index, name or "<anonymous>", "function"))
        elif line.startswith("class "):
            name = line.split("(")[0].replace("class", "").split(":")[0].strip()
            starts.append((index, name or "<anonymous>", "class"))
    for position, (start, name, kind) in enumerate(starts):
        end = (starts[position + 1][0] - 1) if position + 1 < len(starts) else len(lines)
        add(kind, name, start, end)
    return chunks


def chunk_repository(repo_root: Path) -> list[CodeChunk]:
    repo_root = Path(repo_root)
    chunks: list[CodeChunk] = []
    for file_path in sorted(repo_root.rglob("*.py")):
        relative = file_path.relative_to(repo_root).as_posix()
        if any(part in SKIP_DIRS for part in file_path.parts) or "egg-info" in relative:
            continue
        try:
            if file_path.stat().st_size > MAX_FILE_BYTES:
                continue
            source = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        chunks.extend(chunk_python_source(source, relative))
        if len(chunks) >= MAX_REPO_CHUNKS:
            return chunks[:MAX_REPO_CHUNKS]
    return chunks


def git_binary_available() -> bool:
    return shutil.which("git") is not None
