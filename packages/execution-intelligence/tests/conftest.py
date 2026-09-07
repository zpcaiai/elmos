import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PROFILE_DIR = ROOT / "profiles" / "elmos"
PROJECT_PATH = PROFILE_DIR / "project-profile.json"
TASKS_PATH = PROFILE_DIR / "task-dag.json"
PRICING_PATH = PROFILE_DIR / "pricing-registry.example.json"
