from packages.agent_core.issue_parser import parse_issue


def test_extracts_traceback_paths_and_identifiers():
    body = (
        'Traceback (most recent call last):\n'
        '  File "packages/search/service.py", line 42, in run\n'
        '    result = fuse(rankings)\n'
        'ValueError: `reciprocal_rank_fusion` failed on empty channel\n'
    )
    analysis = parse_issue("RRF fusion crashes", body)
    assert "packages/search/service.py" in analysis.traceback_paths
    assert "reciprocal_rank_fusion" in analysis.identifiers
    terms = analysis.search_terms
    assert terms[0] == "packages/search/service.py"
    assert "service.py" in terms


def test_backticked_file_hints_and_keywords():
    body = "After `ingest.py` runs, the `load_index` helper returns None instead of a list."
    analysis = parse_issue("Ingest returns None", body)
    assert "ingest.py" in analysis.file_hints
    assert "load_index" in analysis.identifiers
    assert "ingest" in analysis.keywords


def test_search_terms_deduplicate_and_cap():
    body = 'File "a/b/c.py", line 1\n' * 30 + " ".join(f"`var_{i}`" for i in range(40))
    analysis = parse_issue("cap test", body)
    assert len(analysis.search_terms) <= 24
    assert len(set(analysis.search_terms)) == len(analysis.search_terms)


def test_empty_body_still_parses_title():
    analysis = parse_issue("Locator crashes on empty index", None)
    assert "locator" in analysis.keywords
