"""ELMOS build cache, generated-file staging, checkpoint/recovery and publication subsystem.

Layering follows the capability DAG declared by the
``elmos-build-cache-staging-recovery`` skills package:

* P0 foundation -- :mod:`.enums`, :mod:`.errors`, :mod:`.canonical`,
  :mod:`.config`, :mod:`.schemas`, :mod:`.db`.
* P1 local cache -- :mod:`.snapshot`, :mod:`.cas`, :mod:`.fingerprint`,
  :mod:`.action_cache`.
* P2 staging -- :mod:`.staging`, :mod:`.atomic`, :mod:`.overlay`,
  :mod:`.manifests`, :mod:`.publish`.
* P3 incremental -- :mod:`.stage_contract`, :mod:`.interface_hash`, :mod:`.dag`.
* P4 recovery -- :mod:`.journal`, :mod:`.checkpoint`, :mod:`.merge`,
  :mod:`.recovery`.
* P5 distributed -- :mod:`.remote`, :mod:`.native_adapters`.
* P6 assurance -- :mod:`.security`, :mod:`.gc`, :mod:`.observability`,
  :mod:`.chaos`.
* P7 rollout -- :mod:`.pipeline`, :mod:`.api`, :mod:`.cli`.
"""

from __future__ import annotations

__all__ = ["__version__", "PACKAGE_VERSION", "SCHEMA_VERSION"]

__version__ = "1.0.0"
PACKAGE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
