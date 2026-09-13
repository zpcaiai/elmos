"""OpenAPI, Postman and Gherkin Specification Normalization Engine.

Normalizes diverse API contracts and acceptance test scenarios into typed,
canonical test models with schema completeness scoring and validation invariants.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set


@dataclass
class CanonicalParameter:
    name: str
    in_location: str  # query, path, header, cookie
    required: bool
    schema_type: str
    format: Optional[str] = None
    default: Optional[Any] = None
    enum_values: List[Any] = field(default_factory=list)


@dataclass
class CanonicalEndpointSpec:
    endpoint_id: str
    path: str
    method: str
    summary: str
    tags: List[str]
    parameters: List[CanonicalParameter]
    request_body_schema: Optional[Dict[str, Any]] = None
    responses: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    security_schemes: List[str] = field(default_factory=list)

    def compute_signature(self) -> str:
        raw = f"{self.method.upper()}:{self.path}:{len(self.parameters)}:{sorted(self.responses.keys())}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


@dataclass
class CanonicalGherkinScenario:
    scenario_id: str
    feature_title: str
    scenario_title: str
    tags: List[str]
    given_steps: List[str]
    when_steps: List[str]
    then_steps: List[str]

    def is_executable(self) -> bool:
        return bool(self.when_steps and self.then_steps)


@dataclass
class CanonicalTestSpec:
    spec_id: str
    source_type: str
    title: str
    version: str
    endpoints: List[CanonicalEndpointSpec] = field(default_factory=list)
    scenarios: List[CanonicalGherkinScenario] = field(default_factory=list)
    completeness_score: float = 0.0

    def compute_merkle_root(self) -> str:
        hashes = [ep.compute_signature() for ep in self.endpoints]
        hashes.extend(hashlib.sha256(s.scenario_title.encode('utf-8')).hexdigest() for s in self.scenarios)
        combined = ''.join(sorted(hashes))
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()


class SpecNormalizationEngine:
    """Normalizes OpenAPI 3.0/3.1, Postman and Gherkin into CanonicalTestSpec."""

    @classmethod
    def normalize_openapi(cls, spec_data: Dict[str, Any]) -> CanonicalTestSpec:
        info = spec_data.get("info", {})
        title = info.get("title", "Untitled API")
        version = info.get("version", "1.0.0")
        spec_id = f"openapi-{hashlib.sha256(title.encode('utf-8')).hexdigest()[:8]}"

        endpoints: List[CanonicalEndpointSpec] = []
        paths = spec_data.get("paths", {})

        for path_str, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method in ("get", "post", "put", "delete", "patch", "head", "options"):
                if method not in path_item:
                    continue
                op = path_item[method]
                if not isinstance(op, dict):
                    continue

                endpoint_id = op.get("operationId", f"{method}_{re.sub(r'[^a-zA-Z0-9]', '_', path_str)}")
                summary = op.get("summary", "")
                tags = op.get("tags", [])

                # Parameters
                params: List[CanonicalParameter] = []
                for p in op.get("parameters", []):
                    if isinstance(p, dict):
                        p_schema = p.get("schema", {})
                        params.append(
                            CanonicalParameter(
                                name=p.get("name", ""),
                                in_location=p.get("in", "query"),
                                required=p.get("required", False),
                                schema_type=p_schema.get("type", "string"),
                                format=p_schema.get("format"),
                                default=p_schema.get("default"),
                                enum_values=p_schema.get("enum", []),
                            )
                        )

                # Request Body
                req_body = op.get("requestBody", {})
                content = req_body.get("content", {})
                json_schema = content.get("application/json", {}).get("schema")

                # Responses
                responses: Dict[int, Dict[str, Any]] = {}
                for status_code_str, resp_item in op.get("responses", {}).items():
                    if status_code_str.isdigit():
                        code = int(status_code_str)
                        resp_schema = resp_item.get("content", {}).get("application/json", {}).get("schema", {})
                        responses[code] = resp_schema

                endpoints.append(
                    CanonicalEndpointSpec(
                        endpoint_id=endpoint_id,
                        path=path_str,
                        method=method.upper(),
                        summary=summary,
                        tags=tags,
                        parameters=params,
                        request_body_schema=json_schema,
                        responses=responses,
                    )
                )

        # Completeness calculation
        total_fields = len(endpoints) * 4
        scored_fields = sum(
            (1 if ep.summary else 0)
            + (1 if ep.responses else 0)
            + (1 if ep.tags else 0)
            + (1 if (ep.method in ('GET', 'DELETE') or ep.request_body_schema) else 0)
            for ep in endpoints
        )
        completeness = round((scored_fields / total_fields) * 100.0, 2) if total_fields > 0 else 100.0

        return CanonicalTestSpec(
            spec_id=spec_id,
            source_type="OPENAPI",
            title=title,
            version=version,
            endpoints=endpoints,
            completeness_score=completeness,
        )

    @classmethod
    def normalize_gherkin(cls, gherkin_text: str) -> CanonicalTestSpec:
        feature_match = re.search(r"Feature:\s*(.+)", gherkin_text)
        feature_title = feature_match.group(1).strip() if feature_match else "Untitled Feature"
        spec_id = f"gherkin-{hashlib.sha256(feature_title.encode('utf-8')).hexdigest()[:8]}"

        scenarios: List[CanonicalGherkinScenario] = []
        raw_scenarios = re.split(r"Scenario(?: Outline)?:", gherkin_text)[1:]

        for idx, raw_sc in enumerate(raw_scenarios, 1):
            lines = [line.strip() for line in raw_sc.strip().splitlines() if line.strip()]
            if not lines:
                continue
            scenario_title = lines[0]
            given_steps: List[str] = []
            when_steps: List[str] = []
            then_steps: List[str] = []

            for l in lines[1:]:
                if l.startswith("Given "):
                    given_steps.append(l[6:])
                elif l.startswith("When "):
                    when_steps.append(l[5:])
                elif l.startswith("Then "):
                    then_steps.append(l[5:])
                elif l.startswith("And "):
                    if then_steps:
                        then_steps.append(l[4:])
                    elif when_steps:
                        when_steps.append(l[4:])
                    elif given_steps:
                        given_steps.append(l[4:])

            scenarios.append(
                CanonicalGherkinScenario(
                    scenario_id=f"SCENARIO-{idx}",
                    feature_title=feature_title,
                    scenario_title=scenario_title,
                    tags=[],
                    given_steps=given_steps,
                    when_steps=when_steps,
                    then_steps=then_steps,
                )
            )

        completeness = 100.0 if all(s.is_executable() for s in scenarios) else 50.0

        return CanonicalTestSpec(
            spec_id=spec_id,
            source_type="GHERKIN",
            title=feature_title,
            version="1.0.0",
            scenarios=scenarios,
            completeness_score=completeness,
        )
