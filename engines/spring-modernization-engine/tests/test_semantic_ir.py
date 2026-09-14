from pathlib import Path
from elmos_spring_modernization.semantic_ir import SpringSemanticExtractor

def test_extract_ir_empty(tmp_path):
    extractor = SpringSemanticExtractor()
    ir = extractor.extract_full_ir(str(tmp_path))
    assert ir is not None
    assert len(ir.bean_graph.beans) == 0
    assert len(ir.endpoints) == 0

def test_extract_full_semantic_ir_from_sources(tmp_path):
    src_dir = tmp_path / "src" / "main" / "java" / "com" / "example"
    src_dir.mkdir(parents=True)

    # 1. Controller
    controller_code = """
package com.example;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/users")
public class UserController {

    @GetMapping("/{id}")
    public String getUser(@PathVariable String id) {
        return "user";
    }

    @PostMapping
    public void createUser() {}

    @DeleteMapping("/{id}")
    public void deleteUser(@PathVariable String id) {}
}
"""
    (src_dir / "UserController.java").write_text(controller_code, encoding="utf-8")

    # 2. Service
    service_code = """
package com.example;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.beans.factory.annotation.Autowired;

@Service("userService")
public class UserService {

    @Autowired
    private UserRepository userRepo;

    @Transactional(propagation = Propagation.REQUIRES_NEW, isolation = Isolation.READ_COMMITTED, readOnly = false)
    public void updateUser(String id) {
    }

    @Transactional(readOnly = true)
    public String findUser(String id) {
        return "found";
    }
}
"""
    (src_dir / "UserService.java").write_text(service_code, encoding="utf-8")

    # 3. Security
    security_code = """
package com.example;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;

@Configuration
public class WebSecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public/**").permitAll()
            .antMatchers("/api/**").authenticated()
            .and()
            .addFilterBefore(new CustomJwtFilter(), UsernamePasswordAuthenticationFilter.class);
    }
}
"""
    (src_dir / "WebSecurityConfig.java").write_text(security_code, encoding="utf-8")

    # 4. Scheduled task
    job_code = """
package com.example;

import org.springframework.stereotype.Component;
import org.springframework.scheduling.annotation.Scheduled;

@Component
public class UserSyncJob {
    @Scheduled(cron = "0 0 * * * ?")
    public void runSync() {}
}
"""
    (src_dir / "UserSyncJob.java").write_text(job_code, encoding="utf-8")

    extractor = SpringSemanticExtractor()
    ir = extractor.extract_full_ir(str(tmp_path))

    # Assert Bean Graph
    bean_names = {b.name for b in ir.bean_graph.beans}
    assert "userController" in bean_names
    assert "userService" in bean_names
    assert "userSyncJob" in bean_names
    user_service_bean = next(b for b in ir.bean_graph.beans if b.name == "userService")
    assert "userRepo" in user_service_bean.dependencies

    # Assert Endpoints
    assert "GET /api/v1/users/{id}" in ir.endpoints
    assert "POST /api/v1/users" in ir.endpoints
    assert "DELETE /api/v1/users/{id}" in ir.endpoints

    # Assert Transactions
    tx_methods = {tx.method: tx for tx in ir.transaction_boundaries}
    assert "UserService.updateUser" in tx_methods
    assert tx_methods["UserService.updateUser"].propagation == "REQUIRES_NEW"
    assert tx_methods["UserService.updateUser"].isolation == "READ_COMMITTED"
    assert tx_methods["UserService.updateUser"].read_only is False

    assert "UserService.findUser" in tx_methods
    assert tx_methods["UserService.findUser"].read_only is True

    # Assert Security
    assert len(ir.security_chains) >= 1
    sec = ir.security_chains[0]
    assert "/public/**" in sec.matchers
    assert "/api/**" in sec.matchers
    assert "CustomJwtFilter" in sec.filters

    # Assert Scheduled Tasks
    assert any("UserSyncJob.runSync" in task and "0 0 * * * ?" in task for task in ir.scheduled_tasks)
