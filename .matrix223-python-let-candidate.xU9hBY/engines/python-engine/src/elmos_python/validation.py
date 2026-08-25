from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any


@dataclass(frozen=True)
class MetricTolerance:
    name: str
    absolute: float
    relative: float
    equal_nan: bool = False


class NumericalDataValidator:
    def compare(
        self,
        baseline: Sequence[float],
        migrated: Sequence[float],
        tolerance: MetricTolerance,
        business_invariants: list[bool],
        ordering_policy: str,
        baseline_dtype: str,
        migrated_dtype: str,
        *,
        ulp_tolerance: int | None = None,
        schema_equal: bool = True,
        null_semantics_equal: bool = True,
        random_seeds: dict[str, int] | None = None,
        randomness_required: bool = False,
    ) -> dict[str, Any]:
        if len(baseline) != len(migrated):
            return self._decision(
                "REGRESSION",
                tolerance,
                ordering_policy,
                baseline_dtype,
                migrated_dtype,
                ["SHAPE_CHANGED"],
                ulp_tolerance,
                random_seeds,
            )
        failures = []
        for index, (before, after) in enumerate(zip(baseline, migrated, strict=True)):
            if math.isnan(before) or math.isnan(after):
                if not tolerance.equal_nan or not (math.isnan(before) and math.isnan(after)):
                    failures.append(f"NAN_MISMATCH:{index}")
                continue
            if ulp_tolerance is not None:
                unit = max(math.ulp(before), math.ulp(after))
                if abs(before - after) > unit * ulp_tolerance:
                    failures.append(f"ULP_TOLERANCE_EXCEEDED:{index}")
            elif not math.isclose(before, after, rel_tol=tolerance.relative, abs_tol=tolerance.absolute):
                failures.append(f"TOLERANCE_EXCEEDED:{index}")
        if baseline_dtype != migrated_dtype:
            failures.append("DTYPE_CHANGED")
        if not schema_equal:
            failures.append("SCHEMA_CHANGED")
        if not null_semantics_equal:
            failures.append("NULL_SEMANTICS_CHANGED")
        if not all(business_invariants):
            failures.append("BUSINESS_INVARIANT_FAILED")
        if randomness_required and not random_seeds:
            failures.append("RANDOMNESS_CONTROL_MISSING")
        status = (
            "NUMERICALLY_EQUIVALENT"
            if not failures and baseline == migrated
            else ("WITHIN_APPROVED_TOLERANCE" if not failures else "REGRESSION")
        )
        return self._decision(
            status,
            tolerance,
            ordering_policy,
            baseline_dtype,
            migrated_dtype,
            failures,
            ulp_tolerance,
            random_seeds,
        )

    @staticmethod
    def _decision(
        status: str,
        tolerance: MetricTolerance,
        ordering_policy: str,
        baseline_dtype: str,
        migrated_dtype: str,
        failures: list[str],
        ulp_tolerance: int | None,
        random_seeds: dict[str, int] | None,
    ) -> dict[str, Any]:
        return {
            "comparisonId": f"numerical-{tolerance.name}",
            "policy": {
                "metric": tolerance.name,
                "atol": tolerance.absolute,
                "rtol": tolerance.relative,
                "equalNan": tolerance.equal_nan,
                "ordering": ordering_policy,
            },
            "status": status,
            "metrics": [
                {
                    "baselineDtype": baseline_dtype,
                    "migratedDtype": migrated_dtype,
                    "ulpTolerance": ulp_tolerance,
                    "randomSeeds": dict(sorted((random_seeds or {}).items())),
                }
            ],
            "failures": failures,
            "evidenceRefs": [],
        }


