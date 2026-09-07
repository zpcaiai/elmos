"""Configuration manager for ELMOS CLI Gateway.

Discovers and loads `.elmosrc.yaml` or `.elmosrc.json` from the current working
directory or user home directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
import yaml

DEFAULT_CONFIG: Dict[str, Any] = {
    "tenant_id": "tenant-default",
    "project_id": "project-elmos-modernization",
    "actor_id": "developer-cli-user",
    "default_src_lang": "java",
    "default_tgt_lang": "csharp",
    "budget_limit_usd": 50.0,
    "cache_enabled": True,
    "cache_dir": ".elmos/cache",
    "smt_solver": "z3-cvc5-ensemble",
    "fuzz_cases": 25,
    "model_router_preference": "cost_performance",
}


def find_config_file(cwd: Path | None = None) -> Path | None:
    search_dirs = [cwd or Path.cwd(), Path.home()]
    candidates = [
        ".elmosrc.yaml",
        ".elmosrc.yml",
        ".elmosrc.json",
        ".elmos/config.yaml",
        ".elmos/config.json",
    ]
    for d in search_dirs:
        for c in candidates:
            p = d / c
            if p.is_file():
                return p
    return None


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    cfg = dict(DEFAULT_CONFIG)
    p = config_path or find_config_file()
    if p and p.is_file():
        try:
            content = p.read_text(encoding="utf-8")
            if p.suffix in (".yaml", ".yml"):
                loaded = yaml.safe_load(content)
            else:
                loaded = json.loads(content)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass
    return cfg


def save_config(cfg: Dict[str, Any], target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.suffix in (".yaml", ".yml"):
        target_path.write_text(yaml.dump(cfg, sort_keys=False), encoding="utf-8")
    else:
        target_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
