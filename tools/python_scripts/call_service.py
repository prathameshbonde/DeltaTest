#!/usr/bin/env python3
"""
Call the selector service and handle the response.
Makes HTTP POST request to the FastAPI service with the input JSON.
"""

import json
import sys
import urllib.request


def call_selector_service(url: str):
    """Call the selector service and save the response."""
    try:
        with open('tools/output/input_for_llm.json', 'rb') as f:
            data = f.read()
            
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req) as resp:
            response_data = json.loads(resp.read().decode('utf-8'))
            
        with open('selector_output.json', 'w') as f:
            json.dump(response_data, f, indent=2)
            
        print('Wrote selector_output.json')
        
    except Exception as e:
        # Fallback to empty selection
        fallback = {
            "selected_tests": [], 
            "confidence": 0.0, 
            "reason": f"service_error:{e.__class__.__name__}"
        }
        
        with open('selector_output.json', 'w') as f:
            json.dump(fallback, f, indent=2)
            
        print('Selector service unavailable; wrote empty selection to selector_output.json', file=sys.stderr)


def main():
    """Main entry point - expects URL as command line argument."""
    if len(sys.argv) < 2:
        print("Usage: call_service.py <service_url>", file=sys.stderr)
        sys.exit(1)
        
    url = sys.argv[1]
    call_selector_service(url)


if __name__ == '__main__':
    main()