#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.verification import verify_workspace
from elmos_project_synthesis.workspace import generate_workspace


def main() -> int:
    request = approve_request(
        create_draft(
            name="work-order-service",
            description="生成用于创建、查询和跟踪维修工单的 Java、Python 和 C# 服务。",
            entity="work_order",
        ),
        actor="acceptance:local",
        approved_at="2026-07-22T00:00:00+00:00",
    )
    with tempfile.TemporaryDirectory(prefix="elmos-project-synthesis-") as temporary:
        workspace = Path(temporary) / "workspace"
        manifest = generate_workspace(request, workspace)
        evidence = verify_workspace(workspace)
    result = {
        "status": evidence["status"],
        "generated_file_count": manifest["file_count"],
        "build_and_analysis_count": sum(item.get("kind") != "startup-probe" for item in evidence["results"]),
        "startup_probes": [
            {"port": item["port"], "status": item["status"], "response": item["response"]}
            for item in evidence["results"]
            if item.get("kind") == "startup-probe"
        ],
        "production_delivery_status": evidence["production_delivery_status"],
        "external_certification_status": evidence["external_certification_status"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
