"""Comprehensive end-to-end tests for project generation and DDD static validator."""

import compileall
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from project_generation.engine import ProjectConfig, ProjectGenerator
from project_generation.validator import DDDValidator, Layer


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_gen_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_generate_go_microservice(temp_dir: Path):
    """Test generating a Go DDD microservice project."""
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

    # Check key files
    assert (out_dir / "go.mod").is_file()
    assert (out_dir / "Makefile").is_file()
    assert (out_dir / "cmd" / "server" / "main.go").is_file()
    assert (out_dir / "internal" / "domain" / "model" / "entity.go").is_file()
    assert (out_dir / "internal" / "application" / "service" / "service.go").is_file()
    assert (out_dir / "internal" / "infrastructure" / "persistence" / "repository_impl.go").is_file()
    assert (out_dir / "internal" / "interfaces" / "http" / "handler.go").is_file()

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

    # 3. Run real go test in the generated project!
    go_test = subprocess.run(
        ["go", "test", "-v", "./..."],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert go_test.returncode == 0, f"go test failed in generated project:\n{go_test.stderr}\n{go_test.stdout}"


def test_generate_python_microservice(temp_dir: Path):
    """Test generating a Python FastAPI DDD microservice project."""
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
    assert (out_dir / "app" / "interfaces" / "api" / "router.py").is_file()

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

    # Run pytest on generated python project
    py_test = subprocess.run(
        ["uv", "run", "pytest"],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert py_test.returncode == 0, f"pytest failed in generated python project:\n{py_test.stderr}\n{py_test.stdout}"


def test_generate_k8s_manifests(temp_dir: Path):
    """Test generating Kubernetes manifests and Helm chart."""
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
    assert (out_dir / "overlays" / "dev" / "kustomization.yaml").is_file()
    assert (out_dir / "overlays" / "prod" / "kustomization.yaml").is_file()
    assert (out_dir / "helm" / "chart" / "Chart.yaml").is_file()
    assert (out_dir / "helm" / "chart" / "values.yaml").is_file()


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
