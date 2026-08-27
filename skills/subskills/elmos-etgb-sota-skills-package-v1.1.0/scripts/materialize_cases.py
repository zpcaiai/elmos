#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etgb.materializer import materialize

if __name__ == '__main__':
    print(materialize(ROOT))
