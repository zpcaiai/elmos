import unittest
from elmos_ai_optimization.adapters import elastic_queries, pgvector_query, dify_records
from elmos_ai_optimization.contracts import TrustedScope, RevisionBinding, ScopeDeniedError, ContractError

class TestAdapters(unittest.TestCase):
    def setUp(self):
        self.scope = TrustedScope(
            tenant="t1",
            principal="p1",
            acl_epoch=1,
            security_context_ref="ctx1",
            revisions=(RevisionBinding("r1", "s1", "gen-1"),)
        )
        self.vector = [0.1, 0.2]

    def test_elastic_queries_happy_path(self):
        res = elastic_queries(self.scope, "query", self.vector, k=10)
        self.assertIn("lexical", res)
        self.assertIn("dense", res)
        
        lex_filters = res["lexical"]["query"]["bool"]["filter"]
        self.assertIn({"term": {"tenant": "t1"}}, lex_filters)
        
        dense_query = res["dense"]["knn"]
        self.assertEqual(dense_query["query_vector"], self.vector)
        self.assertEqual(dense_query["k"], 10)

    def test_elastic_queries_invalid(self):
        empty_scope = object.__new__(TrustedScope)
        object.__setattr__(empty_scope, 'revisions', ())
        with self.assertRaises(ScopeDeniedError):
            elastic_queries(empty_scope, "query", self.vector)

        with self.assertRaises(ContractError):
            elastic_queries(self.scope, "", self.vector)
            
        with self.assertRaises(ContractError):
            elastic_queries(self.scope, "query", self.vector, k=0)
            
        with self.assertRaises(ContractError):
            elastic_queries(self.scope, "query", [])

    def test_pgvector_query_happy_path(self):
        sql, params = pgvector_query(self.scope, self.vector, k=10)
        self.assertIn("elmos_evidence_chunks", sql)
        self.assertEqual(params["tenant"], "t1")
        self.assertEqual(params["k"], 10)
        self.assertEqual(params["vector"], "[0.1,0.2]")
        self.assertIn('"repository": "r1"', params["bindings"])

    def test_pgvector_query_invalid(self):
        empty_scope = object.__new__(TrustedScope)
        object.__setattr__(empty_scope, 'revisions', ())
        with self.assertRaises(ScopeDeniedError):
            pgvector_query(empty_scope, self.vector)

        with self.assertRaises(ContractError):
            pgvector_query(self.scope, self.vector, k=101)
            
        with self.assertRaises(ContractError):
            pgvector_query(self.scope, [float('inf')])

    def test_dify_records_happy_path(self):
        result = {
            "scope_digest": self.scope.digest,
            "acl_epoch": 1,
            "items": [
                {"evidence_ref": "ev1", "text": "text1", "anchor": {"path": "p1"}},
                {"evidence_ref": "ev2", "text": "text2", "anchor": {"path": "p2"}}
            ]
        }
        scores = {"ev1": 0.8, "ev2": 0.4}
        binding = {"tenant": "t1", "principal": "p1", "scoring_profile": "prof1"}
        
        res = dify_records(self.scope, result, scores, binding, threshold=0.5)
        records = res["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["title"], "p1")
        self.assertEqual(records[0]["score"], 0.8)

    def test_dify_records_invalid_tenant(self):
        binding = {"tenant": "t2", "principal": "p1", "scoring_profile": "prof1"}
        with self.assertRaises(ScopeDeniedError):
            dify_records(self.scope, {}, {}, binding)

    def test_dify_records_invalid_scope_digest(self):
        binding = {"tenant": "t1", "principal": "p1", "scoring_profile": "prof1"}
        result = {"scope_digest": "wrong_digest"}
        with self.assertRaises(ScopeDeniedError):
            dify_records(self.scope, result, {}, binding)

    def test_dify_records_missing_scoring_profile(self):
        binding = {"tenant": "t1", "principal": "p1"}
        result = {"scope_digest": self.scope.digest}
        with self.assertRaises(ContractError):
            dify_records(self.scope, result, {}, binding)

    def test_dify_records_invalid_score(self):
        result = {
            "scope_digest": self.scope.digest,
            "items": [{"evidence_ref": "ev1", "text": "text1"}]
        }
        binding = {"tenant": "t1", "principal": "p1", "scoring_profile": "prof1"}
        
        with self.assertRaises(ContractError):
            dify_records(self.scope, result, {"ev1": 1.5}, binding)
            
        with self.assertRaises(ContractError):
            dify_records(self.scope, result, {}, binding) # missing score

if __name__ == '__main__':
    unittest.main()
