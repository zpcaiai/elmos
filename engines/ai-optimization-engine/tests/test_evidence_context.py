import unittest
from elmos_ai_optimization.evidence_context import EvidenceContextService, Document, _tokenize
from elmos_ai_optimization.scope import HostAuthority, ScopeResolver
from elmos_ai_optimization.contracts import TrustedScope, RevisionBinding, ContextRequest

class TestEvidenceContext(unittest.TestCase):
    def setUp(self):
        self.auth = HostAuthority()
        self.resolver = ScopeResolver(self.auth)
        self.service = EvidenceContextService(self.resolver)
        
        self.auth.register_grant("t1", "r1", ["p1"], "gen-1")
        self.auth.create_session("t1", "p1", "tok")
        self.scope = self.resolver.resolve("t1", "p1", "tok", [("r1", "s1", "gen-1")])
        
    def test_document_create(self):
        doc = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text", [0.1, 0.2])
        self.assertEqual(doc.doc_id, "d1")
        self.assertEqual(len(doc.blob_digest), 64)
        self.assertFalse(doc.tombstoned)

    def test_add_and_fast_path_lookup(self):
        doc = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text")
        self.service.add_document(doc)
        
        req = ContextRequest("req1", "", "exact", 10, 1000, selector={"path": "p1"})
        res = self.service.query(self.scope, req)
        self.assertEqual(res.status, "ok")
        self.assertEqual(len(res.items), 1)
        self.assertEqual(res.items[0].text, "text")

    def test_tombstone_document(self):
        doc = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text")
        self.service.add_document(doc)
        self.service.tombstone_document("t1", "d1")
        
        req = ContextRequest("req1", "", "exact", 10, 1000, selector={"path": "p1"})
        res = self.service.query(self.scope, req)
        self.assertEqual(res.status, "insufficient_evidence")

    def test_scope_filtering_wrong_tenant(self):
        doc = Document.create("d1", "t2", "r1", "s1", "gen-1", "p1", "sym1", "text")
        self.service.add_document(doc)
        
        req = ContextRequest("req1", "", "exact", 10, 1000, selector={"path": "p1"})
        res = self.service.query(self.scope, req)
        self.assertEqual(res.status, "insufficient_evidence")

    def test_scope_filtering_wrong_revision(self):
        doc = Document.create("d1", "t1", "r2", "s1", "gen-1", "p1", "sym1", "text")
        self.service.add_document(doc)
        
        req = ContextRequest("req1", "", "exact", 10, 1000, selector={"path": "p1"})
        res = self.service.query(self.scope, req)
        self.assertEqual(res.status, "insufficient_evidence")

    def test_fts_search(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "apple orange banana")
        doc2 = Document.create("d2", "t1", "r1", "s1", "gen-1", "p2", "sym2", "grape kiwi")
        self.service.add_document(doc1)
        self.service.add_document(doc2)
        
        req = ContextRequest("req1", "apple", "lexical", 10, 1000)
        res = self.service.query(self.scope, req)
        self.assertEqual(len(res.items), 1)
        self.assertEqual(res.items[0].anchor.path, "p1")

    def test_fts_substring_fallback(self):
        # FTS5 might not match substring without wildcards, triggering fallback
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "appleorangebanana")
        self.service.add_document(doc1)
        
        req = ContextRequest("req1", "orange", "lexical", 10, 1000)
        res = self.service.query(self.scope, req)
        self.assertEqual(len(res.items), 1)
        self.assertEqual(res.items[0].anchor.path, "p1")

    def test_dense_search(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text1", [1.0, 0.0])
        doc2 = Document.create("d2", "t1", "r1", "s1", "gen-1", "p2", "sym2", "text2", [0.0, 1.0])
        self.service.add_document(doc1)
        self.service.add_document(doc2)
        
        # Dense search is triggered in hybrid mode when no candidates found in exact mode
        # Wait, dense is only triggered in hybrid mode.
        req = ContextRequest("req1", "query", "hybrid", 10, 1000)
        res = self.service.query(self.scope, req, query_vector=[0.9, 0.1])
        # It should fuse both FTS and dense. FTS won't match "query", so only dense.
        # [1.0, 0.0] should rank higher than [0.0, 1.0] for query [0.9, 0.1]
        self.assertTrue(len(res.items) >= 1)
        self.assertEqual(res.items[0].anchor.path, "p1")

    def test_dense_search_no_vector(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text1")
        self.service.add_document(doc1)
        req = ContextRequest("req1", "query", "hybrid", 10, 1000)
        res = self.service.query(self.scope, req, query_vector=[0.9, 0.1])
        self.assertEqual(len(res.items), 0)
        
    def test_dense_search_zero_query_vector(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text1", [1.0, 0.0])
        self.service.add_document(doc1)
        req = ContextRequest("req1", "query", "hybrid", 10, 1000)
        res = self.service.query(self.scope, req, query_vector=[0.0, 0.0])
        self.assertEqual(len(res.items), 0)

    def test_hybrid_rrf(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text1 match", [1.0, 0.0])
        doc2 = Document.create("d2", "t1", "r1", "s1", "gen-1", "p2", "sym2", "text2", [1.0, 0.0])
        self.service.add_document(doc1)
        self.service.add_document(doc2)
        
        req = ContextRequest("req1", "match", "hybrid", 10, 1000)
        res = self.service.query(self.scope, req, query_vector=[1.0, 0.0])
        # doc1 matches both FTS and dense, should be first
        self.assertEqual(res.items[0].anchor.path, "p1")

    def test_token_budget_truncation(self):
        long_text = "a" * 1000
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", long_text)
        self.service.add_document(doc1)
        
        # Budget is 10 tokens -> ~40 chars
        req = ContextRequest("req1", "a", "lexical", 10, 10)
        res = self.service.query(self.scope, req)
        
        self.assertEqual(len(res.items), 1)
        self.assertTrue(res.items[0].truncated)
        self.assertEqual(len(res.items[0].text), 40)
        self.assertEqual(res.items[0].anchor.end_byte, 40)

    def test_deduplication(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text1 match")
        doc2 = Document.create("d2", "t1", "r1", "s1", "gen-1", "p1", "sym1", "text2 match") # Same anchor
        self.service.add_document(doc1)
        self.service.add_document(doc2)
        
        req = ContextRequest("req1", "match", "lexical", 10, 1000)
        res = self.service.query(self.scope, req)
        self.assertEqual(len(res.items), 1) # Should deduplicate by anchor

    def test_exact_mode_symbol_and_path(self):
        doc1 = Document.create("d1", "t1", "r1", "s1", "gen-1", "p1", "sym_match", "text1")
        doc2 = Document.create("d2", "t1", "r1", "s1", "gen-1", "path_match", "sym2", "text2")
        self.service.add_document(doc1)
        self.service.add_document(doc2)
        
        req = ContextRequest("req1", "sym_match", "exact", 10, 1000)
        res = self.service.query(self.scope, req)
        self.assertEqual(res.items[0].anchor.path, "p1")

        req = ContextRequest("req2", "path_match", "exact", 10, 1000)
        res = self.service.query(self.scope, req)
        self.assertEqual(res.items[0].anchor.path, "path_match")

if __name__ == '__main__':
    unittest.main()
