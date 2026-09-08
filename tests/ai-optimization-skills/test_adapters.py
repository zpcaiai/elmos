from __future__ import annotations

import unittest

from elmos_ai_optimization.adapters import dify_records, elastic_queries, pgvector_query
from elmos_ai_optimization.contracts import ScopeDeniedError
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver


class AdaptersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = HostAuthority()
        self.authority.register_grant("tenant-1", "repo-1", ["dev-1"], generation="gen-1")
        self.authority.create_session("tenant-1", "dev-1", "tok-1")
        self.resolver = ScopeResolver(self.authority)
        self.scope = self.resolver.resolve("tenant-1", "dev-1", "tok-1", [("repo-1", "snap-1")])

    def test_elastic_queries_scope_filters(self) -> None:
        queries = elastic_queries(self.scope, "query text", [0.1, 0.2, 0.3], k=10)
        self.assertIn("lexical", queries)
        self.assertIn("dense", queries)
        lexical = queries["lexical"]
        filters = lexical["query"]["bool"]["filter"]
        self.assertEqual(filters[0]["term"]["tenant"], "tenant-1")
        self.assertEqual(filters[1]["term"]["tombstoned"], False)

    def test_pgvector_query_bindings(self) -> None:
        sql, params = pgvector_query(self.scope, [0.1, 0.2], k=5)
        self.assertIn("WITH requested AS", sql)
        self.assertEqual(params["tenant"], "tenant-1")
        self.assertEqual(params["k"], 5)
        self.assertEqual(params["vector"], "[0.1,0.2]")

    def test_dify_records_adaptation(self) -> None:
        result = {
            "scope_digest": self.scope.digest,
            "acl_epoch": self.scope.acl_epoch,
            "items": [
                {
                    "evidence_ref": "ev-1",
                    "text": "class Service: pass",
                    "anchor": {"path": "service.py"},
                }
            ],
        }
        scores = {"ev-1": 0.85}
        binding = {
            "tenant": "tenant-1",
            "principal": "dev-1",
            "scoring_profile": "hybrid-v1",
        }
        records = dify_records(self.scope, result, scores, binding, threshold=0.5)
        self.assertEqual(len(records["records"]), 1)
        self.assertEqual(records["records"][0]["score"], 0.85)
        self.assertEqual(records["records"][0]["title"], "service.py")

    def test_dify_records_forged_scope_fails_closed(self) -> None:
        result = {
            "scope_digest": "forged" * 10 + "abcd",
            "acl_epoch": self.scope.acl_epoch,
            "items": [],
        }
        binding = {"tenant": "tenant-1", "principal": "dev-1", "scoring_profile": "hybrid-v1"}
        with self.assertRaises(ScopeDeniedError):
            dify_records(self.scope, result, {}, binding)


if __name__ == "__main__":
    unittest.main()
