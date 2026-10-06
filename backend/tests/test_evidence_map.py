import hashlib

from repo_explorer.analysis import PythonSourceAnalyzer
from repo_explorer.config import Settings
from repo_explorer.evidence_map import build_evidence_map
from repo_explorer.sources import CorpusSnapshot


def source_for(text, excerpt=None, source_id="S1", path="sample.py", limit=100):
    excerpt = text if excerpt is None else excerpt
    revision = hashlib.sha256(text.encode()).hexdigest()[:12]
    corpus = CorpusSnapshot([], [{"path": path, "revision": revision}], "", {path: text})
    analyzer = PythonSourceAnalyzer(Settings(_env_file=None, source_symbol_limit=limit), corpus)
    start = text.index(excerpt)
    line = text[:start].count("\n") + 1
    source = {
        "id": source_id,
        "path": path,
        "revision": revision,
        "score": 0.8,
        "start_line": line,
        "end_line": line + excerpt.count("\n"),
        "excerpt": excerpt,
    }
    return {**source, "source_analysis": analyzer.analyze(source).model_dump()}


def test_containment_uses_definition_ids_even_for_repeated_qualified_names():
    text = (
        "class Same:\n    def expire(self): return 1\n\n"
        "class Same:\n    def expire(self): return 2\n"
    )
    source = source_for(text)
    result = build_evidence_map([source], 40)
    classes = [node for node in result.nodes if node.kind == "class"]
    methods = [node for node in result.nodes if node.kind == "method"]
    assert len(classes) == len(methods) == 2
    assert classes[0].id != classes[1].id
    assert methods[0].label == methods[1].label == "Same.expire"
    assert {(edge.parent_id, edge.child_id) for edge in result.edges} == {
        (result.nodes[0].id, classes[0].id),
        (classes[0].id, methods[0].id),
        (result.nodes[0].id, classes[1].id),
        (classes[1].id, methods[1].id),
    }
    assert not result.issues


def test_shared_nodes_keep_per_passage_coverage_and_revisions_separate():
    text = "class Cache:\n    def expire(self):\n        return 1\n"
    first = source_for(text, "return 1")
    second = source_for(text, source_id="S2")
    result = build_evidence_map([first, second], 40)
    assert len(result.nodes) == 3
    assert [(s.source_id, s.coverage) for s in result.nodes[-1].sources] == [
        ("S1", "partial"),
        ("S2", "full"),
    ]
    assert all(edge.source_ids == ["S1", "S2"] for edge in result.edges)
    revised = source_for(text + "# new revision\n", source_id="S3")
    result = build_evidence_map([first, revised], 40)
    assert len(result.nodes) == 6
    by_id = {node.id: node for node in result.nodes}
    assert all(by_id[e.parent_id].revision == by_id[e.child_id].revision for e in result.edges)


def test_missing_analysis_and_legacy_definitions_remain_explicitly_unlinked():
    python = source_for("def example(): return 1\n")
    python["source_analysis"].pop("relationships")
    unsupported = source_for("export const x = 1\n", path="client.ts", source_id="S2")
    absent = {**python, "id": "S3", "source_analysis": None}
    result = build_evidence_map([python, unsupported, absent], 40)
    assert result.edges == []
    assert {issue.reason for issue in result.issues} == {
        "containment_unavailable",
        "unsupported_language",
        "analysis_unavailable",
    }
    assert any(node.kind == "function" for node in result.nodes)


def test_limits_report_hidden_blocks_without_dangling_connections():
    text = "class Cache:\n    def expire(self): return 1\n"
    result = build_evidence_map([source_for(text)], 2)
    assert [node.kind for node in result.nodes] == ["file", "class"]
    assert result.omitted_nodes == 1
    ids = {node.id for node in result.nodes}
    assert all(edge.parent_id in ids and edge.child_id in ids for edge in result.edges)
    limited_analysis = build_evidence_map([source_for(text, limit=1)], 40)
    assert limited_analysis.omitted_nodes == 0
    assert limited_analysis.issues[0].reason == "symbol_limit"


def test_plugin_relationship_cycles_missing_endpoints_and_conflicting_parents_are_omitted():
    source = source_for("class Cache:\n    def expire(self): return 1\n")
    analysis = source["source_analysis"]
    parent, child = [symbol["id"] for symbol in analysis["symbols"]]
    analysis["relationships"] = [
        {"parent_id": child, "child_id": parent},
        {"parent_id": parent, "child_id": child},
        {"parent_id": parent, "child_id": "missing"},
    ]
    result = build_evidence_map([source], 40)
    assert result.edges == []
    assert all(issue.reason == "unresolved_relationship" for issue in result.issues)
    analysis["relationships"] = [
        {"parent_id": None, "child_id": parent},
        {"parent_id": parent, "child_id": child},
        {"parent_id": None, "child_id": child},
    ]
    result = build_evidence_map([source], 40)
    assert len(result.edges) == 1
    assert result.nodes[0].id == result.edges[0].parent_id


def test_module_passage_has_a_file_and_no_invented_definition():
    result = build_evidence_map([source_for("VALUE = 1\n")], 40)
    assert [node.kind for node in result.nodes] == ["file"]
    assert not result.edges and not result.issues
