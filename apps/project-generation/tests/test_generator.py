"""Comprehensive end-to-end tests for project generation and DDD static validator."""

import compileall
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from project_generation.engine import ProjectConfig, ProjectGenerator
from project_generation.validator import DDDValidator, Layer


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_gen_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_generate_go_microservice(temp_dir: Path):
    """Test generating a Go DDD microservice project with enterprise infrastructure."""
    generator = ProjectGenerator()
    out_dir = temp_dir / "order-service"

    config = ProjectConfig(
        language="go",
        project_name="order-service",
        module_name="github.com/example/order-service",
        port="8080",
        grpc_port="9090",
        database="postgres",
        description="Order domain microservice",
        output_dir=str(out_dir),
    )

    result = generator.generate(config)
    assert result.success is True
    assert len(result.files_generated) > 0

    # Check key DDD & enterprise infrastructure files
    assert (out_dir / "go.mod").is_file()
    assert (out_dir / "Makefile").is_file()
    assert (out_dir / "cmd" / "server" / "main.go").is_file()
    assert (out_dir / "internal" / "domain" / "model" / "entity.go").is_file()
    assert (out_dir / "internal" / "application" / "service" / "service.go").is_file()
    assert (out_dir / "internal" / "infrastructure" / "persistence" / "repository_impl.go").is_file()
    assert (out_dir / "internal" / "interfaces" / "http" / "handler.go").is_file()
    assert (out_dir / "internal" / "interfaces" / "http" / "middleware" / "telemetry.go").is_file()
    assert (out_dir / "pkg" / "telemetry" / "tracer.go").is_file()
    assert (out_dir / "pkg" / "resilience" / "circuit_breaker.go").is_file()
    assert (out_dir / "pkg" / "errors" / "errors.go").is_file()

    # Verify graceful drain in main.go
    main_text = (out_dir / "cmd" / "server" / "main.go").read_text(encoding="utf-8")
    assert "30*time.Second" in main_text, "main.go must contain 30s timeout context for graceful drain"
    assert "telemetry.InitTracer" in main_text, "main.go must initialize OpenTelemetry tracer"
    assert "httpServer.Shutdown" in main_text, "main.go must drain active HTTP connections"

    # Verify RFC 7807 Problem Details in pkg/errors
    errors_text = (out_dir / "pkg" / "errors" / "errors.go").read_text(encoding="utf-8")
    assert "ProblemDetails" in errors_text, "errors.go must define RFC 7807 ProblemDetails"
    assert "ToProblemDetails" in errors_text, "errors.go must map errors to ProblemDetails"

    # Verify CircuitBreaker in pkg/resilience
    cb_text = (out_dir / "pkg" / "resilience" / "circuit_breaker.go").read_text(encoding="utf-8")
    assert "CircuitBreaker" in cb_text, "circuit_breaker.go must define CircuitBreaker"
    assert "StateClosed" in cb_text and "StateOpen" in cb_text and "StateHalfOpen" in cb_text

    # Verify DDD compliance
    validator = DDDValidator()
    report = validator.validate(str(out_dir))
    assert report.valid is True
    assert len(report.violations) == 0

    # 1. Run real go vet in the generated project
    go_vet = subprocess.run(
        ["go", "vet", "./..."],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert go_vet.returncode == 0, f"go vet failed in generated project:\n{go_vet.stderr}\n{go_vet.stdout}"

    # 2. Run real go build in the generated project
    go_build = subprocess.run(
        ["go", "build", "./..."],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert go_build.returncode == 0, f"go build failed in generated project:\n{go_build.stderr}\n{go_build.stdout}"

    # 3. Run real go test in the generated project (runs domain, telemetry, resilience, errors tests!)
    go_test = subprocess.run(
        ["go", "test", "-v", "./..."],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert go_test.returncode == 0, f"go test failed in generated project:\n{go_test.stderr}\n{go_test.stdout}"


def test_generate_python_microservice(temp_dir: Path):
    """Test generating a Python FastAPI DDD microservice with enterprise infrastructure."""
    generator = ProjectGenerator()
    out_dir = temp_dir / "user-service"

    config = ProjectConfig(
        language="python",
        project_name="user-service",
        port="8000",
        database="postgresql",
        description="User domain microservice",
        output_dir=str(out_dir),
    )

    result = generator.generate(config)
    assert result.success is True
    assert len(result.files_generated) > 0

    # Check key files
    assert (out_dir / "pyproject.toml").is_file()
    assert (out_dir / "Makefile").is_file()
    assert (out_dir / "app" / "main.py").is_file()
    assert (out_dir / "app" / "domain" / "models" / "entity.py").is_file()
    assert (out_dir / "app" / "application" / "services" / "application_service.py").is_file()
    assert (out_dir / "app" / "infrastructure" / "repositories" / "repository_impl.py").is_file()
    assert (out_dir / "app" / "infrastructure" / "telemetry.py").is_file()
    assert (out_dir / "app" / "interfaces" / "api" / "router.py").is_file()

    # Verify Connection Pool Lifespan and RFC 7807 Exception Handlers in app/main.py
    main_text = (out_dir / "app" / "main.py").read_text(encoding="utf-8")
    assert "lifespan" in main_text, "app/main.py must configure lifespan context manager"
    assert "await db_manager.ping()" in main_text, "lifespan must ping DB connection pool on startup"
    assert "await db_manager.close()" in main_text, "lifespan must close DB connection pool on shutdown"
    assert "application/problem+json" in main_text, "app/main.py must register RFC 7807 problem details handlers"
    assert "make_problem_response" in main_text

    # Verify DDD compliance
    validator = DDDValidator()
    report = validator.validate(str(out_dir))
    assert report.valid is True
    assert len(report.violations) == 0

    # Check python syntax compilation
    success = compileall.compile_dir(str(out_dir), quiet=1)
    assert success is True, "Failed to compile generated Python files!"

    # Run ruff check on generated python project
    ruff_check = subprocess.run(
        ["uv", "run", "ruff", "check", "."],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert ruff_check.returncode == 0, f"ruff check failed in generated python project:\n{ruff_check.stderr}\n{ruff_check.stdout}"

    # Run pytest on generated python project (runs integration test verifying RFC 7807 format and telemetry!)
    py_test = subprocess.run(
        ["uv", "run", "pytest"],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert py_test.returncode == 0, f"pytest failed in generated python project:\n{py_test.stderr}\n{py_test.stdout}"


def test_generate_k8s_manifests(temp_dir: Path):
    """Test generating Kubernetes manifests with PDB and startupProbe hardening."""
    generator = ProjectGenerator()
    out_dir = temp_dir / "k8s"

    config = ProjectConfig(
        language="k8s",
        project_name="payment-service",
        port="8080",
        database="postgres",
        output_dir=str(out_dir),
    )

    result = generator.generate(config)
    assert result.success is True
    assert len(result.files_generated) > 0

    assert (out_dir / "base" / "deployment.yaml").is_file()
    assert (out_dir / "base" / "service.yaml").is_file()
    assert (out_dir / "base" / "kustomization.yaml").is_file()
    assert (out_dir / "base" / "pdb.yaml").is_file()
    assert (out_dir / "overlays" / "dev" / "kustomization.yaml").is_file()
    assert (out_dir / "overlays" / "prod" / "kustomization.yaml").is_file()
    assert (out_dir / "helm" / "chart" / "Chart.yaml").is_file()
    assert (out_dir / "helm" / "chart" / "values.yaml").is_file()

    # YAML Validation: Deployment
    dep_content = (out_dir / "base" / "deployment.yaml").read_text(encoding="utf-8")
    dep_doc = yaml.safe_load(dep_content)
    assert dep_doc["kind"] == "Deployment"
    pod_spec = dep_doc["spec"]["template"]["spec"]

    # Verify startupProbe
    container = pod_spec["containers"][0]
    assert "startupProbe" in container, "Deployment must include startupProbe"
    assert container["startupProbe"]["httpGet"]["path"] == "/healthz"
    assert container["startupProbe"]["failureThreshold"] >= 5

    # Verify topologySpreadConstraints
    assert "topologySpreadConstraints" in pod_spec, "Deployment must include topologySpreadConstraints"
    tsc = pod_spec["topologySpreadConstraints"][0]
    assert tsc["topologyKey"] == "topology.kubernetes.io/zone"
    assert tsc["maxSkew"] == 1

    # YAML Validation: PodDisruptionBudget
    pdb_content = (out_dir / "base" / "pdb.yaml").read_text(encoding="utf-8")
    pdb_doc = yaml.safe_load(pdb_content)
    assert pdb_doc["kind"] == "PodDisruptionBudget"
    assert pdb_doc["spec"]["minAvailable"] == 1

    # YAML Validation: Kustomization includes pdb.yaml
    kust_content = (out_dir / "base" / "kustomization.yaml").read_text(encoding="utf-8")
    kust_doc = yaml.safe_load(kust_content)
    assert "pdb.yaml" in kust_doc["resources"], "kustomization.yaml must include pdb.yaml"

    # Real Kubernetes Client Schema Validation via kubectl dry-run
    if shutil.which("kubectl"):
        for target in ["base", "overlays/dev", "overlays/staging", "overlays/prod"]:
            k_run = subprocess.run(
                ["kubectl", "apply", "--dry-run=client", "-k", str(out_dir / target)],
                capture_output=True,
                text=True,
            )
            assert k_run.returncode == 0, f"kubectl dry-run failed for {target}:\n{k_run.stderr}\n{k_run.stdout}"

    # Real Helm Chart Validation via helm lint --strict and helm template
    if shutil.which("helm"):
        chart_dir = out_dir / "helm" / "chart"
        helm_lint = subprocess.run(
            ["helm", "lint", "--strict", str(chart_dir)],
            capture_output=True,
            text=True,
        )
        assert helm_lint.returncode == 0, f"helm lint failed:\n{helm_lint.stderr}\n{helm_lint.stdout}"

        helm_tmpl = subprocess.run(
            ["helm", "template", "test-release", str(chart_dir)],
            capture_output=True,
            text=True,
        )
        assert helm_tmpl.returncode == 0, f"helm template failed:\n{helm_tmpl.stderr}\n{helm_tmpl.stdout}"


def test_feature_flags_omission(temp_dir: Path):
    """Verify --with-telemetry=False and --with-resilience=False omit infrastructure files."""
    generator = ProjectGenerator()
    out_dir = temp_dir / "minimal-go"

    config = ProjectConfig(
        language="go",
        project_name="minimal-go",
        output_dir=str(out_dir),
        with_telemetry=False,
        with_resilience=False,
    )

    result = generator.generate(config)
    assert result.success is True

    assert not (out_dir / "pkg" / "telemetry" / "tracer.go").exists()
    assert not (out_dir / "pkg" / "resilience" / "circuit_breaker.go").exists()


def test_ddd_validator_detects_violations(temp_dir: Path):
    """Negative test: verify that DDD validator flags architectural violations."""
    project_dir = temp_dir / "bad-project"
    domain_dir = project_dir / "app" / "domain" / "models"
    domain_dir.mkdir(parents=True, exist_ok=True)

    bad_file = domain_dir / "bad_entity.py"
    bad_file.write_text(
        "from app.infrastructure.database.session import DatabaseSessionManager\n"
        "class BadEntity:\n    pass\n",
        encoding="utf-8",
    )

    validator = DDDValidator()
    report = validator.validate(str(project_dir))
    assert report.valid is False
    assert len(report.violations) >= 1
    assert report.violations[0].source_layer == Layer.DOMAIN.value
    assert report.violations[0].target_layer == Layer.INFRASTRUCTURE.value


def test_ddd_validator_relative_import_and_thirdparty(temp_dir: Path):
    """Verify relative import violations are caught and 3rd party packages are not falsely flagged."""
    project_dir = temp_dir / "precision-test-project"
    domain_dir = project_dir / "app" / "domain" / "models"
    domain_dir.mkdir(parents=True, exist_ok=True)

    # 1. Benign file importing 3rd-party packages with matching substrings (e.g. 'application', 'interfaces')
    good_file = domain_dir / "good_entity.py"
    good_file.write_text(
        "import fastapi.applications\n"
        "from google.cloud import application_default_credentials\n"
        "import third_party_interfaces\n"
        "class GoodEntity:\n    pass\n",
        encoding="utf-8",
    )

    validator = DDDValidator()
    report = validator.validate(str(project_dir))
    assert report.valid is True, f"3rd party packages caused false positive violations: {report.violations}"

    # 2. Malicious file using relative import from domain targeting infrastructure
    bad_rel_file = domain_dir / "bad_relative_entity.py"
    bad_rel_file.write_text(
        "from ...infrastructure.repositories import repository_impl\n"
        "class BadRelativeEntity:\n    pass\n",
        encoding="utf-8",
    )

    report2 = validator.validate(str(project_dir))
    assert report2.valid is False, "Relative import into infrastructure was not detected!"
    assert any(
        v.source_layer == Layer.DOMAIN.value and v.target_layer == Layer.INFRASTRUCTURE.value
        for v in report2.violations
    )

