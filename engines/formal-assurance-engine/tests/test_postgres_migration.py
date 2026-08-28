from __future__ import annotations

import unittest

from elmos_formal_assurance.contracts import TrustedIdentity
from elmos_formal_assurance.postgres import (
    Postgres17MigrationManager,
    PostgresMigrationError,
)


class FakeCursor:
    def __init__(self, version: int) -> None:
        self.version = version
        self.current: tuple[object, ...] | None = None
        self.executed: list[tuple[str, object | None]] = []
        self.closed = False

    def execute(self, sql: str, parameters: object | None = None) -> None:
        self.executed.append((sql, parameters))
        if sql == "SHOW server_version_num":
            self.current = (str(self.version),)
        elif sql == "SELECT to_regclass(%s)":
            assert isinstance(parameters, tuple)
            self.current = (parameters[0],)
        else:
            self.current = None

    def fetchone(self) -> tuple[object, ...] | None:
        return self.current

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, version: int = 170005) -> None:
        self.fake_cursor = FakeCursor(version)
        self.committed = False
        self.rolled_back = False

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class PostgresMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = Postgres17MigrationManager()
        self.identity = TrustedIdentity(
            "tenant-a",
            "schema-admin",
            "project-a",
            roles=("formal-assurance-schema-admin",),
            authorization_ref="authz:postgres-migration:a",
        )

    def test_plan_is_digest_bound_and_preserves_external_boundary(self) -> None:
        plan = self.manager.plan()
        self.assertEqual(plan["requiredMajorVersion"], 17)
        self.assertTrue(plan["migrationSha256"].startswith("sha256:"))
        self.assertEqual(len(plan["requiredRelations"]), 3)
        self.assertEqual(plan["executionStatus"], "NOT_RUN")
        self.assertEqual(plan["certificationStatus"], "NOT_CERTIFIED")

    def test_apply_checks_postgres_17_executes_and_verifies_all_relations(self) -> None:
        connection = FakeConnection()
        receipt = self.manager.apply(connection, self.identity)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.fake_cursor.closed)
        self.assertIn(
            "ENABLE ROW LEVEL SECURITY", connection.fake_cursor.executed[1][0]
        )
        self.assertEqual(
            receipt["verifiedRelations"], list(self.manager.REQUIRED_RELATIONS)
        )
        self.assertEqual(receipt["executionStatus"], "LOCAL_EXECUTED_SELF_ATTESTED")
        self.assertEqual(receipt["externalEvidenceStatus"], "NOT_RUN")
        self.assertEqual(receipt["certificationStatus"], "NOT_CERTIFIED")

    def test_apply_denies_missing_authority_and_wrong_server_major(self) -> None:
        with self.assertRaises(PostgresMigrationError):
            self.manager.apply(
                FakeConnection(), TrustedIdentity("tenant-a", "actor-a", "project-a")
            )
        wrong = FakeConnection(160009)
        with self.assertRaises(PostgresMigrationError):
            self.manager.apply(wrong, self.identity)
        self.assertTrue(wrong.rolled_back)
        self.assertFalse(wrong.committed)


if __name__ == "__main__":
    unittest.main()
