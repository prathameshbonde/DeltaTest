from __future__ import annotations
from typing import Dict, List, Tuple, Set, Any


def build_reachability(changed_files: List[Dict[str, Any]],
                       call_graph: List[Dict[str, str]],
                       jdeps_graph: Dict[str, List[str]]) -> Tuple[Set[str], List[Tuple[str, str]]]:
    # Identify changed classes/methods from file paths heuristically
    # For demo: convert .../java/com/foo/Bar.java -> com.foo.Bar; methods unknown
    changed_classes: Set[str] = set()
    for cf in changed_files:
        p = cf.get('path','')
        if '/src/main/java/' in p or '/src/test/java/' in p:
            rel = p.split('/src/')[1]
            try:
                pkg_path = rel.split('/java/')[1]
                cls = pkg_path.replace('/', '.').replace('.java','')
                changed_classes.add(cls)
            except Exception:
                pass

    # Build adjacency for call graph at method level
    call_adj: Dict[str, Set[str]] = {}
    for e in call_graph:
        call_adj.setdefault(e['caller'], set()).add(e['callee'])

    # Build class-level adjacency
    class_adj: Dict[str, Set[str]] = {k: set(v) for k,v in jdeps_graph.items()}

    # Propagate reachability: from changed classes to methods and classes
    reached_methods: Set[str] = set()
    reason_edges: List[Tuple[str,str]] = []

    # From classes, mark all methods starting with Class# (unknown set)
    # Here we just seed class names as pseudo-nodes and expand via call graph/class graph
    frontier: List[str] = list(changed_classes)
    visited: Set[str] = set()

    while frontier:
        cur = frontier.pop()
        if cur in visited:
            continue
        visited.add(cur)
        # If it's a class, expand class deps
        if '#' not in cur:
            for nxt in class_adj.get(cur, set()):
                if nxt not in visited:
                    frontier.append(nxt)
                    reason_edges.append((cur, nxt))
        # Expand call graph
        for nxt in call_adj.get(cur, set()):
            if nxt not in visited:
                frontier.append(nxt)
                reason_edges.append((cur, nxt))
                if '#' in nxt:
                    reached_methods.add(nxt)

    return reached_methods, reason_edges


def select_tests(changed_files: List[Dict[str, Any]],
                 call_graph: List[Dict[str, str]],
                 jdeps_graph: Dict[str, List[str]],
                 test_mapping: List[Dict[str, Any]],
                 max_tests: int = 500) -> Tuple[List[str], Dict[str,str], float, Dict[str, Any]]:
    reached_methods, reason_edges = build_reachability(changed_files, call_graph, jdeps_graph)

    selected: List[str] = []
    explanations: Dict[str,str] = {}

    # Match tests whose covers intersect reached methods or changed classes
    changed_paths = [c['path'] for c in changed_files]

    for tm in test_mapping:
        test = tm.get('test')
        covers = set(tm.get('covers', []))
        if covers & reached_methods:
            selected.append(test)
            explanations[test] = 'Selected via call-graph reachability to covered methods.'

    # Fallback: if nothing selected, choose tests in same package as changed classes
    if not selected:
        changed_pkgs = set()
        for cf in changed_files:
            p = cf.get('path','')
            if '/src/' in p and '/java/' in p:
                try:
                    pkg_path = p.split('/src/')[1].split('/java/')[1]
                    pkg = '.'.join(pkg_path.split('/')[:-1])
                    changed_pkgs.add(pkg)
                except Exception:
                    pass
        for tm in test_mapping:
            test = tm.get('test')
            test_pkg = '.'.join(test.split('#')[0].split('.')[:-1])
            if test_pkg in changed_pkgs:
                selected.append(test)
                explanations[test] = 'Selected via package heuristic fallback.'
                if len(selected) >= max_tests:
                    break

    selected = selected[:max_tests]

    # Confidence: combine factors
    num_changed_lines = sum((h['end'] - h['start'] + 1) for cf in changed_files for h in cf.get('hunks', [])) or 1
    distance_factor = min(1.0, 0.8 if reason_edges else 0.4)
    size_factor = max(0.3, min(1.0, 50.0 / num_changed_lines))
    coverage_factor = min(1.0, len(selected) / max(1, len(test_mapping)))
    confidence = round(min(1.0, 0.5*distance_factor + 0.3*size_factor + 0.2*coverage_factor), 2)

    metadata = {
        'reason_edges': [{'from': a, 'to': b} for a,b in reason_edges[:200]],
        'changed_files': changed_paths,
    }

    return selected, explanations, confidence, metadata
