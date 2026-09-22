#!/usr/bin/env python3
"""Render Claude's final response from a retained structured event stream."""
import json
import sys

for line in sys.stdin:
    try:
        event = json.loads(line)
    except ValueError:
        continue
    if isinstance(event, dict) and event.get("type") == "result":
        result = event.get("result")
        if isinstance(result, str):
            print(result)
