from __future__ import annotations

from .models import FieldSpec, SynthesisRequest
from .rendering import (
    clean,
    dockerignore,
    env_example,
    gitignore,
    kubernetes_yaml,
    openapi_yaml,
    sample_payload,
    target_readme,
)


def _python_type(field: FieldSpec) -> str:
    return {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "datetime": "datetime",
    }[field.type]


def render_python(request: SynthesisRequest, port: int) -> dict[str, str]:
    package_name = request.project_name.replace("-", "_")
    entity_class = request.entity_class
    field_lines: list[str] = []
    for field in request.entity.fields:
        default = "" if field.required else " | None = None"
        field_lines.append(f"    {field.name}: {_python_type(field)}{default}")
    fields = "\n".join(field_lines)
    sample = repr(sample_payload(request))
    datetime_import = (
        "from datetime import datetime\n\n"
        if any(field.type == "datetime" for field in request.entity.fields)
        else ""
    )
    files: dict[str, str] = {
        ".gitignore": gitignore(),
        ".dockerignore": dockerignore(),
        ".env.example": env_example(request, port),
        "pyproject.toml": clean(
            f"""
            [project]
            name = "{request.project_name}"
            version = "1.0.0"
            description = "{request.description.replace(chr(34), chr(39))}"
            requires-python = ">=3.12,<3.13"
            dependencies = [
              "fastapi==0.116.1",
              "pydantic==2.11.7",
              "uvicorn==0.35.0",
            ]

            [dependency-groups]
            dev = [
              "httpx==0.28.1",
              "mypy==1.17.0",
              "pytest==8.4.1",
              "ruff==0.12.5",
            ]

            [build-system]
            requires = ["hatchling==1.27.0"]
            build-backend = "hatchling.build"

            [tool.hatch.build.targets.wheel]
            packages = ["src/{package_name}"]

            [tool.pytest.ini_options]
            addopts = "-q --strict-markers"
            testpaths = ["tests"]

            [tool.ruff]
            target-version = "py312"
            line-length = 120

            [tool.ruff.lint]
            select = ["E", "F", "I", "B", "UP", "S"]
            ignore = ["S101"]

            [tool.mypy]
            python_version = "3.12"
            strict = true
            packages = ["{package_name}"]
            """
        ),
        "requirements.lock": clean(
            """
            annotated-types==0.7.0
            anyio==4.9.0
            certifi==2025.7.14
            click==8.2.1
            fastapi==0.116.1
            h11==0.16.0
            httpcore==1.0.9
            httpx==0.28.1
            idna==3.10
            iniconfig==2.1.0
            packaging==25.0
            pluggy==1.6.0
            pydantic==2.11.7
            pydantic-core==2.33.2
            pygments==2.19.2
            pytest==8.4.1
            sniffio==1.3.1
            starlette==0.47.2
            typing-extensions==4.14.1
            typing-inspection==0.4.1
            uvicorn==0.35.0
            """
        ),
        f"src/{package_name}/__init__.py": f'"""{request.description}"""\n',
        f"src/{package_name}/models.py": (
            f"{datetime_import}from pydantic import BaseModel, ConfigDict\n\n\n"
            f"class {entity_class}Create(BaseModel):\n"
            '    model_config = ConfigDict(extra="forbid")\n\n'
            f"{fields}\n\n\n"
            f"class {entity_class}({entity_class}Create):\n"
            "    id: str\n"
        ),
        f"src/{package_name}/app.py": clean(
            f"""
            from __future__ import annotations

            import os
            from uuid import uuid4

            from fastapi import FastAPI, HTTPException, status

            from .models import {entity_class}, {entity_class}Create

            app = FastAPI(title="{request.project_name}", version="1.0.0")
            _records: dict[str, {entity_class}] = {{}}


            @app.get("/health")
            def health() -> dict[str, str]:
                return {{"status": "UP", "service": os.getenv("APP_NAME", "{request.project_name}")}}


            @app.get("/api/v1/{request.entity.plural}", response_model=list[{entity_class}])
            def list_records() -> list[{entity_class}]:
                return [_records[key] for key in sorted(_records)]


            @app.get("/api/v1/{request.entity.plural}/{{record_id}}", response_model={entity_class})
            def get_record(record_id: str) -> {entity_class}:
                record = _records.get(record_id)
                if record is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
                return record


            @app.post(
                "/api/v1/{request.entity.plural}",
                response_model={entity_class},
                status_code=status.HTTP_201_CREATED,
            )
            def create_record(payload: {entity_class}Create) -> {entity_class}:
                record = {entity_class}(id=str(uuid4()), **payload.model_dump())
                _records[record.id] = record
                return record
            """
        ),
        f"src/{package_name}/__main__.py": clean(
            f"""
            import os

            import uvicorn

            if __name__ == "__main__":
                uvicorn.run(
                    "{package_name}.app:app",
                    host="0.0.0.0",  # noqa: S104 - container listener is intentional
                    port=int(os.getenv("PORT", "{port}")),
                    log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
                )
            """
        ),
        "tests/test_api.py": clean(
            f"""
            from fastapi.testclient import TestClient

            from {package_name}.app import app

            client = TestClient(app)


            def test_requirement_traced_crud_and_health_journey() -> None:
                health = client.get("/health")
                assert health.status_code == 200
                assert health.json()["status"] == "UP"

                payload = {sample}
                created = client.post("/api/v1/{request.entity.plural}", json=payload)
                assert created.status_code == 201
                record_id = created.json()["id"]

                listing = client.get("/api/v1/{request.entity.plural}")
                assert listing.status_code == 200
                assert listing.json()[0]["id"] == record_id

                fetched = client.get(f"/api/v1/{request.entity.plural}/{{record_id}}")
                assert fetched.status_code == 200
            """
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM python:3.12.11-slim
            ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
            RUN groupadd --system app && useradd --system --gid app --uid 10001 app
            WORKDIR /app
            COPY requirements.lock ./
            RUN pip install --no-cache-dir -r requirements.lock
            COPY pyproject.toml ./
            COPY src ./src
            RUN pip install --no-cache-dir --no-deps .
            USER 10001:10001
            EXPOSE {port}
            CMD ["python", "-m", "{package_name}"]
            """
        ),
        "deploy/kubernetes.yaml": kubernetes_yaml(request, language="python", port=port),
        ".github/workflows/ci.yml": clean(
            """
            name: python-ci
            on:
              push:
              pull_request:
            permissions:
              contents: read
            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - uses: actions/checkout@v4
                  - uses: astral-sh/setup-uv@v6
                  - run: uv sync --python 3.12
                  - run: uv run pytest
                  - run: uv run ruff check src tests
                  - run: uv run mypy src
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: sync test check run
            sync:
            \tuv sync --python 3.12
            test:
            \tuv run pytest
            check:
            \tuv run ruff check src tests
            \tuv run mypy src
            run:
            \tPORT={port} uv run python -m {package_name}
            """
        ),
        "README.md": target_readme(
            request,
            language="Python 3.12",
            framework="FastAPI 0.116.1",
            port=port,
            commands=f"uv sync --python 3.12\nuv run pytest\nPORT={port} uv run python -m {package_name}",
        ),
    }
    return files
