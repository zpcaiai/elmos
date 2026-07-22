#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text())
    weights = data.get('weights', {})
    results = []
    for candidate in data.get('candidates', []):
        score = sum(float(candidate.get(key, 0)) * float(weight) for key, weight in weights.items())
        if score >= 14:
            decision = 'approve'
        elif score >= 7:
            decision = 'sequence'
        else:
            decision = 'research'
        results.append({
            'pack_key': candidate.get('pack_key'),
            'score': round(score, 3),
            'decision': decision,
            'evidence_notes': candidate.get('evidence_notes', []),
        })
    results.sort(key=lambda item: item['score'], reverse=True)
    Path(args.output).write_text(json.dumps({'schema_version': 1, 'results': results}, indent=2) + '\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
