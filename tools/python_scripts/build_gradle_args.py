#!/usr/bin/env python3
"""
Build Gradle test arguments from selector output.
Converts test identifiers to module-qualified Gradle test commands.
"""

import json
import os
import re
from pathlib import Path


def nearest_gradle_module_dir(file_path: Path):
    """Find the nearest directory containing a Gradle build file."""
    cur = file_path.parent
    while True:
        if (cur / 'build.gradle').exists() or (cur / 'build.gradle.kts').exists():
            return cur
        if cur == cur.parent:
            return None
        cur = cur.parent


def gradle_task_for_module(module_dir: Path, root: Path):
    """Convert module directory to Gradle task path."""
    rel = os.path.relpath(module_dir, root)
    if rel == '.' or rel == '' or rel.startswith('..'):
        return 'test'
    # Convert path segments to gradle path (e.g., services/foo -> :services:foo:test)
    segs = [s for s in rel.replace('\\', '/').split('/') if s and s != '.']
    return ':' + ':'.join(segs) + ':test'


def find_source_for_class(fqc: str, root: Path):
    """Find the source file for a given fully qualified class name."""
    # Support inner classes by using the top-level class for file name
    top = fqc.split('$', 1)[0]
    parts = top.rsplit('.', 1)
    pkg = parts[0] if len(parts) == 2 else ''
    cls = parts[1] if len(parts) == 2 else parts[0]
    
    if not cls:
        return None
        
    pkg_path = pkg.replace('.', '/') if pkg else ''
    patterns = []
    
    if pkg_path:
        patterns.append(f"**/src/test/java/{pkg_path}/{cls}.java")
    else:
        patterns.append(f"**/src/test/java/{cls}.java")
    
    # Fallback: search anywhere under src/test/java for the class file
    patterns.append(f"**/src/test/java/**/{cls}.java")
    
    for pat in patterns:
        for p in root.glob(pat):
            try:
                txt = p.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue
            # Verify package matches when known
            m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', txt, re.MULTILINE)
            file_pkg = m.group(1) if m else ''
            if pkg and file_pkg != pkg:
                continue
            return p
    return None


def build_gradle_args():
    """Build Gradle test arguments from selector output."""
    root = Path(os.environ.get('PROJECT_ROOT') or '.')
    
    # Load selector output
    with open('selector_output.json', 'r') as f:
        sel = json.load(f)
    
    selected = sel.get('selected_tests', [])
    lines = []
    
    for t in selected:
        try:
            cls, meth = t.split('#', 1)
        except ValueError:
            # Skip invalid entries
            continue
            
        src = find_source_for_class(cls, root)
        task = 'test'
        
        if src is not None:
            mod_dir = nearest_gradle_module_dir(src)
            if mod_dir is not None:
                task = gradle_task_for_module(mod_dir, root)
                
        lines.append(f"{task} --tests {cls}.{meth}")
    
    # Write to output file
    out_path = Path('tools/output/gradle_args.txt')
    content = '\n'.join(lines) + ('\n' if lines else '')
    out_path.write_text(content, encoding='utf-8')
    
    print('Wrote tools/output/gradle_args.txt')


def main():
    """Main entry point."""
    build_gradle_args()


if __name__ == '__main__':
    main()