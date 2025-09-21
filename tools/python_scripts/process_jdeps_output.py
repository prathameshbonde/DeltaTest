#!/usr/bin/env python3
"""
Process jdeps output to create a dependency graph.
Parses jdeps output and converts it to JSON format.
"""

import json
import re
import sys


def process_jdeps_output(jdeps_path, out_path):
    """Process jdeps output file and create dependency graph."""
    deps = {}
    line_re = re.compile(r'\s*([\w.$]+)\s*->\s*([\w.$]+)')
    
    with open(jdeps_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = line_re.match(line)
            if not m:
                continue
                
            src, dst = m.group(1), m.group(2)
            if src == dst:
                continue
                
            deps.setdefault(src, set()).add(dst)
    
    # Convert sets to sorted lists for JSON serialization
    as_json = {k: sorted(v) for k, v in deps.items()}
    
    with open(out_path, 'w') as out:
        json.dump(as_json, out, indent=2)
        
    print(f"Wrote {out_path}")


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: process_jdeps_output.py <jdeps_file> <output_file>", file=sys.stderr)
        sys.exit(1)
        
    jdeps_path, out_path = sys.argv[1], sys.argv[2]
    process_jdeps_output(jdeps_path, out_path)


if __name__ == '__main__':
    main()