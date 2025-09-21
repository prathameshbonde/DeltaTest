"""
Core test selection logic for analyzing code changes and computing test coverage.

This module implements the deterministic selection algorithm that builds reachability
graphs from changed files, class dependencies, and method call graphs to identify
which tests should be executed for a given change set.
"""
from __future__ import annotations
from typing import Dict, List, Tuple, Set, Any
from collections import defaultdict, deque
import logging

logger = logging.getLogger("selector.core")


class CallGraph:
    """
    Represents a call graph with efficient traversal capabilities.
    """
    
    def __init__(self, call_graph_edges: List[Dict[str, str]]):
        """Initialize the call graph from edge list."""
        # Forward graph: who calls whom (caller -> callees)
        self.forward: Dict[str, Set[str]] = defaultdict(set)
        # Reverse graph: who is called by whom (callee -> callers)
        self.reverse: Dict[str, Set[str]] = defaultdict(set)
        
        for edge in call_graph_edges:
            caller = edge['caller']
            callee = edge['callee']
            
            self.forward[caller].add(callee)
            self.reverse[callee].add(caller)
    
    def get_callers(self, method: str) -> Set[str]:
        """Get all methods that call the given method."""
        return self.reverse.get(method, set())
    
    def get_callees(self, method: str) -> Set[str]:
        """Get all methods that are called by the given method."""
        return self.forward.get(method, set())
    
    def find_all_callers_bfs(self, start_methods: Set[str], max_depth: int = 10) -> Tuple[Set[str], Dict[str, int]]:
        """
        Find all methods that transitively call any of the start methods using BFS.
        
        Args:
            start_methods: Set of methods to start traversal from
            max_depth: Maximum traversal depth to prevent infinite loops
            
        Returns:
            Tuple of (all_callers, depth_map) where:
            - all_callers: All methods that can reach start_methods
            - depth_map: Distance from each caller to nearest start method
        """
        visited = set()
        depth_map = {}
        queue = deque()
        
        # Initialize queue with start methods at depth 0
        for method in start_methods:
            if method not in visited:
                visited.add(method)
                depth_map[method] = 0
                queue.append((method, 0))
        
        while queue:
            current_method, current_depth = queue.popleft()
            
            if current_depth >= max_depth:
                continue
                
            # Find all methods that call the current method
            callers = self.get_callers(current_method)
            
            for caller in callers:
                if caller not in visited:
                    visited.add(caller)
                    depth_map[caller] = current_depth + 1
                    queue.append((caller, current_depth + 1))
        
        return visited, depth_map
    
    def is_test_method(self, method: str) -> bool:
        """
        Determine if a method is likely a test method based on naming conventions.
        """
        if not method or '#' not in method:
            return False
            
        class_name, method_name = method.split('#', 1)
        
        # Check if class is a test class
        if any(pattern in class_name.lower() for pattern in ['test', 'spec']):
            return True
            
        # Check if method follows test naming conventions
        if method_name.lower().startswith('test'):
            return True
            
        return False


def extract_touched_methods(changed_files: List[Dict[str, Any]]) -> Set[str]:
    """
    Extract all touched methods from changed files.
    
    Args:
        changed_files: List of changed file objects with metadata
        
    Returns:
        Set of fully qualified method names that were touched
    """
    touched_methods = set()
    
    for cf in changed_files:
        # Get explicitly identified touched methods
        for method in cf.get('touched_methods', []):
            fqn = method.get('fqn')
            if fqn:
                touched_methods.add(fqn)
        
        # Also add class-level changes (constructors, static initializers, etc.)
        fqc = cf.get('fully_qualified_class')
        if fqc and cf.get('lang') == 'java':
            # Add common constructor patterns
            touched_methods.add(f"{fqc}#<init>")
            touched_methods.add(f"{fqc}#{cf.get('class_name', '')}")
    
    return touched_methods


