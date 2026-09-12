"""Unit tests verifying all 45 atomic skills dispatch through FdeSkillDispatcher."""

from __future__ import annotations

import unittest

from elmos_fde_delivery.dispatcher import FdeSkillDispatcher, dispatch_fde_skill
from elmos_fde_delivery.registry import (
    ALIAS_PREFIX,
    TOPOLOGICAL_ORDER,
)


class TestAll45SkillsDispatch(unittest.TestCase):
    def test_dispatch_all_skills_by_source_id(self) -> None:
        for skill_id in TOPOLOGICAL_ORDER:
            with self.subTest(skill_id=skill_id):
                result = dispatch_fde_skill(skill_id, {})
                self.assertEqual(result.get("status"), "PASS")
                self.assertEqual(result.get("source_id"), skill_id)
                self.assertEqual(result.get("alias"), ALIAS_PREFIX + skill_id)
                self.assertEqual(result.get("standalone_boundary"), "E3")
                self.assertIn("effect_class", result)

    def test_dispatch_all_skills_by_alias(self) -> None:
        for skill_id in TOPOLOGICAL_ORDER:
            alias = ALIAS_PREFIX + skill_id
            with self.subTest(alias=alias):
                result = FdeSkillDispatcher.dispatch(alias, {})
                self.assertEqual(result.get("status"), "PASS")
                self.assertEqual(result.get("source_id"), skill_id)
                self.assertEqual(result.get("alias"), alias)

    def test_unknown_skill_fails_closed(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            dispatch_fde_skill("non-existent-fde-skill", {})
        self.assertIn("UNKNOWN_OR_UNAUTHORIZED_FDE_SKILL", str(ctx.exception))

    def test_prohibited_production_write_fails_closed(self) -> None:
        with self.assertRaises(PermissionError) as ctx:
            dispatch_fde_skill(
                "changeset-commit-and-provenance-governance",
                {"production_write": True},
            )
        self.assertIn("Production mutation prohibited", str(ctx.exception))

    def test_prohibited_production_target_environment_fails_closed(self) -> None:
        with self.assertRaises(PermissionError) as ctx:
            dispatch_fde_skill(
                "reproducible-build-environment",
                {"target_environment": "production"},
            )
        self.assertIn("Direct production target environment is prohibited", str(ctx.exception))

    def test_unauthorized_e5_certification_claim_fails_closed(self) -> None:
        with self.assertRaises(PermissionError) as ctx:
            dispatch_fde_skill(
                "e0-e3-readiness-and-evidence-bundle",
                {"claim_certification_level": "E5"},
            )
        self.assertIn("external certification required", str(ctx.exception))
