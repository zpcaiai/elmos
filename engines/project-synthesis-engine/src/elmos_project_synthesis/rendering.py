from __future__ import annotations

import json
import re
from textwrap import dedent
from typing import Any

from .models import EntitySpec, FieldSpec, SynthesisRequest, pascal


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


def sample_payload(request: SynthesisRequest, entity: EntitySpec | None = None) -> dict[str, Any]:
    selected = entity or request.entity
    return {field.name: sample_value(field) for field in selected.fields}


def openapi_yaml(request: SynthesisRequest, *, server_port: int) -> str:
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
    ]

    for entity in request.entities:
        entity_class = pascal(entity.singular)
        lines.extend(
            [
                f"  /api/v1/{entity.plural}:",
                "    get:",
                f"      operationId: list{entity_class}s",
                "      responses:",
                "        '200':",
                "          description: All records",
                "    post:",
                f"      operationId: create{entity_class}",
                "      requestBody:",
                "        required: true",
                "        content:",
                "          application/json:",
                "            schema:",
                f"              $ref: '#/components/schemas/{entity_class}Create'",
                "      responses:",
                "        '201':",
                "          description: Created",
                f"  /api/v1/{entity.plural}/{{id}}:",
                "    get:",
                f"      operationId: get{entity_class}",
                "      parameters:",
                "        - $ref: '#/components/parameters/RecordId'",
                "      responses:",
                "        '200':",
                "          description: Found",
                "        '404':",
                "          description: Not found",
                "    put:",
                f"      operationId: update{entity_class}",
                "      parameters:",
                "        - $ref: '#/components/parameters/RecordId'",
                "      requestBody:",
                "        required: true",
                "        content:",
                "          application/json:",
                "            schema:",
                f"              $ref: '#/components/schemas/{entity_class}Create'",
                "      responses:",
                "        '200':",
                "          description: Updated",
                "        '404':",
                "          description: Not found",
                "    delete:",
                f"      operationId: delete{entity_class}",
                "      parameters:",
                "        - $ref: '#/components/parameters/RecordId'",
                "      responses:",
                "        '204':",
                "          description: Deleted",
                "        '404':",
                "          description: Not found",
            ]
        )

    lines.extend(
        [
            "components:",
            "  parameters:",
            "    RecordId:",
            "      name: id",
            "      in: path",
            "      required: true",
            "      schema:",
            "        type: string",
            "  schemas:",
        ]
    )

    def append_schema(entity: EntitySpec, name: str, *, include_id: bool) -> None:
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

    for entity in request.entities:
        entity_class = pascal(entity.singular)
        append_schema(entity, entity_class, include_id=True)
        append_schema(entity, f"{entity_class}Create", include_id=False)
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
    readiness_path = "/health/ready" if request.requires_database else "/health"
    liveness_path = "/health/live" if request.requires_database else "/health"
    production_environment = ""
    secret_volume = ""
    network_policy = ""
    if request.requires_authentication:
        auth_secret_key = "jwt-hmac" if request.auth_mode == "jwt" else "oidc-jwks"
        auth_secret_env = "ELMOS_JWT_HMAC_SECRET_FILE" if request.auth_mode == "jwt" else "ELMOS_OIDC_JWKS_FILE"
        production_environment = f"""
                    - name: ELMOS_DATABASE_URL_FILE
                      value: /run/secrets/database-url
                    - name: {auth_secret_env}
                      value: /run/secrets/{auth_secret_key}
                    - name: ELMOS_AUTH_ISSUER
                      valueFrom:
                        configMapKeyRef:
                          name: {app}-runtime
                          key: auth-issuer
                    - name: ELMOS_AUTH_AUDIENCE
                      valueFrom:
                        configMapKeyRef:
                          name: {app}-runtime
                          key: auth-audience"""
        secret_volume = f"""
                  volumeMounts:
                    - name: runtime-secrets
                      mountPath: /run/secrets
                      readOnly: true
              volumes:
                - name: runtime-secrets
                  secret:
                    secretName: {app}-runtime
                    defaultMode: 256
                    items:
                      - key: database-url
                        path: database-url
                      - key: {auth_secret_key}
                        path: {auth_secret_key}"""
        network_policy = f"""
        ---
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: {app}-default-deny
        spec:
          podSelector:
            matchLabels:
              app: {app}
          policyTypes:
            - Ingress
            - Egress
          ingress:
            - from:
                - podSelector: {{}}
              ports:
                - protocol: TCP
                  port: {port}
          egress:
            - to:
                - namespaceSelector:
                    matchLabels:
                      kubernetes.io/metadata.name: kube-system
              ports:
                - protocol: UDP
                  port: 53
                - protocol: TCP
                  port: 53
            - to:
                - podSelector:
                    matchLabels:
                      elmos.io/database-for: {app}
              ports:
                - protocol: TCP
                  port: 5432
        ---
        apiVersion: policy/v1
        kind: PodDisruptionBudget
        metadata:
          name: {app}
        spec:
          minAvailable: 1
          selector:
            matchLabels:
              app: {app}"""
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
        {production_environment}
                  readinessProbe:
                    httpGet:
                      path: {readiness_path}
                      port: http
                    initialDelaySeconds: 5
                    periodSeconds: 5
                  livenessProbe:
                    httpGet:
                      path: {liveness_path}
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
        {secret_volume}
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
        {network_policy}
        """
    )


def target_readme(request: SynthesisRequest, *, language: str, framework: str, port: int, commands: str) -> str:
    resources = ", ".join(f"`/api/v1/{entity.plural}`" for entity in request.entities)
    return clean(
        f"""
        # {request.project_name} — {language}

        {request.description}

        Generated from the approved ELMOS requirement baseline using the `{framework}` profile.
        It is a runnable starter with full in-memory CRUD, health, tests, externalized configuration,
        CI, a non-root container, Kubernetes resources, OpenAPI, and requirement traceability.

        ## Run and test

        ```bash
        {commands}
        ```

        The API listens on `http://localhost:{port}`. Health is `GET /health`; generated
        collections are {resources}.

        ## Evidence boundary

        Local build/startup evidence is engineering evidence only. The requested authentication
        profile is `{request.auth_mode}` and persistence profile is `{request.persistence}`.
        Provider enforcement, durable database migration, immutable image digests, deployment, SLOs,
        backup/restore, and external certification remain `NOT_RUN` until configured and tested.
        """
    )