class ModelBehaviorValidator:
    def decide(
        self,
        artifact_status: str,
        inference_status: str,
        training_status: str,
        owner_thresholds_approved: bool,
        baseline_tests: int,
        migrated_tests: int,
        *,
        load_matrix_complete: bool = True,
        signature_compatible: bool = True,
        hardware_difference_separated: bool = True,
    ) -> dict[str, Any]:
        blockers = []
        if artifact_status != "PASS":
            blockers.append("ARTIFACT_COMPATIBILITY")
        if inference_status != "PASS":
            blockers.append("INFERENCE_COMPATIBILITY")
        if training_status not in {"PASS", "NOT_REQUIRED_APPROVED"}:
            blockers.append("TRAINING_COMPATIBILITY")
        if not owner_thresholds_approved:
            blockers.append("MODEL_OWNER_THRESHOLD_APPROVAL")
        if migrated_tests < baseline_tests:
            blockers.append("TEST_INVENTORY_REGRESSION")
        if not load_matrix_complete:
            blockers.append("MODEL_LOAD_MATRIX_INCOMPLETE")
        if not signature_compatible:
            blockers.append("MODEL_SIGNATURE_REGRESSION")
        if not hardware_difference_separated:
            blockers.append("HARDWARE_VARIATION_NOT_SEPARATED")
        if blockers:
            decision = "HUMAN_REVIEW_REQUIRED" if blockers == ["MODEL_OWNER_THRESHOLD_APPROVAL"] else "FAIL"
        else:
            decision = "PASS"
        return {
            "artifactStatus": artifact_status,
            "inferenceStatus": inference_status,
            "trainingStatus": training_status,
            "decision": decision,
            "blockers": blockers,
            "hardwareDifferenceSeparated": hardware_difference_separated,
        }


class DatasetSnapshotter:
    def snapshot(
        self,
        rows: Sequence[dict[str, object]],
        *,
        primary_key: str | None,
        ordering: str,
        timezone: str | None = None,
    ) -> dict[str, object]:
        columns = sorted({key for row in rows for key in row})
        schema = [
            {
                "name": column,
                "types": sorted({type(row.get(column)).__name__ for row in rows}),
                "nullCount": sum(row.get(column) is None for row in rows),
            }
            for column in columns
        ]
        canonical = repr([{key: row.get(key) for key in columns} for row in rows]).encode()
        return {
            "schema": schema,
            "shape": [len(rows), len(columns)],
            "rowCount": len(rows),
            "primaryKey": primary_key,
            "ordering": ordering,
            "timezone": timezone or "UNDECLARED",
            "sampleHash": "sha256:" + sha256(canonical).hexdigest(),
            "primaryKeyUnique": primary_key is None or len({row.get(primary_key) for row in rows}) == len(rows),
        }


class PythonValidationJudge:
    def judge(self, path: str, options: dict[str, Any]) -> dict[str, Any]:
        baseline_tests = int(options.get("baselineTests", 0))
        migrated_tests = int(options.get("migratedTests", 0))
        common_blockers = []
        if baseline_tests <= 0:
            common_blockers.append("BASELINE_TEST_IDENTITY_MISSING")
        if migrated_tests < baseline_tests:
            common_blockers.append("TEST_INVENTORY_REGRESSION")
        if not options.get("environmentReproduced", False):
            common_blockers.append("ENVIRONMENT_NOT_REPRODUCED")
        path_upper = path.upper()
        if path_upper == "WEB":
            required = ["httpContractPassed", "sessionAuthPassed", "databaseBehaviorPassed"]
        elif path_upper == "DATA_PIPELINE":
            required = ["dataContractPassed", "numericalPassed", "scheduleRetryPassed"]
        elif path_upper == "AI_ML":
            required = ["artifactPassed", "inferencePassed", "trainingEvidencePassed", "ownerThresholdsApproved"]
        else:
            required = ["syntaxPassed", "typeStateNotRegressed"]
        blockers = [*common_blockers, *(key for key in required if not options.get(key, False))]
        return {
            "path": path_upper,
            "decision": "PASS" if not blockers else "FAIL",
            "blockingReasons": blockers,
            "requiredEvidence": required,
        }