def find_affected_tests(changed_files: List[Dict[str, Any]], 
                       call_graph: List[Dict[str, str]],
                       jdeps_graph: Dict[str, List[str]],
                       allowed_tests: Set[str] = None) -> Tuple[Set[str], Dict[str, Any]]:
    """
    Find all test methods that are affected by the changed methods.
    
    Args:
        changed_files: List of changed file objects with metadata
        call_graph: Method-level call relationships
        jdeps_graph: Class-level dependency relationships
        allowed_tests: Set of allowed test methods to filter results
        
    Returns:
        Tuple of (affected_tests, metadata) where:
        - affected_tests: Set of test method identifiers that should be run
        - metadata: Additional context about the analysis
    """
    # Extract touched methods from changed files
    touched_methods = extract_touched_methods(changed_files)
    logger.debug(f"Found {len(touched_methods)} touched methods: {list(touched_methods)[:10]}")
    
    if not touched_methods:
        return set(), {'reason': 'no_touched_methods', 'touched_methods_count': 0}
    
    # Build call graph
    graph = CallGraph(call_graph)
    
    # Find all methods that transitively call the touched methods
    all_callers, depth_map = graph.find_all_callers_bfs(touched_methods, max_depth=15)
    logger.debug(f"Found {len(all_callers)} methods in call chain")
    
    # Filter to only test methods
    test_methods = {method for method in all_callers if graph.is_test_method(method)}
    logger.debug(f"Found {len(test_methods)} test methods in call chain")
    
    # Filter against allowed tests if provided
    if allowed_tests:
        filtered_tests = test_methods.intersection(allowed_tests)
        logger.debug(f"Filtered to {len(filtered_tests)} allowed test methods")
        test_methods = filtered_tests
    
    metadata = {
        'touched_methods_count': len(touched_methods),
        'total_callers_count': len(all_callers),
        'test_methods_count': len(test_methods),
        'max_depth_used': max(depth_map.values()) if depth_map else 0,
        'touched_methods_sample': list(touched_methods)[:10],
        'depth_distribution': _calculate_depth_distribution(test_methods, depth_map)
    }
    
    return test_methods, metadata


def _calculate_depth_distribution(test_methods: Set[str], depth_map: Dict[str, int]) -> Dict[str, int]:
    """Calculate distribution of test methods by their distance from changed methods."""
    distribution = defaultdict(int)
    for test_method in test_methods:
        depth = depth_map.get(test_method, -1)
        distribution[f"depth_{depth}"] += 1
    return dict(distribution)


def build_reachability(changed_files: List[Dict[str, Any]],
                       call_graph: List[Dict[str, str]],
                       jdeps_graph: Dict[str, List[str]]) -> Tuple[Set[str], List[Tuple[str, str]]]:
    """
    Legacy function for building reachability graph.
    
    This function is kept for backward compatibility but the new graph-based
    approach in find_affected_tests() is preferred.
    
    Args:
        changed_files: List of changed file objects with metadata
        call_graph: Method-level call relationships (caller -> callee)
        jdeps_graph: Class-level dependency relationships
        
    Returns:
        Tuple of (reached_methods, reason_edges) where:
        - reached_methods: Set of method signatures that may be affected
        - reason_edges: List of (from, to) edges explaining the reachability
    """
    logger.warning("build_reachability is deprecated, use find_affected_tests instead")
    
    # Extract touched methods
    touched_methods = extract_touched_methods(changed_files)
    
    # Use the new graph-based approach
    graph = CallGraph(call_graph)
    all_callers, _ = graph.find_all_callers_bfs(touched_methods)
    
    # Convert to old format for compatibility
    reason_edges = []
    for edge in call_graph:
        if edge['caller'] in all_callers and edge['callee'] in all_callers:
            reason_edges.append((edge['caller'], edge['callee']))
    
    return all_callers, reason_edges[:200]  # Limit edges for compatibility


