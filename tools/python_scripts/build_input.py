#!/usr/bin/env python3
"""
Build input JSON payload for the selector service.
This script assembles changed files, dependency graphs, and test metadata.
"""

import json
import os
import re
from pathlib import Path


def build_allowed_tests(root: str):
    """Parse Java test files and extract test method identifiers."""
    tests = []
    root_path = Path(root or '.')
    
    for p in root_path.rglob('src/test/java/**/*.java'):
        try:
            text = p.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
            
        # Extract package name
        pkg = None
        m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', text, re.MULTILINE)
        if m:
            pkg = m.group(1)
            
        lines = text.splitlines()
        brace = 0
        pending_class = None
        class_stack = []
        class_brace_levels = []
        pending_test_annot = False
        
        # Patterns for parsing
        class_re = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?class\s+([A-Za-z_][\w$]*)\b')
        method_header = re.compile(r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*(?:public|protected|private)?\s*(?:static\s+)?[\w\[\].<>]+\s+([A-Za-z_][\w$]*)\s*\([^)]*\)')
        
        for line in lines:
            # Track test annotations
            if '@Test' in line or '@org.junit.Test' in line or '@ParameterizedTest' in line or '@RepeatedTest' in line:
                pending_test_annot = True
                
            # Class detection
            cm = class_re.match(line)
            if cm:
                pending_class = cm.group(1)
                # Class body may open on same line
                if '{' in line:
                    brace += line.count('{') - line.count('}')
                    class_stack.append(pending_class)
                    class_brace_levels.append(brace)
                    pending_class = None
                    continue
                    
            # Method detection
            mm = method_header.match(line)
            if mm and class_stack:
                name = mm.group(1)
                is_junit4 = name.startswith('test')
                if pending_test_annot or is_junit4:
                    cls = '$'.join(class_stack)
                    fqc = (pkg + '.' if pkg else '') + cls
                    tests.append(f"{fqc}#{name}")
                pending_test_annot = False
                
            # Brace tracking and class pushes/pops
            if pending_class and '{' in line:
                # handled above, but keep for robustness
                pass
                
            if '{' in line or '}' in line:
                opens = line.count('{')
                closes = line.count('}')
                # If we saw a class header earlier and encounter first '{', push class
                if pending_class and opens > 0:
                    brace += opens
                    class_stack.append(pending_class)
                    class_brace_levels.append(brace)
                    pending_class = None
                    # consume remaining braces for this line
                    if closes:
                        brace -= closes
                else:
                    brace += opens
                    brace -= closes
                    
                # Pop classes whose scope ended
                while class_brace_levels and brace < class_brace_levels[-1]:
                    class_brace_levels.pop()
                    class_stack.pop()
                    
    return sorted(set(tests))


def main():
    """Build and write the input JSON for the LLM service."""
    project_root = os.environ.get('PROJECT_ROOT') or '.'
    
    allowed = build_allowed_tests(project_root)
    
    output = {
        "repo": {
            "name": os.path.basename(os.getcwd()),
            "base_commit": os.environ.get('BASE_REF', 'origin/main'),
            "head_commit": os.environ.get('HEAD_REF', 'HEAD'),
        },
        "changed_files": json.load(open('tools/output/changed_files.json')) if os.path.exists('tools/output/changed_files.json') else [],
        "jdeps_graph": json.load(open('tools/output/jdeps_graph.json')) if os.path.exists('tools/output/jdeps_graph.json') else {},
        "call_graph": json.load(open('tools/output/call_graph.json')) if os.path.exists('tools/output/call_graph.json') else [],
        "allowed_tests": allowed,
        "settings": {
            "confidence_threshold": float(os.environ.get('CONFIDENCE_THRESHOLD', '0.6')),
            "max_tests": 500
        }
    }
    
    with open('tools/output/input_for_llm.json', 'w') as f:
        json.dump(output, f, indent=2)
        
    print('Wrote tools/output/input_for_llm.json')


if __name__ == '__main__':
    main()