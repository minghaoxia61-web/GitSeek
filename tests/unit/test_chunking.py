import pytest

from packages.agent_core import chunking
from packages.agent_core.chunking import chunk_python_source, chunk_repository

SAMPLE = '''"""Module docstring."""

import os


def first_function(alpha):
    """Do the alpha thing."""
    return alpha + 1


class Greeter:
    """Greets people."""

    def method_one(self):
        return 1


def second_function(beta):
    return beta * 2
'''


def test_tree_sitter_chunks_functions_and_classes():
    chunks = chunk_python_source(SAMPLE, "sample.py")
    by_name = {chunk.name: chunk for chunk in chunks}
    assert set(by_name) == {"first_function", "Greeter", "second_function"}
    assert by_name["first_function"].kind == "function"
    assert by_name["Greeter"].kind == "class"
    assert by_name["Greeter"].start_line == 11
    assert by_name["Greeter"].end_line == 15
    assert by_name["first_function"].summary == "Do the alpha thing."


def test_line_fallback_without_tree_sitter(monkeypatch):
    monkeypatch.setattr(chunking, "_PARSER", None)
    chunks = chunk_python_source(SAMPLE, "sample.py")
    by_name = {chunk.name: chunk for chunk in chunks}
    assert {"first_function", "Greeter", "second_function"} <= set(by_name)
    assert by_name["Greeter"].kind == "class"


def test_oversized_chunks_are_skipped():
    huge = "def big():\n" + "\n".join(f"    x{i} = {i}" for i in range(400))
    assert chunk_python_source(huge, "big.py") == []


def test_chunk_repository_skips_noise_dirs(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(SAMPLE, encoding="utf-8")
    noise = tmp_path / "__pycache__"
    noise.mkdir()
    (noise / "junk.py").write_text("def junk():\n    pass\n", encoding="utf-8")
    chunks = chunk_repository(tmp_path)
    assert {chunk.path for chunk in chunks} == {"pkg/mod.py"}


@pytest.mark.parametrize("source", ["", "\n\n"], ids=["empty", "blank"])
def test_blank_sources_produce_no_chunks(source):
    assert chunk_python_source(source, "empty.py") == []
