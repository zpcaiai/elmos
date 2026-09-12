"""Tests for error taxonomy and classification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from elmos_router_industrial.domain.errors import (
    ErrorTaxonomyClass,
    ProviderError,
    map_http_status_to_taxonomy,
)


class TestErrorTaxonomy(unittest.TestCase):
    def test_all_seventeen_error_classes_exist(self) -> None:
        expected_classes = {
            "AUTH",
            "PERMISSION",
            "POLICY_DENIED",
            "RATE_LIMIT",
            "QUOTA_EXHAUSTED",
            "TIMEOUT",
            "CANCELLED",
            "PROVIDER_4XX",
            "PROVIDER_5XX",
            "CONTENT_REFUSAL",
            "CONTEXT_OVERFLOW",
            "INVALID_STRUCTURED_OUTPUT",
            "TOOL_PROTOCOL_ERROR",
            "NETWORK",
            "CIRCUIT_OPEN",
            "BUDGET_DENIED",
            "UNSUPPORTED_CAPABILITY",
        }
        actual_classes = {c.value for c in ErrorTaxonomyClass}
        self.assertEqual(actual_classes, expected_classes)

    def test_http_status_mapping(self) -> None:
        self.assertEqual(map_http_status_to_taxonomy(401), ErrorTaxonomyClass.AUTH)
        self.assertEqual(map_http_status_to_taxonomy(403), ErrorTaxonomyClass.PERMISSION)
        self.assertEqual(map_http_status_to_taxonomy(403, message="Policy violation"), ErrorTaxonomyClass.POLICY_DENIED)
        self.assertEqual(map_http_status_to_taxonomy(429), ErrorTaxonomyClass.RATE_LIMIT)
        self.assertEqual(map_http_status_to_taxonomy(429, error_body={"type": "insufficient_quota"}), ErrorTaxonomyClass.QUOTA_EXHAUSTED)
        self.assertEqual(map_http_status_to_taxonomy(504), ErrorTaxonomyClass.TIMEOUT)
        self.assertEqual(map_http_status_to_taxonomy(500), ErrorTaxonomyClass.PROVIDER_5XX)
        self.assertEqual(map_http_status_to_taxonomy(503), ErrorTaxonomyClass.PROVIDER_5XX)
        self.assertEqual(map_http_status_to_taxonomy(400, message="Maximum context length exceeded"), ErrorTaxonomyClass.CONTEXT_OVERFLOW)
        self.assertEqual(map_http_status_to_taxonomy(400, message="Refusal due to safety filter"), ErrorTaxonomyClass.CONTENT_REFUSAL)

    def test_retryability_and_fallback_eligibility(self) -> None:
        # Rate limit is retryable and fallback eligible
        rl_err = ProviderError(ErrorTaxonomyClass.RATE_LIMIT, "Too many requests", statusCode=429)
        self.assertTrue(rl_err.retryable)
        self.assertTrue(rl_err.fallbackEligible)

        now = datetime.now(timezone.utc)
        deadline = now + timedelta(seconds=10)
        self.assertTrue(rl_err.is_retryable(deadline=deadline, retries_remaining=2, now=now))

        # Exhausted retries
        self.assertFalse(rl_err.is_retryable(deadline=deadline, retries_remaining=0, now=now))

        # Past deadline
        past_deadline = now - timedelta(seconds=1)
        self.assertFalse(rl_err.is_retryable(deadline=past_deadline, retries_remaining=2, now=now))

        # Auth error is NOT retryable and NOT fallback eligible (configuration defect)
        auth_err = ProviderError(ErrorTaxonomyClass.AUTH, "Invalid API Key", statusCode=401)
        self.assertFalse(auth_err.retryable)
        self.assertFalse(auth_err.fallbackEligible)
        self.assertFalse(auth_err.is_retryable(deadline=deadline, retries_remaining=3, now=now))


if __name__ == "__main__":
    unittest.main()
