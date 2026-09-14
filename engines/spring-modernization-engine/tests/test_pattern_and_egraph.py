from __future__ import annotations

from pathlib import Path
from elmos_spring_modernization.pattern_engine import (
    DeclarativePatternMatcher,
    DeclarativeRewriteRule,
    EGraphEquivalenceEngine,
    ENode,
)
from elmos_spring_modernization.java_worker_bridge import JavaWorkerClient


def test_declarative_pattern_matcher_request_mapping():
    source_code = """
package com.example.demo.controller;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @RequestMapping(value = "/api/v1/users", method = RequestMethod.GET)
    public List<User> getUsers() {
        return userService.findAll();
    }

    @RequestMapping(value = "/api/v1/users", method = RequestMethod.POST)
    public User createUser(User user) {
        return userService.save(user);
    }
}
"""
    rule = DeclarativeRewriteRule(
        rule_id="SPRING_MVC_TO_GET_MAPPING",
        pattern="@RequestMapping(value = $path, method = RequestMethod.GET)",
        replacement="@GetMapping($path)",
        description="Replace @RequestMapping(GET) with modern @GetMapping"
    )

    matcher = DeclarativePatternMatcher([rule])
    transformed, applied = matcher.apply_rules(source_code)

    assert "SPRING_MVC_TO_GET_MAPPING" in applied
    assert '@GetMapping("/api/v1/users")' in transformed
    # POST method should remain untouched
    assert "RequestMethod.POST" in transformed
    assert "public List<User> getUsers()" in transformed
    assert "return userService.findAll();" in transformed


def test_egraph_equality_saturation_and_invariance_proof():
    engine = EGraphEquivalenceEngine()
    
    # 1. Test basic E-graph construction and union-find
    n1 = ENode(op="getUsers", children=())
    n2 = ENode(op="fetchUsers", children=())
    
    id1 = engine.add_enode(n1)
    id2 = engine.add_enode(n2)
    assert id1 != id2
    
    engine.union(id1, id2)
    assert engine.find(id1) == engine.find(id2)
    
    # 2. Formal Semantic Equivalence Verification
    orig_code = """
package com.example.service;

public class OrderService {
    public Order processOrder(Long id) {
        log.info("Processing order: " + id);
        return orderRepository.findById(id);
    }
}
"""
    # Equivalent code with formatting/annotation adjustment but identical semantics
    rewritten_code = """
package com.example.service;

public class OrderService {
    public Order processOrder(Long id) {
        log.info("Processing order: " + id);
        return orderRepository.findById(id);
    }
}
"""
    proof = EGraphEquivalenceEngine.verify_equivalence(orig_code, rewritten_code)
    assert proof.is_equivalent is True
    assert proof.confidence == 1.0
    assert proof.proof_digest.startswith("sha256:")
    assert "CLASS_STRUCTURE_PRESERVED" in proof.preserved_properties
    assert "METHOD_SIGNATURES_PRESERVED[OrderService]" in proof.preserved_properties
    assert "RETURN_TYPE_PRESERVED[OrderService.processOrder]" in proof.preserved_properties
    assert len(proof.potential_divergences) == 0


def test_egraph_detects_semantic_divergence():
    orig_code = """
package com.example.service;

public class OrderService {
    public Order processOrder(Long id) {
        return orderRepository.findById(id);
    }
}
"""
    # Altered code: return type changed and method removed
    altered_code = """
package com.example.service;

public class OrderService {
    public void processOrder(Long id) {
        orderRepository.deleteById(id);
    }
}
"""
    proof = EGraphEquivalenceEngine.verify_equivalence(orig_code, altered_code)
    assert proof.is_equivalent is False
    assert proof.confidence < 1.0
    assert any("RETURN_TYPE_CHANGED" in div for div in proof.potential_divergences)


def test_java_worker_client_fallback():
    client = JavaWorkerClient(repo_root=Path("/fake/repo/root"))
    
    # When worker directory is not present or uncompiled, client gracefully falls back
    res = client.rewrite_with_openrewrite(
        source_code="public class Test {}",
        recipe_family="SPRING_SECURITY_6"
    )
    
    assert res.status == "FALLBACK_PYTHON_LST"
    assert res.source_code == "public class Test {}"
    assert res.error_message is not None
    assert "standalone Python LST" in res.error_message
