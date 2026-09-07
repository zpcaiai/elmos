import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/spring-golden-route-engine/src"
sys.path.insert(0, str(ENGINE_SRC))

from elmos_spring_golden_route.errors import StepBudgetAuthorizationDenied  # noqa: E402
from elmos_spring_golden_route.step_budget import (  # noqa: E402
    BudgetScope,
    REQUEST_SCHEMA_VERSION,
    StepBudgetStore,
    authorization_scope_sha256,
)


PACKAGE = ENGINE_SRC / "elmos_spring_golden_route"
REQUEST_SCHEMA = PACKAGE / "agent_step_budget_request.schema.json"
RESPONSE_SCHEMA = PACKAGE / "agent_step_budget_response.schema.json"
ERROR_SCHEMA = PACKAGE / "agent_step_budget_error.schema.json"


class AgentStepBudgetSchemaTest(unittest.TestCase):
    def test_schemas_accept_real_runtime_request_response_and_typed_error(self) -> None:
        schemas = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (REQUEST_SCHEMA, RESPONSE_SCHEMA, ERROR_SCHEMA)
        ]
        for schema in schemas:
            Draft202012Validator.check_schema(schema)

        request_validator = Draft202012Validator(schemas[0])
        response_validator = Draft202012Validator(schemas[1])
        error_validator = Draft202012Validator(schemas[2])
        scope = BudgetScope("tenant-a", "project-a", "run-a", "task-a", "agent-a")
        now = datetime(2026, 8, 28, 8, 0, tzinfo=UTC)
        permission = "agent-step-budget.admit"
        request = {
            "schema_version": REQUEST_SCHEMA_VERSION,
            "operation": "admit",
            "skill_name": "agent-step-budget",
            **scope.as_dict(),
            "actor_id": "actor-a",
            "idempotency_key": "idem-a",
            "authorization": {
                "authorization_id": "auth-a",
                "decision": "ALLOW",
                "permission": permission,
                "subject_actor_id": "actor-a",
                "scope_sha256": authorization_scope_sha256(scope, permission),
                "issued_at": (now - timedelta(seconds=1)).isoformat(),
                "expires_at": (now + timedelta(minutes=5)).isoformat(),
                "token": "trusted-local-test-token",
            },
            "input": {
                "policy": {
                    "base_max_steps": 2,
                    "base_max_turns": 2,
                    "hard_max_steps": 2,
                    "hard_max_turns": 2,
                    "complexity": "MEDIUM",
                    "expected_step_cost_microusd": 10,
                    "max_cost_microusd": 100,
                    "max_tokens": 1000,
                    "warning_remaining_steps": 1,
                    "warning_remaining_turns": 1,
                    "reservation_timeout_seconds": 60,
                }
            },
        }
        request_validator.validate(request)
        with tempfile.TemporaryDirectory() as temporary:
            store = StepBudgetStore(
                Path(temporary) / "budgets.sqlite3",
                authorization_verifier=lambda authorization: authorization["token"] == "trusted-local-test-token",
                clock=lambda: now,
            )
            response = store.execute(request)
            response_validator.validate(response)

            denied = json.loads(json.dumps(request))
            denied["idempotency_key"] = "idem-denied"
            denied["authorization"]["decision"] = "DENY"
            with self.assertRaises(StepBudgetAuthorizationDenied) as caught:
                store.execute(denied)
            error_validator.validate(caught.exception.as_dict())


if __name__ == "__main__":
    unittest.main()
