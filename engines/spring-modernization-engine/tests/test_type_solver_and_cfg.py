from __future__ import annotations

import pytest
from elmos_spring_modernization.java_ast import (
    JavaLexer,
    JavaASTParser,
    ImportDeclaration,
)
from elmos_spring_modernization.type_solver import (
    GlobalClasspathIndex,
    ClasspathTypeSolver,
    TypeSymbol,
)
from elmos_spring_modernization.control_flow import (
    ControlFlowGraphBuilder,
    TransactionalSelfInvocationDetector,
    SecurityContextTaintAnalyzer,
    HibernateLazyNPlusOneDetector,
)


def test_global_classpath_index_same_package_resolution():
    index = GlobalClasspathIndex()

    order_entity_code = """package com.example.model;

public class OrderEntity {
    private Long id;
}
"""
    index.index_source_code(order_entity_code, "OrderEntity.java")

    # Resolve from another class in the same package (no import)
    resolved = index.resolve_type("OrderEntity", current_package="com.example.model")
    assert resolved is not None
    assert resolved.fqcn == "com.example.model.OrderEntity"
    assert resolved.package_name == "com.example.model"


def test_global_classpath_index_wildcard_import():
    index = GlobalClasspathIndex()

    # Builtin Spring RestController exists in index
    imports = [ImportDeclaration(name="org.springframework.web.bind.annotation.*", is_wildcard=True)]
    resolved = index.resolve_type("RestController", current_package="com.example.controller", imports=imports)

    assert resolved is not None
    assert resolved.fqcn == "org.springframework.web.bind.annotation.RestController"


def test_type_hierarchy_resolution():
    index = GlobalClasspathIndex()

    base_service = """package com.example.service;

public interface BaseService {
    void init();
}
"""
    user_service = """package com.example.service;

public class UserService implements BaseService {
    public void init() {}
}
"""
    index.index_source_code(base_service, "BaseService.java")
    index.index_source_code(user_service, "UserService.java")

    hierarchy = index.get_type_hierarchy("com.example.service.UserService")
    assert "com.example.service.UserService" in hierarchy
    assert "com.example.service.BaseService" in hierarchy


def test_cfg_basic_blocks_builder():
    code = """package com.example.service;

public class PaymentService {
    public void process(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException();
        }
        for (int i = 0; i < 3; i++) {
            System.out.println(i);
        }
        try {
            doCall();
        } catch (Exception e) {
            handleError();
        } finally {
            cleanup();
        }
        return;
    }
}
"""
    lexer = JavaLexer(code)
    tokens = lexer.tokenize()
    parser = JavaASTParser(tokens, source=code)
    unit = parser.parse()

    method = unit.type_declarations[0].members[0]
    cfg = ControlFlowGraphBuilder.build_cfg(method)

    block_kinds = [b.kind for b in cfg.blocks]
    assert "ENTRY" in block_kinds
    assert "EXIT" in block_kinds
    assert "BRANCH" in block_kinds
    assert "LOOP" in block_kinds
    assert "TRY" in block_kinds
    assert "CATCH" in block_kinds
    assert "FINALLY" in block_kinds


def test_transactional_self_invocation_detector():
    code = """package com.example.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    public void checkout(Long orderId) {
        // Self-invocation of transactional method
        this.completeTransaction(orderId);
    }

    @Transactional
    public void completeTransaction(Long orderId) {
        // DB operations
    }
}
"""
    lexer = JavaLexer(code)
    tokens = lexer.tokenize()
    parser = JavaASTParser(tokens, source=code)
    unit = parser.parse()

    findings = TransactionalSelfInvocationDetector.analyze_type(unit.type_declarations[0])
    assert len(findings) == 1
    assert findings[0].rule_id == "SPRING_TX_SELF_INVOCATION"
    assert findings[0].severity == "CRITICAL"
    assert "completeTransaction" in findings[0].message
    assert "checkout" in findings[0].location


def test_security_context_taint_analyzer():
    # Flawed: sets auth without finally clearContext
    flawed_code = """package com.example.security;

public class AuthWorker {
    public void runWithAuth() {
        SecurityContextHolder.getContext().setAuthentication(token);
        doWork();
    }
}
"""
    # Secure: sets auth with finally clearContext
    secure_code = """package com.example.security;

public class AuthWorker {
    public void runWithAuth() {
        try {
            SecurityContextHolder.getContext().setAuthentication(token);
            doWork();
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
"""
    lexer1 = JavaLexer(flawed_code)
    p1 = JavaASTParser(lexer1.tokenize(), source=flawed_code).parse()
    flawed_findings = SecurityContextTaintAnalyzer.analyze_method(p1.type_declarations[0].members[0])
    assert len(flawed_findings) == 1
    assert flawed_findings[0].rule_id == "SECURITY_CONTEXT_LEAK"

    lexer2 = JavaLexer(secure_code)
    p2 = JavaASTParser(lexer2.tokenize(), source=secure_code).parse()
    secure_findings = SecurityContextTaintAnalyzer.analyze_method(p2.type_declarations[0].members[0])
    assert len(secure_findings) == 0


def test_hibernate_lazy_n_plus_one_detector():
    code = """package com.example.reporting;

public class ReportGenerator {
    public void generate(List<User> users) {
        for (User u : users) {
            List<Order> orders = u.getOrders();
            process(orders);
        }
    }
}
"""
    lexer = JavaLexer(code)
    p = JavaASTParser(lexer.tokenize(), source=code).parse()
    findings = HibernateLazyNPlusOneDetector.analyze_method(p.type_declarations[0].members[0])

    assert len(findings) == 1
    assert findings[0].rule_id == "HIBERNATE_LAZY_N_PLUS_ONE"
    assert "getOrders" in findings[0].message
