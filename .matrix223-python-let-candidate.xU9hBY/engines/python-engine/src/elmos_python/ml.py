from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path


class MachineLearningModernizationAdvisor:
    EXECUTABLE_ARTIFACTS = {".pkl", ".pickle", ".joblib", ".pt", ".pth", ".ckpt"}

    def inventory(self, root: Path) -> dict[str, object]:
        artifacts = []
        frameworks: set[str] = set()
        findings: set[str] = set()
        gpu_markers: set[str] = set()
        feature_markers: set[str] = set()
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            if path.suffix.lower() in self.EXECUTABLE_ARTIFACTS:
                artifacts.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": sha256(path.read_bytes()).hexdigest(),
                        "loadPolicy": "ISOLATED_NO_NETWORK_NO_SECRET",
                        "loadedDuringScan": False,
                    }
                )
            if path.suffix == ".py":
                source = path.read_text(encoding="utf-8", errors="replace")
                for name, marker in (("TENSORFLOW", "tensorflow"), ("PYTORCH", "torch"), ("SCIKIT_LEARN", "sklearn")):
                    if marker in source:
                        frameworks.add(name)
                if re.search(r"\b(?:tf\.)?(?:Session|placeholder|Estimator)\b|compat\.v1", source):
                    frameworks.add("TENSORFLOW")
                    findings.add("TENSORFLOW_1_STAGED_MIGRATION_REQUIRED")
                if any(marker in source for marker in ("cuda", "cudnn", ".to('cuda", '.to("cuda', "torch.device")):
                    gpu_markers.add(path.relative_to(root).as_posix())
                    findings.add("MODEL_GPU_STACK_COMPATIBILITY_REQUIRED")
                if any(marker in source for marker in ("feature_names", "ColumnTransformer", "Pipeline(", "tokenizer")):
                    feature_markers.add(path.relative_to(root).as_posix())
        if artifacts:
            findings.add("MODEL_ARTIFACT_ENVIRONMENT_LOCKED")
        strategies = [
            "LOAD_IN_OLD_ENV_EXPORT_NEUTRAL",
            "LOAD_IN_OLD_ENV_RESAVE",
            "RETRAIN",
            "KEEP_OLD_SERVING_RUNTIME",
            "DUAL_SERVING_SHADOW",
        ]
        return {
            "frameworks": sorted(frameworks),
            "artifacts": artifacts,
            "artifactEnvironmentBinding": "REQUIRED",
            "tensorflowMigrationStages": [
                "CAPTURE_TF1_BASELINE",
                "TF_UPGRADE_V2_CANDIDATE_ONLY",
                "COMPAT_V1_TRANSITION",
                "EAGER_OR_TF_FUNCTION",
                "TRAINING_AND_CHECKPOINT",
                "SAVED_MODEL_AND_NUMERICAL_VALIDATION",
            ]
            if "TENSORFLOW_1_STAGED_MIGRATION_REQUIRED" in findings
            else [],
            "gpuSourceFiles": sorted(gpu_markers),
            "featurePipelineSourceFiles": sorted(feature_markers),
            "strategies": strategies,
            "codeMigrationSeparateFromModelMigration": True,
            "findings": sorted(findings),
            "requiredValidation": ["ARTIFACT_COMPATIBILITY", "INFERENCE_COMPATIBILITY", "TRAINING_COMPATIBILITY"],
        }
