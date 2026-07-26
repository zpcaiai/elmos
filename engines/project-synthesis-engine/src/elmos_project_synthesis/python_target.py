from __future__ import annotations

import json

from .container_images import PYTHON_IMAGE
from .models import FieldSpec, SynthesisRequest, pascal
from .python_production_target import render_python_production
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


def _python_docstring(description: str) -> str:
    chunks = [description[index : index + 40] for index in range(0, len(description), 40)]
    literals = "\n".join(f"    {json.dumps(chunk, ensure_ascii=False)}" for chunk in chunks)
    return f"__doc__ = (\n{literals}\n)\n"


def render_python(request: SynthesisRequest, port: int) -> dict[str, str]:
    if request.requires_database or request.requires_authentication:
        return render_python_production(request, port)
    package_name = request.project_name.replace("-", "_")
    toml_description = json.dumps(request.description, ensure_ascii=False)
    datetime_import = (
        "from datetime import datetime\n\n"
        if any(field.type == "datetime" for entity in request.entities for field in entity.fields)
        else ""
    )
    model_blocks: list[str] = []
    app_imports: list[str] = []
    store_blocks: list[str] = []
    route_blocks: list[str] = []
    test_blocks: list[str] = []
    for entity in request.entities:
        entity_class = pascal(entity.singular)
        field_lines: list[str] = []
        for field in entity.fields:
            default = "" if field.required else " | None = None"
            field_lines.append(f"    {field.name}: {_python_type(field)}{default}")
        fields = "\n".join(field_lines)
        model_blocks.append(
            f"class {entity_class}Upsert(BaseModel):\n"
            '    model_config = ConfigDict(extra="forbid")\n\n'
            f"{fields}\n\n\n"
            f"class {entity_class}({entity_class}Upsert):\n"
            "    id: str"
        )
        app_imports.extend((entity_class, f"{entity_class}Upsert"))
        store_name = f"_{entity.plural}"
        store_blocks.append(f"{store_name}: dict[str, {entity_class}] = {{}}")
        route_blocks.append(
            clean(
                f"""
                @app.get("/api/v1/{entity.plural}", response_model=list[{entity_class}])
                def list_{entity.plural}() -> list[{entity_class}]:
                    return [{store_name}[key] for key in sorted({store_name})]


                @app.get("/api/v1/{entity.plural}/{{record_id}}", response_model={entity_class})
                def get_{entity.singular}(record_id: str) -> {entity_class}:
                    record = {store_name}.get(record_id)
                    if record is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
                    return record


                @app.post(
                    "/api/v1/{entity.plural}",
                    response_model={entity_class},
                    status_code=status.HTTP_201_CREATED,
                )
                def create_{entity.singular}(payload: {entity_class}Upsert) -> {entity_class}:
                    record = {entity_class}(id=str(uuid4()), **payload.model_dump())
                    {store_name}[record.id] = record
                    return record


                @app.put("/api/v1/{entity.plural}/{{record_id}}", response_model={entity_class})
                def update_{entity.singular}(record_id: str, payload: {entity_class}Upsert) -> {entity_class}:
                    if record_id not in {store_name}:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
                    record = {entity_class}(id=record_id, **payload.model_dump())
                    {store_name}[record_id] = record
                    return record


                @app.delete(
                    "/api/v1/{entity.plural}/{{record_id}}",
                    status_code=status.HTTP_204_NO_CONTENT,
                    response_class=Response,
                )
                def delete_{entity.singular}(record_id: str) -> Response:
                    if {store_name}.pop(record_id, None) is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="record not found")
                    return Response(status_code=status.HTTP_204_NO_CONTENT)
                """
            ).rstrip()
        )
        sample = repr(sample_payload(request, entity))
        test_blocks.append(
            clean(
                f"""
                def test_{entity.singular}_full_crud_journey() -> None:
                    payload = {sample}
                    created = client.post("/api/v1/{entity.plural}", json=payload)
                    assert created.status_code == 201
                    record_id = created.json()["id"]

                    listing = client.get("/api/v1/{entity.plural}")
                    assert listing.status_code == 200
                    assert listing.json()[0]["id"] == record_id

                    fetched = client.get(f"/api/v1/{entity.plural}/{{record_id}}")
                    assert fetched.status_code == 200

                    updated = client.put(f"/api/v1/{entity.plural}/{{record_id}}", json=payload)
                    assert updated.status_code == 200

                    deleted = client.delete(f"/api/v1/{entity.plural}/{{record_id}}")
                    assert deleted.status_code == 204
                    assert client.get(f"/api/v1/{entity.plural}/{{record_id}}").status_code == 404
                """
            ).rstrip()
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
            description = {toml_description}
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
        f"src/{package_name}/__init__.py": _python_docstring(request.description),
        f"src/{package_name}/models.py": (
            f"{datetime_import}from pydantic import BaseModel, ConfigDict\n\n\n" + "\n\n\n".join(model_blocks) + "\n"
        ),
        f"src/{package_name}/app.py": (
            "from __future__ import annotations\n\n"
            "import os\n"
            "from uuid import uuid4\n\n"
            "from fastapi import FastAPI, HTTPException, Response, status\n\n"
            "from .models import (\n" + "".join(f"    {model},\n" for model in sorted(app_imports)) + ")\n\n"
            f'app = FastAPI(title="{request.project_name}", version="1.0.0")\n'
            f"{chr(10).join(store_blocks)}\n\n\n"
            '@app.get("/health")\n'
            "def health() -> dict[str, str]:\n"
            f'    return {{"status": "UP", "service": os.getenv("APP_NAME", "{request.project_name}")}}\n\n\n'
            f"{chr(10).join(route_blocks)}\n"
        ),
        f"src/{package_name}/__main__.py": clean(
            f"""
            import os

            import uvicorn

            if __name__ == "__main__":
                uvicorn.run(
                    "{package_name}.app:app",
                    host=os.getenv("HOST", "127.0.0.1"),
                    port=int(os.getenv("PORT", "{port}")),
                    log_level=os.getenv("LOG_LEVEL", "INFO").lower(),
                )
            """
        ),
        "tests/test_api.py": (
            "from fastapi.testclient import TestClient\n\n"
            f"from {package_name}.app import app\n\n"
            "client = TestClient(app)\n\n\n"
            "def test_health_journey() -> None:\n"
            '    health = client.get("/health")\n'
            "    assert health.status_code == 200\n"
            '    assert health.json()["status"] == "UP"\n\n\n'
            f"{chr(10).join(test_blocks)}\n"
        ),
        "openapi.yaml": openapi_yaml(request, server_port=port),
        "Dockerfile": clean(
            f"""
            FROM {PYTHON_IMAGE}
            ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0
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
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
                  - uses: astral-sh/setup-uv@d0cc045d04ccac9d8b7881df0226f9e82c39688e # v6
                  - run: uv sync --locked --python 3.12
                  - run: uv run pytest
                  - run: uv run ruff check src tests
                  - run: uv run mypy src
            """
        ),
        "Makefile": clean(
            f"""
            .PHONY: sync test check run
            sync:
            \tuv sync --locked --python 3.12
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
            commands=f"uv sync --locked --python 3.12\nuv run pytest\nPORT={port} uv run python -m {package_name}",
        ),
    }
    return files
