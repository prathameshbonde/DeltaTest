#!/usr/bin/env python3
"""
Process Soot/javap output to create a call graph.
Parses method call information and converts it to JSON format.
"""

import json
import sys


def process_call_graph_output(input_path, output_path):
    """Process call graph output file and create JSON format."""
    edges = []
    
    with open(input_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or '->' not in line:
                continue
                
            caller, callee = [x.strip() for x in line.split('->', 1)]
            
            # Normalize stray '#?' artifacts
            caller = caller.replace('#?', '')
            
            edges.append({"caller": caller, "callee": callee})
    
    with open(output_path, 'w') as out:
        json.dump(edges, out, indent=2)
        
    print(f"Wrote {output_path}")


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: process_call_graph.py <input_file> <output_file>", file=sys.stderr)
        sys.exit(1)
        
    input_path, output_path = sys.argv[1], sys.argv[2]
    process_call_graph_output(input_path, output_path)


if __name__ == '__main__':
    main()