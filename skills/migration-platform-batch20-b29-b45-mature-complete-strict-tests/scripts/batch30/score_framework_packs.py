#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description='Score candidate Batch 30 framework packs.')
    parser.add_argument('input')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text())
    weights = data.get('weights', {})
    results = []
    for candidate in data.get('candidates', []):
        score = sum(float(candidate.get(key, 0)) * float(weight) for key, weight in weights.items())
        blockers = candidate.get('blockers', [])
        if blockers:
            decision = 'block'
        elif score >= 3.75:
            decision = 'approve'
        elif score >= 2.5:
            decision = 'research'
        else:
            decision = 'defer'
        results.append({'pack_key':candidate.get('pack_key'),'score':round(score,4),'decision':decision,'blockers':blockers})
    results.sort(key=lambda item: item['score'], reverse=True)
    Path(args.output).write_text(json.dumps({'results':results}, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