def select_tests(changed_files: List[Dict[str, Any]],
                 call_graph: List[Dict[str, str]],
                 jdeps_graph: Dict[str, List[str]],
                 allowed_tests: List[str] = None,
                 max_tests: int = 500) -> Tuple[List[str], Dict[str,str], float, Dict[str, Any]]:
    """
    Main test selection function using graph-based analysis.
    
    This function implements the core selection algorithm that:
    1. Extracts touched methods from changed files
    2. Builds call graph and performs reverse traversal
    3. Identifies test methods that transitively call changed methods
    4. Calculates confidence based on graph coverage and change size
    
    Args:
        changed_files: List of changed file objects with metadata
        call_graph: Method-level call relationships
        jdeps_graph: Class-level dependency relationships (legacy, kept for compatibility)
        allowed_tests: List of allowed test identifiers (for filtering)
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
    
    # Convert allowed_tests to set for faster lookup
    allowed_tests_set = set(allowed_tests) if allowed_tests else None
    
    # Use graph-based analysis to find affected tests
    affected_tests, graph_metadata = find_affected_tests(
        changed_files, call_graph, jdeps_graph, allowed_tests_set
    )
    
    logger.debug(
        "graph_analysis: found %d affected tests from %d touched methods",
        len(affected_tests), graph_metadata.get('touched_methods_count', 0)
    )
    
    # Convert to list and apply max_tests limit
    selected_tests = list(affected_tests)[:max_tests]
    
    # Generate explanations for each selected test
    explanations = {}
    depth_dist = graph_metadata.get('depth_distribution', {})
    
    # Build call graph for explanation lookups
    if call_graph:
        graph = CallGraph(call_graph)
        touched_methods = extract_touched_methods(changed_files)
        
        for test in selected_tests:
            explanation = _generate_test_explanation(test, touched_methods, graph)
            explanations[test] = explanation
    
    # Calculate confidence based on multiple factors
    confidence = _calculate_confidence(changed_files, graph_metadata, len(selected_tests))
    
    # Prepare comprehensive metadata
    metadata = {
        'selection_method': 'graph_based_traversal',
        'graph_analysis': graph_metadata,
        'changed_files_paths': [cf.get('path', '') for cf in changed_files],
        'reachability_stats': {
            'total_affected_methods': graph_metadata.get('total_callers_count', 0),
            'affected_tests': len(affected_tests),
            'selected_tests': len(selected_tests),
            'max_depth': graph_metadata.get('max_depth_used', 0)
        }
    }
    
    if selected_tests:
        logger.info("select_tests: returning %d tests (from %d affected), confidence=%.2f", 
                   len(selected_tests), len(affected_tests), confidence)
        logger.debug("selected sample: %s", selected_tests[:10])
    else:
        logger.info("select_tests: returning empty selection, confidence=%.2f", confidence)
        
    return selected_tests, explanations, confidence, metadata


def _generate_test_explanation(test_method: str, touched_methods: Set[str], graph: CallGraph) -> str:
    """
    Generate human-readable explanation for why a test was selected.
    """
    # Find the shortest path from test to any touched method
    # For simplicity, we'll do a basic explanation
    if any(touched in graph.get_callees(test_method) for touched in touched_methods):
        return f"Test directly calls changed methods"
    
    return f"Test transitively calls changed methods through call chain"


def _calculate_confidence(changed_files: List[Dict[str, Any]], 
                         graph_metadata: Dict[str, Any], 
                         selected_count: int) -> float:
    """
    Calculate confidence score based on analysis quality and coverage.
    """
    # Factor 1: Graph coverage (did we find call relationships?)
    touched_count = graph_metadata.get('touched_methods_count', 0)
    if touched_count == 0:
        return 0.1  # Very low confidence if no touched methods identified
    
    total_callers = graph_metadata.get('total_callers_count', 0)
    coverage_factor = min(1.0, 0.7 if total_callers > 0 else 0.3)
    
    # Factor 2: Change size (smaller changes = higher confidence)
    num_changed_lines = 0
    for cf in changed_files:
        for h in cf.get('hunks', []):
            if 'end' in h and 'start' in h:
                num_changed_lines += h['end'] - h['start'] + 1
            elif 'new_lines' in h:
                num_changed_lines += h['new_lines']
            elif 'old_lines' in h:
                num_changed_lines += h['old_lines']
            else:
                num_changed_lines += 1  # Default to 1 line per hunk
    
    num_changed_lines = max(num_changed_lines, 1)  # Ensure at least 1
    size_factor = max(0.3, min(1.0, 50.0 / num_changed_lines))
    
    # Factor 3: Test selection count (moderate count = higher confidence)
    if selected_count == 0:
        selection_factor = 0.2
    elif selected_count <= 10:
        selection_factor = 1.0
    elif selected_count <= 50:
        selection_factor = 0.8
    else:
        selection_factor = 0.6
    
    # Factor 4: Max traversal depth (shallower = higher confidence)
    max_depth = graph_metadata.get('max_depth_used', 0)
    depth_factor = max(0.4, min(1.0, 1.0 - (max_depth * 0.1)))
    
    # Combine factors
    confidence = (0.4 * coverage_factor + 
                 0.25 * size_factor + 
                 0.2 * selection_factor + 
                 0.15 * depth_factor)
    
    # Ensure minimum confidence for graph-based selections
    if selected_count > 0 and total_callers > 0:
        confidence = max(confidence, 0.5)
    
    return round(min(1.0, confidence), 2)


def select_tests_hybrid(changed_files: List[Dict[str, Any]],
                       call_graph: List[Dict[str, str]],
                       jdeps_graph: Dict[str, List[str]],
                       allowed_tests: List[str] = None,
                       max_tests: int = 500,
                       llm_adapter = None) -> Tuple[List[str], Dict[str,str], float, Dict[str, Any]]:
    """
    Hybrid test selection that combines deterministic and LLM-based approaches.
    
    This function runs both the deterministic graph-based selector and an LLM adapter,
    then returns the union of their results. This provides better coverage by combining
    the reliability of deterministic analysis with the contextual understanding of LLMs.
    
    Args:
        changed_files: List of changed file objects with metadata
        call_graph: Method-level call relationships
        jdeps_graph: Class-level dependency relationships
        allowed_tests: List of allowed test identifiers (for filtering)
        max_tests: Maximum number of tests to select
        llm_adapter: LLM adapter instance for additional selection (optional)
        
    Returns:
        Tuple of (selected_tests, explanations, confidence, metadata) where:
        - selected_tests: List of test identifiers from union of both approaches
        - explanations: Combined explanations from both selectors
        - confidence: Weighted confidence score considering both approaches
        - metadata: Combined metadata from both selection methods
    """
    logger.debug(
        "select_tests_hybrid: inputs changed_files=%d, call_graph_edges=%d, jdeps_nodes=%d, max_tests=%d",
        len(changed_files), len(call_graph), len(jdeps_graph), max_tests,
    )
    
    # Run deterministic selector
    det_tests, det_explanations, det_confidence, det_metadata = select_tests(
        changed_files, call_graph, jdeps_graph, allowed_tests, max_tests
    )
    
    logger.debug("Deterministic selector: %d tests, confidence=%.2f", len(det_tests), det_confidence)
    
    # Run LLM selector if adapter is provided
    llm_tests = []
    llm_explanations = {}
    llm_confidence = 0.0
    llm_metadata = {}
    
    if llm_adapter:
        try:
            # Prepare payload for LLM adapter
            payload = {
                'changed_files': changed_files,
                'call_graph': call_graph,
                'jdeps_graph': jdeps_graph,
                'allowed_tests': allowed_tests or [],
                'settings': {'max_tests': max_tests}
            }
            
            llm_tests, llm_explanations, llm_confidence, llm_metadata = llm_adapter.select(payload)
            logger.debug("LLM selector: %d tests, confidence=%.2f", len(llm_tests), llm_confidence)
            
        except Exception as e:
            logger.warning("LLM selector failed, using deterministic only: %s", str(e))
    
    # Create union of selected tests
    det_tests_set = set(det_tests)
    llm_tests_set = set(llm_tests)
    union_tests = list(det_tests_set.union(llm_tests_set))
    
    # Apply max_tests limit to the union
    if len(union_tests) > max_tests:
        # Prioritize deterministic tests, then add LLM tests up to limit
        prioritized_tests = det_tests + [t for t in llm_tests if t not in det_tests_set]
        union_tests = prioritized_tests[:max_tests]
    
    # Combine explanations
    combined_explanations = {}
    combined_explanations.update(det_explanations)
    
    for test, explanation in llm_explanations.items():
        if test in combined_explanations:
            # Combine explanations for tests found by both selectors
            combined_explanations[test] = f"Deterministic: {combined_explanations[test]}; LLM: {explanation}"
        else:
            # Add LLM-only explanations
            combined_explanations[test] = f"LLM: {explanation}"
    
    # Calculate hybrid confidence
    # Higher confidence when both selectors agree, moderate when they complement each other
    overlap_ratio = len(det_tests_set.intersection(llm_tests_set)) / max(len(union_tests), 1)
    base_confidence = max(det_confidence, llm_confidence)
    
    if llm_adapter:
        # Boost confidence when selectors agree, maintain when they complement
        agreement_bonus = overlap_ratio * 0.2
        hybrid_confidence = min(1.0, base_confidence + agreement_bonus)
    else:
        # No LLM adapter, use deterministic confidence
        hybrid_confidence = det_confidence
    
    # Combine metadata
    hybrid_metadata = {
        'selection_method': 'hybrid_deterministic_llm',
        'deterministic': {
            'tests_count': len(det_tests),
            'confidence': det_confidence,
            'metadata': det_metadata
        },
        'llm': {
            'tests_count': len(llm_tests),
            'confidence': llm_confidence,
            'metadata': llm_metadata
        },
        'union': {
            'total_tests': len(union_tests),
            'overlap_count': len(det_tests_set.intersection(llm_tests_set)),
            'overlap_ratio': overlap_ratio,
            'deterministic_only': len(det_tests_set - llm_tests_set),
            'llm_only': len(llm_tests_set - det_tests_set)
        },
        'changed_files_paths': [cf.get('path', '') for cf in changed_files]
    }
    
    logger.info(
        "select_tests_hybrid: det=%d, llm=%d, union=%d, overlap=%d, confidence=%.2f",
        len(det_tests), len(llm_tests), len(union_tests), 
        len(det_tests_set.intersection(llm_tests_set)), hybrid_confidence
    )
    
    return union_tests, combined_explanations, hybrid_confidence, hybrid_metadata
