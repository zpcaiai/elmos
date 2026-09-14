from __future__ import annotations

from pathlib import Path
from elmos_spring_modernization.java_worker_bridge import JavaWorkerClient


def test_java_worker_client_real_execution():
    repo_root = Path(__file__).parents[3]
    client = JavaWorkerClient(repo_root=repo_root)

    assert client.is_java_available() is True
    assert client.is_worker_available() is True

    legacy_code = """
package com.example.security;

import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

public class SecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests().anyRequest().authenticated();
    }
}
"""

    res = client.rewrite_with_openrewrite(
        source_code=legacy_code,
        recipe_family="SPRING_SECURITY_6"
    )

    assert res.status == "SUCCESS"
    assert "extends WebSecurityConfigurerAdapter" not in res.source_code
    assert "SecurityFilterChain" in res.source_code
    assert len(res.recipes_applied) > 0
    assert len(res.diff) > 0
    assert res.duration_ms > 0


def test_java_worker_client_jpa_hibernate_real_execution():
    repo_root = Path(__file__).parents[3]
    client = JavaWorkerClient(repo_root=repo_root)

    legacy_jpa_code = """
package com.example.dao;

import org.hibernate.Criteria;
import org.hibernate.criterion.Restrictions;

public class OrderDao {
    public void findOrders() {
        Criteria criteria = null;
    }
}
"""

    res = client.rewrite_with_openrewrite(
        source_code=legacy_jpa_code,
        recipe_family="JPA_HIBERNATE_6"
    )

    assert res.status == "SUCCESS"
    assert "import org.hibernate.Criteria;" not in res.source_code
    assert "CriteriaQuery" in res.source_code
    assert len(res.recipes_applied) > 0


def test_java_worker_client_fallback_on_fake_repo():
    client = JavaWorkerClient(repo_root=Path("/fake/nonexistent/path"))
    res = client.rewrite_with_openrewrite(
        source_code="public class Foo {}",
        recipe_family="SPRING_SECURITY_6"
    )
    assert res.status == "FALLBACK_PYTHON_LST"
    assert "Java Worker environment unavailable" in (res.error_message or "")


def test_java_worker_client_analyze_real_execution():
    repo_root = Path(__file__).parents[3]
    client = JavaWorkerClient(repo_root=repo_root)

    bad_tx_code = """
package com.example.service;

import org.springframework.transaction.annotation.Transactional;

public class OrderService {
    public void processOrder() {
        doInternalUpdate();
    }

    @Transactional
    public void doInternalUpdate() {
        System.out.println("Updating...");
    }
}
"""
    res = client.analyze_with_java_worker(
        source_code=bad_tx_code,
        analysis_type="ALL"
    )
    assert res.status == "SUCCESS"
    assert res.findings_count >= 1
    rules = [f.rule_id for f in res.findings]
    assert "SPRING_TX_SELF_INVOCATION" in rules

