from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import Any

from .models import FieldSpec, SynthesisRequest


def clean(text: str) -> str:
    return dedent(text).lstrip().rstrip() + "\n"


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def kebab(value: str) -> str:
    return re.sub(r"_+", "-", value)


def camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def pascal_identifier(value: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in value.split("_"))


def sample_value(field: FieldSpec) -> Any:
    return {
        "string": f"sample-{kebab(field.name)}",
        "integer": 1,
        "number": 1.5,
        "boolean": True,
        "datetime": "2026-01-01T00:00:00Z",
    }[field.type]


def sample_payload(request: SynthesisRequest) -> dict[str, Any]:
    return {field.name: sample_value(field) for field in request.entity.fields}


def openapi_yaml(request: SynthesisRequest, *, server_port: int) -> str:
    entity = request.entity
    lines = [
        "openapi: 3.1.0",
        "info:",
        f"  title: {request.project_name} API",
        "  version: 1.0.0",
        f"  description: {json.dumps(request.description, ensure_ascii=False)}",
        "servers:",
        f"  - url: http://localhost:{server_port}",
        "paths:",
        "  /health:",
        "    get:",
        "      operationId: health",
        "      responses:",
        "        '200':",
        "          description: Service is healthy",
        f"  /api/v1/{entity.plural}:",
        "    get:",
        f"      operationId: list{request.entity_class}s",
        "      responses:",
        "        '200':",
        "          description: All records",
        "    post:",
        f"      operationId: create{request.entity_class}",
        "      requestBody:",
        "        required: true",
        "        content:",
        "          application/json:",
        "            schema:",
        f"              $ref: '#/components/schemas/{request.entity_class}Create'",
        "      responses:",
        "        '201':",
        "          description: Created",
        f"  /api/v1/{entity.plural}/{{id}}:",
        "    get:",
        f"      operationId: get{request.entity_class}",
        "      parameters:",
        "        - name: id",
        "          in: path",
        "          required: true",
        "          schema:",
        "            type: string",
        "      responses:",
        "        '200':",
        "          description: Found",
        "        '404':",
        "          description: Not found",
        "components:",
        "  schemas:",
    ]

    def append_schema(name: str, *, include_id: bool) -> None:
        required = (["id"] if include_id else []) + [field.name for field in entity.fields if field.required]
        lines.extend([f"    {name}:", "      type: object", "      additionalProperties: false", "      required:"])
        lines.extend(f"        - {field_name}" for field_name in required)
        lines.append("      properties:")
        if include_id:
            lines.extend(["        id:", "          type: string"])
        for field in entity.fields:
            schema_type, schema_format = {
                "string": ("string", None),
                "integer": ("integer", "int64"),
                "number": ("number", "double"),
                "boolean": ("boolean", None),
                "datetime": ("string", "date-time"),
            }[field.type]
            lines.extend([f"        {field.name}:", f"          type: {schema_type}"])
            if schema_format:
                lines.append(f"          format: {schema_format}")

    append_schema(request.entity_class, include_id=True)
    append_schema(f"{request.entity_class}Create", include_id=False)
    return "\n".join(lines) + "\n"


def dockerignore() -> str:
    return clean(
        """
        .git
        .github
        .idea
        .vscode
        .env
        .venv
        bin
        obj
        target
        __pycache__
        *.pyc
        """
    )


def gitignore() -> str:
    return clean(
        """
        .env
        .idea/
        .vscode/
        .venv/
        __pycache__/
        *.py[cod]
        target/
        bin/
        obj/
        TestResults/
        """
    )


def env_example(request: SynthesisRequest, port: int) -> str:
    return clean(
        f"""
        APP_NAME={request.project_name}
        APP_ENV=development
        PORT={port}
        LOG_LEVEL=INFO
        # Add secret references through the deployment platform. Do not commit values here.
        """
    )


def kubernetes_yaml(request: SynthesisRequest, *, language: str, port: int) -> str:
    app = f"{request.project_name}-{language}"
    return clean(
        f"""
        apiVersion: apps/v1
        kind: Deployment
        metadata:
          name: {app}
        spec:
          replicas: 1
          selector:
            matchLabels:
              app: {app}
          template:
            metadata:
              labels:
                app: {app}
            spec:
              automountServiceAccountToken: false
              securityContext:
                runAsNonRoot: true
                seccompProfile:
                  type: RuntimeDefault
              containers:
                - name: app
                  image: {app}:local
                  imagePullPolicy: IfNotPresent
                  ports:
                    - name: http
                      containerPort: {port}
                  env:
                    - name: PORT
                      value: "{port}"
                    - name: APP_ENV
                      value: production
                  readinessProbe:
                    httpGet:
                      path: /health
                      port: http
                    initialDelaySeconds: 5
                    periodSeconds: 5
                  livenessProbe:
                    httpGet:
                      path: /health
                      port: http
                    initialDelaySeconds: 15
                    periodSeconds: 10
                  resources:
                    requests:
                      cpu: 100m
                      memory: 128Mi
                    limits:
                      cpu: 500m
                      memory: 512Mi
                  securityContext:
                    allowPrivilegeEscalation: false
                    readOnlyRootFilesystem: true
                    capabilities:
                      drop: ["ALL"]
        ---
        apiVersion: v1
        kind: Service
        metadata:
          name: {app}
        spec:
          selector:
            app: {app}
          ports:
            - name: http
              port: 80
              targetPort: http
        """
    )


def target_readme(request: SynthesisRequest, *, language: str, framework: str, port: int, commands: str) -> str:
    return clean(
        f"""
        # {request.project_name} — {language}

        {request.description}

        Generated from the approved ELMOS requirement baseline using the `{framework}` profile.
        It is a complete runnable starter with CRUD, health, tests, externalized configuration,
        CI, a non-root container, Kubernetes resources, OpenAPI, and requirement traceability.

        ## Run and test

        ```bash
        {commands}
        ```

        The API listens on `http://localhost:{port}`. Health is `GET /health`; the primary
        collection is `/api/v1/{request.entity.plural}`.

        ## Evidence boundary

        Local build/startup evidence is engineering evidence only. Authentication, durable
        database storage, immutable image digests, production secrets, deployment, SLOs,
        backup/restore, and external certification remain `NOT_RUN` until configured and tested.
        """
    )
