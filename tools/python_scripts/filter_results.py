#!/usr/bin/env python3
"""
Filter selector output against allowed tests.
Ensures that only valid test identifiers are included in the final selection.
"""

import json


def filter_selected_tests():
    """Filter the selector output to only include allowed tests."""
    # Load input data to get allowed tests
    with open('tools/output/input_for_llm.json', 'r') as f:
        inp = json.load(f)
    allowed = set(inp.get('allowed_tests') or [])
    
    # Load selector output
    with open('selector_output.json', 'r') as f:
        sel = json.load(f)
    
    # Filter selected tests against allowed list
    selected = [
        t for t in sel.get('selected_tests', []) 
        if (not allowed) or (t in allowed)
    ]
    
    # Filter explanations to match filtered tests
    explanations = {
        k: v for k, v in (sel.get('explanations') or {}).items() 
        if k in selected
    }
    
    # Update the selector output
    sel['selected_tests'] = selected
    sel['explanations'] = explanations
    
    # Write back the filtered results
    with open('selector_output.json', 'w') as f:
        json.dump(sel, f, indent=2)
    
    print('Filtered selector_output.json against allowed_tests')


def main():
    """Main entry point."""
    filter_selected_tests()


if __name__ == '__main__':
    main()