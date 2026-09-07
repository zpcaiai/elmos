#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output'); args = p.parse_args()
    data = json.loads(Path(args.input).read_text()); weights = data.get('weights', {})
    results = []
    for candidate in data.get('candidates', []):
        score = sum(float(candidate.get(k, 0)) * float(w) for k, w in weights.items())
        decision = 'approve' if score >= 12 else 'research' if score >= 6 else 'defer'
        results.append({'pack_key': candidate.get('pack_key'), 'score': round(score, 3), 'decision': decision, 'evidence_notes': candidate.get('evidence_notes', [])})
    results.sort(key=lambda x: x['score'], reverse=True)
    output = {'results': results}
    text = json.dumps(output, indent=2) + '\n'
    if args.output: Path(args.output).write_text(text)
    else: print(text, end='')
    return 0
if __name__ == '__main__': raise SystemExit(main())
