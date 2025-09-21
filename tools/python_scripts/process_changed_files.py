#!/usr/bin/env python3
"""
Process git diff output and extract changed file metadata.
Enriches Java files with package, class, and method information.
"""

import json
import os
import re
import subprocess
import sys


def parse_git_diff(diff_path):
    """Parse git diff output to extract changed files and hunks."""
    changed = []
    current = None
    hunk_re = re.compile(r'^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@')
    file_re = re.compile(r'^\+\+\+ b\/(.*)$')
    
    with open(diff_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if line.startswith('+++ b/'):
                path = file_re.match(line).group(1)
                current = {"path": path, "hunks": []}
                changed.append(current)
            elif line.startswith('@@') and current is not None:
                m = hunk_re.match(line)
                if m:
                    start = int(m.group('new_start'))
                    count = int(m.group('new_count') or '1')
                    current["hunks"].append({"start": start, "end": start + max(count-1, 0)})
    
    return changed


def get_change_types():
    """Get change types for each file using git diff --name-status."""
    base = os.environ.get("BASE_REF", "origin/main")
    head = os.environ.get("HEAD_REF", "HEAD")
    repo = os.environ.get("REPO_CWD", "").strip()
    
    args = ["git"]
    if repo:
        args += ["-C", repo]
    args += ["diff", "--name-status", base, head]
    
    change_type_map = {}
    try:
        ns = subprocess.check_output(args, text=True)
        for line in ns.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                typ, path = parts
                change_type_map[path.strip()] = typ
    except Exception:
        pass
    
    return change_type_map


def detect_lang(path):
    """Detect programming language from file extension."""
    _, ext = os.path.splitext(path)
    if ext.lower() == '.java':
        return 'java'
    return ext[1:].lower() if ext.startswith('.') else None


def git_show(commit, path):
    """Get file content from a specific commit."""
    repo = os.environ.get("REPO_CWD", "").strip()
    args = ["git"]
    if repo:
        args += ["-C", repo]
    args += ["show", f"{commit}:{path}"]
    
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return None


def read_file_for_change(path, change_type):
    """Read file content based on change type."""
    base = os.environ.get("BASE_REF", "origin/main")
    head = os.environ.get("HEAD_REF", "HEAD")
    
    if change_type == 'D':
        return git_show(base, path)
    # default to HEAD for A/M/R
    return git_show(head, path)


def parse_java_info(src, path):
    """Parse Java source to extract package, class, and method information."""
    if not src:
        return None
        
    # Extract package
    pkg_m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', src, re.MULTILINE)
    package = pkg_m.group(1) if pkg_m else None
    
    # Extract class name from file path
    cls = os.path.basename(path).rsplit('.', 1)[0]
    fqc = f"{package}.{cls}" if package else cls
    
    # Extract methods
    lines = src.splitlines()
    methods = []
    
    # Regex for method declarations with opening brace on same line
    header_re = re.compile(
        r'^\s*(?:@[\w.$]+(?:\([^)]*\))?\s*)*'  # annotations
        r'(?:public|protected|private)?\s*'     # access modifier
        r'(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(?:native\s+)?'  # other modifiers
        r'(?:<[^>]+>\s*)?'                      # generic type parameters
        r'[\w\[\].<>]+\s+'                      # return type
        r'([A-Za-z_][\w$]*)\s*'                 # method name (capture)
        r'\([^)]*\)\s*'                         # parameters
        r'(?:throws [^{;]*)?\s*\{'              # throws clause and opening brace
    )
    
    for i, line in enumerate(lines):
        m = header_re.match(line)
        if not m:
            continue
            
        name = m.group(1)
        sig = line.strip()
        start_line = i + 1
        
        # Find end by brace matching starting from this line
        brace = 0
        found_open = False
        end_line = start_line
        
        for j in range(i, len(lines)):
            for ch in lines[j]:
                if ch == '{':
                    brace += 1
                    found_open = True
                elif ch == '}':
                    brace -= 1
            if found_open and brace == 0:
                end_line = j + 1
                break
                
        methods.append({
            "name": name,
            "signature": sig,
            "start_line": start_line,
            "end_line": end_line,
            "fqn": f"{fqc}#{name}",
        })
    
    return {
        "package": package,
        "class_name": cls,
        "fully_qualified_class": fqc,
        "methods": methods,
    }


def compute_touched_methods(java_info, hunks):
    """Determine which methods are touched by the changed hunks."""
    touched = []
    if not java_info:
        return touched
        
    for method in java_info.get('methods', []) or []:
        for hunk in hunks or []:
            # Check if hunk overlaps with method
            if not (hunk['end'] < method['start_line'] or hunk['start'] > method['end_line']):
                touched.append(method)
                break
                
    return touched


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: process_changed_files.py <diff_file> <output_file>", file=sys.stderr)
        sys.exit(1)
        
    diff_path, out_path = sys.argv[1], sys.argv[2]
    
    # Parse git diff output
    changed = parse_git_diff(diff_path)
    
    # Get change types
    change_type_map = get_change_types()
    
    # Enrich each changed file record
    for cf in changed:
        cf["change_type"] = change_type_map.get(cf["path"], "M")
        cf["file_name"] = os.path.basename(cf["path"]) if cf.get("path") else None
        cf["lang"] = detect_lang(cf["path"]) if cf.get("path") else None
        
        if cf["lang"] == 'java':
            src = read_file_for_change(cf["path"], cf.get("change_type", "M")) or ""
            jinfo = parse_java_info(src, cf["path"]) if src else None
            
            if jinfo:
                cf.update({
                    "package": jinfo.get("package"),
                    "class_name": jinfo.get("class_name"),
                    "fully_qualified_class": jinfo.get("fully_qualified_class"),
                })
                cf["touched_methods"] = compute_touched_methods(jinfo, cf.get("hunks", []))
            else:
                cf["touched_methods"] = []
    
    # Write output
    with open(out_path, 'w', encoding='utf-8') as out:
        json.dump(changed, out, indent=2)
        
    print(f"Wrote {out_path}")


if __name__ == '__main__':
    main()