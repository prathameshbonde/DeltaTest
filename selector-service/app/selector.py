"""
Core test selection logic for analyzing code changes and computing test coverage.

This module implements the deterministic selection algorithm that builds reachability
graphs from changed files, class dependencies, and method call graphs to identify
which tests should be executed for a given change set.
"""
from __future__ import annotations
from typing import Dict, List, Tuple, Set, Any
import logging

logger = logging.getLogger("selector.core")


def build_reachability(changed_files: List[Dict[str, Any]],
                       call_graph: List[Dict[str, str]],
                       jdeps_graph: Dict[str, List[str]]) -> Tuple[Set[str], List[Tuple[str, str]]]:
    """
    Build reachability graph from changed files through dependency and call graphs.
    
    This function identifies which methods and classes are potentially affected by
    the given file changes by following dependency and call relationships.
    
    Args:
        changed_files: List of changed file objects with metadata
        call_graph: Method-level call relationships (caller -> callee)
        jdeps_graph: Class-level dependency relationships
        
    Returns:
        Tuple of (reached_methods, reason_edges) where:
        - reached_methods: Set of method signatures that may be affected
        - reason_edges: List of (from, to) edges explaining the reachability
    """
    # Identify changed classes/methods from file paths heuristically
    # For Java files: convert .../java/com/foo/Bar.java -> com.foo.Bar
    changed_classes: Set[str] = set()
    for cf in changed_files:
        # Prefer already computed fully qualified class if available
        fqc = cf.get('fully_qualified_class')
        if fqc:
            changed_classes.add(fqc)
        else:
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
    # Also seed method-level nodes whose declaring class is among changed classes, so method call edges are discovered
    for caller in list(call_adj.keys()):
        cls_part = caller.split('#')[0]
        if cls_part in changed_classes:
            frontier.append(caller)
    # Seed with touched methods if provided
    for cf in changed_files:
        for m in cf.get('touched_methods', []) or []:
            fqn = m.get('fqn')
            if fqn:
                frontier.append(fqn)
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
                 max_tests: int = 500) -> Tuple[List[str], Dict[str,str], float, Dict[str, Any]]:
    """
    Main test selection function using deterministic heuristics.
    
    This function implements the core selection algorithm that:
    1. Builds reachability graphs from changes
    2. Applies selection heuristics based on package proximity
    3. Calculates confidence based on graph signals and change size
    
    Args:
        changed_files: List of changed file objects with metadata
        call_graph: Method-level call relationships
        jdeps_graph: Class-level dependency relationships  
        max_tests: Maximum number of tests to select
        
    Returns:
        Tuple of (selected_tests, explanations, confidence, metadata) where:
        - selected_tests: List of test identifiers to execute
        - explanations: Human-readable reasons for each selection
        - confidence: Float 0.0-1.0 indicating selection quality
        - metadata: Additional context about the selection process
    """
    logger.debug(
        "select_tests: inputs changed_files=%d, call_graph_edges=%d, jdeps_nodes=%d, max_tests=%d",
        len(changed_files), len(call_graph), len(jdeps_graph), max_tests,
    )
    reached_methods, reason_edges = build_reachability(changed_files, call_graph, jdeps_graph)
    logger.debug(
        "reachability: reached_methods=%d, reason_edges=%d",
        len(reached_methods), len(reason_edges),
    )

    selected: List[str] = []
    explanations: Dict[str,str] = {}

    # With no explicit mapping, use a heuristic: select tests whose package matches changed classes' packages
    changed_paths = [c['path'] for c in changed_files]
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
    logger.debug("heuristic: changed_pkgs=%s", sorted(changed_pkgs))

    # Note: This mock implementation returns empty selection by design.
    # In practice, external LLM adapters or enhanced heuristics would populate the selection.
    # The confidence reflects the quality of available graph signals.

    selected = selected[:max_tests]

    # Confidence: combine factors
    num_changed_lines = sum((h['end'] - h['start'] + 1) for cf in changed_files for h in cf.get('hunks', [])) or 1
    distance_factor = min(1.0, 0.8 if reason_edges else 0.4)
    size_factor = max(0.3, min(1.0, 50.0 / num_changed_lines))
    coverage_factor = 0.0
    confidence = round(min(1.0, 0.6*distance_factor + 0.4*size_factor), 2)
    logger.debug(
        "confidence: num_changed_lines=%d, distance_factor=%.2f, size_factor=%.2f, coverage_factor=%.2f, final=%.2f",
        num_changed_lines, distance_factor, size_factor, coverage_factor, confidence,
    )

    metadata = {
        'reason_edges': [{'from': a, 'to': b} for a,b in reason_edges[:200]],
        'changed_files': changed_paths,
    }

    if selected:
        logger.info("select_tests: returning %d tests, confidence=%.2f", len(selected), confidence)
        logger.debug("selected sample: %s", selected[:10])
    else:
        logger.info("select_tests: returning empty selection, confidence=%.2f", confidence)
    return selected, explanations, confidence, metadata
