#!/usr/bin/env python3
"""Read-only, token-free scan of structured denial and agent-turn events."""
import argparse
import json
import re
import sys


PHRASES = re.compile(r'allow rule|permission rule|settings|auto mode', re.IGNORECASE)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='JSONL schema: {"type":"denial"|"turn", "thread":"id", '
               '"seq":integer, "text":"text"}. Needs denials recorded as '
               'structured events; none exist yet. Sequence, not file order, '
               'determines whether a turn follows a denial. Exit: 0 clean, '
               '1 flagged turns, 2 missing/malformed file.')
    parser.add_argument('events', help='JSONL event file (read only)')
    args = parser.parse_args()
    events = []
    try:
        with open(args.events, encoding='utf-8') as source:
            for number, line in enumerate(source, 1):
                try:
                    event = json.loads(line)
                    if not (isinstance(event, dict) and
                            event.get('type') in ('denial', 'turn') and
                            isinstance(event.get('thread'), str) and event['thread'] and
                            type(event.get('seq')) is int and
                            isinstance(event.get('text'), str)):
                        raise ValueError('invalid event schema')
                except ValueError as error:
                    raise ValueError(f'line {number}: {error}') from error
                events.append((number, event))
    except (OSError, ValueError) as error:
        print(f'{args.events}: {error}', file=sys.stderr)
        return 2
    denials = {}
    for _, event in events:
        if event['type'] == 'denial':
            thread = event['thread']
            denials[thread] = min(event['seq'], denials.get(thread, event['seq']))
    flagged = False
    for number, event in events:
        if (event['type'] == 'turn' and event['thread'] in denials and
                event['seq'] > denials[event['thread']]):
            match = PHRASES.search(event['text'])
            if match:
                print(f'{args.events}:{number}: thread={event["thread"]!r} '
                      f'seq={event["seq"]}: post-denial phrase {match.group()!r}')
                flagged = True
    return int(flagged)


if __name__ == '__main__':
    sys.exit(main())
