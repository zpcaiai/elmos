from __future__ import annotations

import json
from pathlib import Path
import tempfile

from elmos_spring_modernization.semantic_diff_explainer import (
    SemanticCategory,
    RiskLevel,
    SemanticDiffExplainer,
)
from elmos_spring_modernization.git_pr_bundle_emitter import (
    GitPRBundleEmitter,
)


def test_semantic_diff_explainer_categorization():
    file_pairs = [
        (
            "pom.xml",
            """<parent><artifactId>spring-boot-starter-parent</artifactId><version>2.7.0</version></parent>
<dependency><groupId>com.github.pagehelper</groupId><artifactId>pagehelper</artifactId><version>5.2.0</version></dependency>""",
            """<parent><artifactId>spring-boot-starter-parent</artifactId><version>3.5.3</version></parent>
<dependency><groupId>com.github.pagehelper</groupId><artifactId>pagehelper-spring-boot-starter</artifactId><version>2.1.0</version></dependency>""",
        ),
        (
            "src/main/java/com/example/MyServlet.java",
            "import javax.servlet.http.HttpServletRequest;",
            "import jakarta.servlet.http.HttpServletRequest;",
        ),
        (
            "src/main/java/com/example/SecurityConfig.java",
            "public class SecurityConfig extends WebSecurityConfigurerAdapter { }",
            "@Configuration public class SecurityConfig { @Bean public SecurityFilterChain filterChain(HttpSecurity http) {} }",
        ),
        (
            "src/main/java/com/example/GatewayConfig.java",
            "@EnableZuulProxy public class GatewayConfig {}",
            "@Configuration public class GatewayConfig { @Bean public RouteLocator customRoutes() {} }",
        ),
        (
            "src/test/java/com/example/MyServiceTest.java",
            "@RunWith(PowerMockRunner.class)\nPowerMockito.mockStatic(MyUtil.class);",
            "try (MockedStatic<MyUtil> mocked = mockStatic(MyUtil.class)) { }",
        ),
    ]

    report = SemanticDiffExplainer.generate_report(file_pairs)

    assert report.total_files_changed == 5
    assert report.highest_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert report.changes_by_category[SemanticCategory.TOOLCHAIN_BUILD.value] >= 1
    assert report.changes_by_category[SemanticCategory.ECOSYSTEM_DEPENDENCY.value] >= 1
    assert report.changes_by_category[SemanticCategory.JAKARTA_NAMESPACE.value] >= 1
    assert report.changes_by_category[SemanticCategory.SECURITY_AUTH.value] >= 1
    assert report.changes_by_category[SemanticCategory.MICROSERVICE_NETFLIX.value] >= 1
    assert report.changes_by_category[SemanticCategory.TEST_MOCKING.value] >= 1

    md = report.to_markdown()
    assert "# Spring Modernization Semantic Diff Report" in md
    assert "Toolchain baseline upgrade to Spring Boot 3.5.3 & Java 21" in md
    assert "Namespace migration from javax.servlet to jakarta.servlet" in md
    assert "Elimination of PowerMock in favor of Mockito 5 MockedStatic" in md


def test_git_pr_bundle_planning_and_emission():
    file_pairs = [
        (
            "pom.xml",
            "<parent>2.7.0</parent>",
            "<parent>3.5.3</parent>",
        ),
        (
            "src/main/java/com/example/UserEntity.java",
            "import javax.persistence.Entity;",
            "import jakarta.persistence.Entity;",
        ),
        (
            "src/main/java/com/example/SecurityConfig.java",
            "public class SecurityConfig extends WebSecurityConfigurerAdapter",
            "@Bean public SecurityFilterChain filterChain",
        ),
        (
            "src/test/java/com/example/UserServiceTest.java",
            "@RunWith(PowerMockRunner.class)",
            "try (MockedStatic<X> m = mockStatic(X.class))",
        ),
    ]

    report = SemanticDiffExplainer.generate_report(file_pairs)
    prs = GitPRBundleEmitter.plan_pr_splits(report, project_id="sample-service", base_branch="main")

    # There should be distinct ordered PRs
    assert len(prs) >= 3
    # Check ordering: Toolchain (01) before Core/Jakarta (03) before Security (06) before Testing (07)
    indices = [pr.pr_index for pr in prs]
    assert indices == sorted(indices)

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "pr_bundle"
        manifest = GitPRBundleEmitter.emit_bundle(prs, out_dir, project_id="sample-service")

        assert (out_dir / "PR_STACK_OVERVIEW.md").is_file()
        assert (out_dir / "bundle_manifest.json").is_file()

        manifest_data = json.loads((out_dir / "bundle_manifest.json").read_text(encoding="utf-8"))
        assert manifest_data["project_id"] == "sample-service"
        assert manifest_data["total_prs"] == len(prs)

        # Check individual PR markdown exists
        pr_md_files = list(out_dir.glob("PR_[0-9]*.md"))
        assert len(pr_md_files) == len(prs)
