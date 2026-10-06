"""Project cited snapshot metadata into a bounded containment map."""

import hashlib

from repo_explorer.schemas import (
    Citation,
    EvidenceMap,
    MapEdge,
    MapIssue,
    MapNode,
    MapSupport,
)


def identity(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:24]


def build_evidence_map(sources: list[dict], node_limit: int) -> EvidenceMap:
    result = EvidenceMap(node_limit=node_limit)
    nodes: dict[str, MapNode] = {}
    claims: dict[str, dict[str, MapEdge]] = {}

    def issue(source_id: str, reason: str, detail: str):
        value = MapIssue(source_id=source_id, reason=reason, detail=detail)
        if value not in result.issues:
            result.issues.append(value)

    for raw in sources:
        source = Citation.model_validate(raw)
        file_id = identity("file", source.path, source.revision)
        if file_id not in nodes:
            nodes[file_id] = MapNode(
                id=file_id,
                kind="file",
                label=source.path,
                path=source.path,
                revision=source.revision,
            )
        nodes[file_id].sources.append(MapSupport(source_id=source.id))
        analysis = source.source_analysis
        if analysis is None:
            issue(source.id, "analysis_unavailable", "This passage has no saved source analysis.")
            continue
        if analysis.status != "analyzed":
            issue(source.id, analysis.status, "Source analysis could not identify definitions.")
            continue
        if analysis.omitted_symbols:
            issue(
                source.id,
                "symbol_limit",
                f"{analysis.omitted_symbols} definitions omitted by the passage limit.",
            )
        if analysis.relationships is None:
            issue(
                source.id,
                "containment_unavailable",
                "The analyzer supplied no containment relationships.",
            )

        def symbol_id(value: str) -> str:
            return identity("symbol", source.path, source.revision, analysis.method, value)

        for symbol in analysis.symbols:
            key = symbol_id(symbol.id)
            if key not in nodes:
                nodes[key] = MapNode(
                    id=key,
                    kind=symbol.kind,
                    label=symbol.qualified_name,
                    path=source.path,
                    revision=source.revision,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )
            nodes[key].sources.append(MapSupport(source_id=source.id, coverage=symbol.coverage))
        for relation in analysis.relationships or []:
            child = symbol_id(relation.child_id)
            parent = symbol_id(relation.parent_id) if relation.parent_id is not None else file_id
            parents = claims.setdefault(child, {})
            if parent not in parents:
                parents[parent] = MapEdge(
                    parent_id=parent,
                    child_id=child,
                    method=analysis.method,
                    source_ids=[],
                )
            if source.id not in parents[parent].source_ids:
                parents[parent].source_ids.append(source.id)

    # Check plugin-supplied relationships before displaying a hierarchy. Names and
    # overlapping line ranges alone never establish an edge.
    edges: dict[str, MapEdge] = {}
    for child, parents in claims.items():
        for parent, edge in parents.items():
            if len(parents) != 1 or child not in nodes or parent not in nodes or child == parent:
                for source_id in edge.source_ids:
                    issue(
                        source_id,
                        "unresolved_relationship",
                        "A containment relationship was ambiguous or lacked an endpoint.",
                    )
            else:
                edges[child] = edge
    cyclic = set()
    for child in edges:
        seen = set()
        current = child
        while current in edges:
            if current in seen:
                cyclic.update(seen)
                break
            seen.add(current)
            current = edges[current].parent_id
    for child in cyclic:
        edge = edges.pop(child)
        for source_id in edge.source_ids:
            issue(source_id, "unresolved_relationship", "Cyclic containment was omitted.")

    # Visit parents before children so a node limit cannot leave a visible edge
    # pointing to an omitted parent. Unplaced definitions remain explicitly unlinked.
    children: dict[str, list[str]] = {}
    for child, edge in edges.items():
        children.setdefault(edge.parent_id, []).append(child)
    roots = [key for key in nodes if key not in edges]
    pending = list(reversed(roots))
    kept = []
    while pending and len(kept) < node_limit:
        key = pending.pop()
        kept.append(key)
        pending.extend(reversed(children.get(key, [])))
    included = set(kept)
    result.nodes = [nodes[key] for key in kept]
    result.edges = [
        edge for edge in edges.values() if edge.parent_id in included and edge.child_id in included
    ]
    result.omitted_nodes = len(nodes) - len(kept)
    return result
