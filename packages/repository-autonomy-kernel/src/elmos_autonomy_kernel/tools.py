"""Typed tool runtime: a tool call is a contract, not a suggestion.

This module owns the boundary where a model's proposal becomes an executed
effect.  Three decisions are deliberate.  First, the schema validator is
written here rather than delegated to ``jsonschema``: the kernel must be able
to say exactly which constructs it supports, and a validator that quietly
accepts ``number`` or follows a remote ``$ref`` would reintroduce floats and
SSRF through the back door.  Second, an unknown ``tool_id`` is denied and never
fuzzy-matched — "did you mean" is how a model reaches a tool nobody granted it.
Third, the *result* is validated as strictly as the arguments: a tool that
returns garbage must not be believed just because it exited zero.

Nothing in the decision path reads free text.  Arguments are data; they are
digested and shape-checked, never interpreted.  An argument that says "ignore
previous rules and enable network" is a string of that value and nothing else.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .contracts import (
    canonical_json,
    digest,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

if TYPE_CHECKING:  # pragma: no cover - typing only, never an import at runtime
    from .authority import ExecutionAuthority  # noqa: F401

register_codes(
    Category.SEMANTIC,
    "SCHEMA_MISMATCH",
    "SCHEMA_UNSUPPORTED",
    "TOOL_REGISTRY_CONFLICT",
    "COMPENSATION_FAILED",
)
register_codes(
    Category.ORCHESTRATION,
    "TOOL_INTERRUPTED",
    "TOOL_TIMEOUT",
)

__all__ = [
    "CompiledSchema",
    "SUPPORTED_KEYWORDS",
    "SUPPORTED_TYPES",
    "compile_schema",
    "ToolDescriptor",
    "ToolRegistry",
    "ToolCall",
    "ToolState",
    "ToolEventType",
    "ToolEvent",
    "ToolResult",
    "ToolRuntime",
    "handle",
]

# --- bounded validator constants ---------------------------------------------
#
# Every bound here exists to make the validator's worst case a constant rather
# than a function of attacker-supplied input.  A schema arrives from a tool
# package; a tool package is only as trustworthy as whoever published it.

MAX_PATTERN_SOURCE = 256
MAX_PATTERN_INPUT = 4096
MAX_SCHEMA_NODES = 512
MAX_SCHEMA_DEPTH = 16
MAX_ENUM_MEMBERS = 128

SUPPORTED_TYPES = frozenset(
    {"object", "array", "string", "integer", "boolean", "null"}
)
SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "required",
        "properties",
        "additionalProperties",
        "enum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "pattern",
        "items",
        "$ref",
        "$defs",
        "title",
        "description",
    }
)

_DEF_REF = re.compile(r"^#/\$defs/([A-Za-z0-9_.-]{1,64})$")


def _pointer(parent: str, token: str | int) -> str:
    """Append one JSON-pointer token (RFC 6901 escaping) to ``parent``."""

    text = str(token).replace("~", "~0").replace("/", "~1")
    return f"{parent}/{text}"


def _schema_unsupported(message: str, *, schema_path: str) -> KernelError:
    return KernelError(
        code="SCHEMA_UNSUPPORTED",
        message=f"{message} (at schema path {schema_path or '#'})",
        recommended_action="rewrite the schema using the kernel's supported subset",
        details={"schemaPath": schema_path or "#"},
    )


def _mismatch(message: str, *, pointer: str, keyword: str, schema_path: str) -> KernelError:
    return KernelError(
        code="SCHEMA_MISMATCH",
        message=f"{message} (at {pointer or '/'})",
        recommended_action="correct the value at the reported JSON pointer",
        details={
            "pointer": pointer or "",
            "keyword": keyword,
            "schemaPath": schema_path or "#",
        },
    )


@dataclass(frozen=True, slots=True)
class CompiledSchema:
    """A schema whose supported subset has already been proven at compile time.

    Compiling separates two failure classes that are constantly confused: a
    *schema* the kernel refuses to interpret (``SCHEMA_UNSUPPORTED``, the tool
    author's bug) and an *instance* that does not satisfy a schema the kernel
    does interpret (``SCHEMA_MISMATCH``, the caller's bug).  Patterns are
    compiled exactly once here, so a call site can never pay a regex-compilation
    cost per invocation or smuggle an unbounded pattern past the size guard.
    """

    root: Mapping[str, Any]
    defs: Mapping[str, Mapping[str, Any]]
    patterns: Mapping[str, re.Pattern[str]]
    source_digest: str

    def validate(self, instance: Any, *, pointer: str = "") -> None:
        """Raise ``SCHEMA_MISMATCH`` (with a JSON pointer) unless ``instance`` conforms."""

        _validate_node(self.root, instance, pointer=pointer, schema_path="#",
                       compiled=self, depth=0)


_SCHEMA_CACHE: dict[str, CompiledSchema] = {}


def compile_schema(schema: Mapping[str, Any]) -> CompiledSchema:
    """Compile and cache ``schema``.

    The cache is keyed by the schema's own digest, so two structurally identical
    schemas share one compilation and a mutated schema can never hit the entry
    of the version it was derived from.
    """

    schema = require_mapping(schema, "schema")
    key = digest(schema)
    cached = _SCHEMA_CACHE.get(key)
    if cached is not None:
        return cached

    defs_raw = schema.get("$defs", {})
    if not isinstance(defs_raw, Mapping):
        raise _schema_unsupported("$defs must be an object", schema_path="#/$defs")
    defs: dict[str, Mapping[str, Any]] = {}
    for name, sub in defs_raw.items():
        if not isinstance(name, str) or not _DEF_REF.match(f"#/$defs/{name}"):
            raise _schema_unsupported(
                f"illegal $defs name {name!r}", schema_path="#/$defs"
            )
        if not isinstance(sub, Mapping):
            raise _schema_unsupported(
                f"$defs/{name} must be an object", schema_path=f"#/$defs/{name}"
            )
        defs[name] = sub

    patterns: dict[str, re.Pattern[str]] = {}
    budget = [MAX_SCHEMA_NODES]
    _compile_node(schema, schema_path="#", defs=defs, patterns=patterns, depth=0,
                  budget=budget, allow_defs=True)
    for name, sub in sorted(defs.items()):
        _compile_node(sub, schema_path=f"#/$defs/{name}", defs=defs, patterns=patterns,
                      depth=0, budget=budget, allow_defs=False)

    compiled = CompiledSchema(
        root=schema,
        defs=dict(sorted(defs.items())),
        patterns=dict(sorted(patterns.items())),
        source_digest=key,
    )
    if len(_SCHEMA_CACHE) < 4096:  # a cache is a convenience, never a leak
        _SCHEMA_CACHE[key] = compiled
    return compiled


def _compile_node(node: Any, *, schema_path: str, defs: Mapping[str, Any],
                  patterns: dict[str, re.Pattern[str]], depth: int,
                  budget: list[int], allow_defs: bool) -> None:
    if depth > MAX_SCHEMA_DEPTH:
        raise _schema_unsupported(
            f"schema nests deeper than {MAX_SCHEMA_DEPTH} levels", schema_path=schema_path
        )
    budget[0] -= 1
    if budget[0] < 0:
        raise _schema_unsupported(
            f"schema exceeds {MAX_SCHEMA_NODES} nodes", schema_path=schema_path
        )
    if not isinstance(node, Mapping):
        raise _schema_unsupported("a schema node must be an object", schema_path=schema_path)

    unknown = sorted(set(node) - SUPPORTED_KEYWORDS)
    if unknown:
        raise _schema_unsupported(
            f"unsupported schema keywords {unknown}", schema_path=schema_path
        )
    if "$defs" in node and not allow_defs:
        raise _schema_unsupported(
            "$defs is only permitted at the schema root", schema_path=schema_path
        )

    if "$ref" in node:
        ref = node["$ref"]
        if not isinstance(ref, str):
            raise _schema_unsupported("$ref must be a string", schema_path=schema_path)
        match = _DEF_REF.match(ref)
        if match is None:
            raise _schema_unsupported(
                f"$ref {ref!r} is not a local #/$defs/<name> reference; a remote "
                "reference would make schema resolution a network fetch (SSRF)",
                schema_path=schema_path,
            )
        if match.group(1) not in defs:
            raise _schema_unsupported(
                f"$ref {ref!r} has no target in $defs", schema_path=schema_path
            )
        if sorted(set(node) - {"$ref", "title", "description"}):
            raise _schema_unsupported(
                "$ref must not be combined with other constraints", schema_path=schema_path
            )
        return

    declared = node.get("type")
    if declared is not None:
        if not isinstance(declared, str):
            raise _schema_unsupported(
                "type must be a single string; union types are not supported",
                schema_path=schema_path,
            )
        if declared not in SUPPORTED_TYPES:
            extra = (
                "; floats are banned kernel-wide, use integer or a decimal string"
                if declared in {"number", "float"}
                else ""
            )
            raise _schema_unsupported(
                f"unsupported type {declared!r}{extra}", schema_path=schema_path
            )

    for keyword in ("minLength", "maxLength", "minItems", "maxItems"):
        if keyword in node:
            value = node[keyword]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise _schema_unsupported(
                    f"{keyword} must be a non-negative integer", schema_path=schema_path
                )

    if "enum" in node:
        members = node["enum"]
        if not isinstance(members, Sequence) or isinstance(members, (str, bytes)):
            raise _schema_unsupported("enum must be an array", schema_path=schema_path)
        if not members:
            raise _schema_unsupported(
                "an empty enum can never be satisfied", schema_path=schema_path
            )
        if len(members) > MAX_ENUM_MEMBERS:
            raise _schema_unsupported(
                f"enum exceeds {MAX_ENUM_MEMBERS} members", schema_path=schema_path
            )
        canonical_json(list(members))  # rejects floats and unhashable exotica

    if "pattern" in node:
        source = node["pattern"]
        if not isinstance(source, str) or not source:
            raise _schema_unsupported("pattern must be a non-empty string",
                                      schema_path=schema_path)
        if len(source) > MAX_PATTERN_SOURCE:
            raise _schema_unsupported(
                f"pattern source exceeds {MAX_PATTERN_SOURCE} characters; an unbounded "
                "pattern is a denial-of-service primitive",
                schema_path=schema_path,
            )
        if source not in patterns:
            try:
                patterns[source] = re.compile(source)
            except re.error as exc:
                raise _schema_unsupported(
                    f"pattern does not compile: {exc}", schema_path=schema_path
                ) from exc

    additional = node.get("additionalProperties", False)
    if not isinstance(additional, bool):
        raise _schema_unsupported(
            "additionalProperties must be a boolean in this subset",
            schema_path=schema_path,
        )

    if "required" in node:
        required = node["required"]
        if not isinstance(required, Sequence) or isinstance(required, (str, bytes)):
            raise _schema_unsupported("required must be an array of strings",
                                      schema_path=schema_path)
        for name in required:
            if not isinstance(name, str) or not name:
                raise _schema_unsupported("required entries must be non-empty strings",
                                          schema_path=schema_path)

    properties = node.get("properties")
    if properties is not None:
        if not isinstance(properties, Mapping):
            raise _schema_unsupported("properties must be an object",
                                      schema_path=schema_path)
        for name in sorted(properties):
            _compile_node(properties[name], schema_path=f"{schema_path}/properties/{name}",
                          defs=defs, patterns=patterns, depth=depth + 1, budget=budget,
                          allow_defs=False)

    if "items" in node:
        _compile_node(node["items"], schema_path=f"{schema_path}/items", defs=defs,
                      patterns=patterns, depth=depth + 1, budget=budget, allow_defs=False)


def _type_matches(declared: str, instance: Any) -> bool:
    if declared == "object":
        return isinstance(instance, Mapping)
    if declared == "array":
        return isinstance(instance, (list, tuple)) and not isinstance(instance, (str, bytes))
    if declared == "string":
        return isinstance(instance, str)
    if declared == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if declared == "boolean":
        return isinstance(instance, bool)
    return instance is None


def _describe(instance: Any) -> str:
    if instance is None:
        return "null"
    if isinstance(instance, bool):
        return "boolean"
    if isinstance(instance, int):
        return "integer"
    if isinstance(instance, str):
        return "string"
    if isinstance(instance, Mapping):
        return "object"
    if isinstance(instance, (list, tuple)):
        return "array"
    return type(instance).__name__


def _validate_node(node: Mapping[str, Any], instance: Any, *, pointer: str,
                   schema_path: str, compiled: CompiledSchema, depth: int) -> None:
    if depth > MAX_SCHEMA_DEPTH:
        raise _mismatch("instance nests deeper than the schema allows", pointer=pointer,
                        keyword="$depth", schema_path=schema_path)

    ref = node.get("$ref")
    if isinstance(ref, str):
        match = _DEF_REF.match(ref)
        name = match.group(1) if match else ""
        target = compiled.defs.get(name)
        if target is None:  # pragma: no cover - compile time already proved this
            raise _schema_unsupported(f"dangling $ref {ref!r}", schema_path=schema_path)
        _validate_node(target, instance, pointer=pointer,
                       schema_path=f"#/$defs/{name}", compiled=compiled, depth=depth + 1)
        return

    if isinstance(instance, float):
        raise _mismatch(
            "float values are not representable in this kernel; use an integer "
            "or a decimal string",
            pointer=pointer, keyword="type", schema_path=schema_path,
        )

    declared = node.get("type")
    if isinstance(declared, str) and not _type_matches(declared, instance):
        raise _mismatch(
            f"expected type {declared!r}, got {_describe(instance)}",
            pointer=pointer, keyword="type", schema_path=schema_path,
        )

    if "enum" in node:
        members = list(node["enum"])
        if not any(_enum_equal(member, instance) for member in members):
            raise _mismatch(
                f"value is not one of the {len(members)} permitted enum members",
                pointer=pointer, keyword="enum", schema_path=schema_path,
            )

    if isinstance(instance, str):
        minimum = node.get("minLength")
        maximum = node.get("maxLength")
        if isinstance(minimum, int) and len(instance) < minimum:
            raise _mismatch(f"string is shorter than minLength {minimum}", pointer=pointer,
                            keyword="minLength", schema_path=schema_path)
        if isinstance(maximum, int) and len(instance) > maximum:
            raise _mismatch(f"string is longer than maxLength {maximum}", pointer=pointer,
                            keyword="maxLength", schema_path=schema_path)
        source = node.get("pattern")
        if isinstance(source, str):
            if len(instance) > MAX_PATTERN_INPUT:
                raise _mismatch(
                    f"string exceeds {MAX_PATTERN_INPUT} characters and is refused "
                    "rather than matched against a pattern",
                    pointer=pointer, keyword="pattern", schema_path=schema_path,
                )
            expression = compiled.patterns.get(source)
            if expression is None:  # pragma: no cover - compile time populated this
                raise _schema_unsupported("pattern was not compiled",
                                          schema_path=schema_path)
            if expression.search(instance) is None:
                raise _mismatch("string does not match the required pattern",
                                pointer=pointer, keyword="pattern", schema_path=schema_path)

    if isinstance(instance, Mapping):
        required = node.get("required")
        if isinstance(required, Sequence) and not isinstance(required, (str, bytes)):
            for name in required:
                if name not in instance:
                    raise _mismatch(f"required property {name!r} is absent",
                                    pointer=_pointer(pointer, str(name)),
                                    keyword="required", schema_path=schema_path)
        properties = node.get("properties")
        known = set(properties) if isinstance(properties, Mapping) else set()
        if not node.get("additionalProperties", False):
            for name in sorted(set(instance) - known):
                raise _mismatch(
                    f"property {name!r} is not declared and additionalProperties is false",
                    pointer=_pointer(pointer, str(name)),
                    keyword="additionalProperties", schema_path=schema_path,
                )
        if isinstance(properties, Mapping):
            for name in sorted(known & set(instance)):
                _validate_node(properties[name], instance[name],
                               pointer=_pointer(pointer, str(name)),
                               schema_path=f"{schema_path}/properties/{name}",
                               compiled=compiled, depth=depth + 1)

    if isinstance(instance, (list, tuple)) and not isinstance(instance, (str, bytes)):
        minimum = node.get("minItems")
        maximum = node.get("maxItems")
        if isinstance(minimum, int) and len(instance) < minimum:
            raise _mismatch(f"array has fewer than minItems {minimum}", pointer=pointer,
                            keyword="minItems", schema_path=schema_path)
        if isinstance(maximum, int) and len(instance) > maximum:
            raise _mismatch(f"array has more than maxItems {maximum}", pointer=pointer,
                            keyword="maxItems", schema_path=schema_path)
        item_schema = node.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(instance):
                _validate_node(item_schema, item, pointer=_pointer(pointer, index),
                               schema_path=f"{schema_path}/items", compiled=compiled,
                               depth=depth + 1)


def _enum_equal(member: Any, instance: Any) -> bool:
    """Enum comparison that refuses ``True == 1``.

    JSON has no way to say "the integer one, not the boolean true", so a naive
    ``in`` check lets a boolean satisfy an integer enum.  That is a real
    privilege bug when the enum is a mode selector.
    """

    if isinstance(member, bool) != isinstance(instance, bool):
        return False
    return member == instance


# --- descriptors and calls ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class ToolDescriptor:
    """The versioned ABI of one tool.

    ``side_effecting`` and ``declared_effects`` must agree: a tool that can
    change the world without saying what it changes cannot be compensated, and a
    tool that lists effects while claiming to be pure is lying in the direction
    that matters.  Both schemas are compiled at construction so that a broken
    tool package fails at registration rather than in the middle of a run.
    """

    tool_id: str
    version: str
    input_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]
    side_effecting: bool
    idempotent: bool
    required_scopes: tuple[str, ...] = ()
    declared_effects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.tool_id, "tool_id")
        require_str(self.version, "version", max_length=64)
        require_mapping(self.input_schema, "input_schema")
        require_mapping(self.output_schema, "output_schema")
        require_bool(self.side_effecting, "side_effecting")
        require_bool(self.idempotent, "idempotent")
        if self.side_effecting and not self.declared_effects:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"tool {self.tool_id!r} is side-effecting but declares no effects",
                recommended_action="declare every effect so it can be audited and compensated",
            )
        if not self.side_effecting and self.declared_effects:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"tool {self.tool_id!r} declares effects but claims to be pure",
                recommended_action="set side_effecting=True or remove the declared effects",
            )
        compile_schema(self.input_schema)
        compile_schema(self.output_schema)

    @property
    def input_validator(self) -> CompiledSchema:
        return compile_schema(self.input_schema)

    @property
    def output_validator(self) -> CompiledSchema:
        return compile_schema(self.output_schema)

    @property
    def key(self) -> str:
        return f"{self.tool_id}@{self.version}"

    def to_payload(self) -> dict[str, Any]:
        return {
            "toolId": self.tool_id,
            "version": self.version,
            "inputSchema": dict(self.input_schema),
            "outputSchema": dict(self.output_schema),
            "sideEffecting": self.side_effecting,
            "idempotent": self.idempotent,
            "requiredScopes": list(self.required_scopes),
            "declaredEffects": list(self.declared_effects),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ToolDescriptor:
        """Decode the wire form of ``contracts/schemas/tool-descriptor.schema.json``."""

        payload = require_mapping(payload, "tool_descriptor")
        known = {
            "toolId", "version", "inputSchema", "outputSchema", "sideEffecting",
            "idempotent", "requiredScopes", "declaredEffects",
        }
        reject_unknown_fields(payload, known, field_name="tool_descriptor")
        for name in ("toolId", "version", "inputSchema", "outputSchema", "sideEffecting"):
            if name not in payload:
                raise KernelError(
                    code="MISSING_REQUIRED_INPUT",
                    message=f"tool_descriptor.{name} is required",
                    recommended_action=f"supply tool_descriptor.{name}",
                )
        return cls(
            tool_id=require_identifier(payload["toolId"], "tool_descriptor.toolId"),
            version=require_str(payload["version"], "tool_descriptor.version", max_length=64),
            input_schema=require_mapping(payload["inputSchema"], "tool_descriptor.inputSchema"),
            output_schema=require_mapping(payload["outputSchema"],
                                          "tool_descriptor.outputSchema"),
            side_effecting=require_bool(payload["sideEffecting"],
                                        "tool_descriptor.sideEffecting"),
            idempotent=require_bool(payload.get("idempotent", False),
                                    "tool_descriptor.idempotent"),
            required_scopes=require_str_seq(payload.get("requiredScopes", ()),
                                            "tool_descriptor.requiredScopes"),
            declared_effects=require_str_seq(payload.get("declaredEffects", ()),
                                             "tool_descriptor.declaredEffects"),
        )


class ToolRegistry:
    """The set of tools that exist.

    Lookup is exact.  There is no nearest-match, no case folding and no alias
    table, because every one of those turns a typo — or a model's invention —
    into a call against a tool the operator never reviewed.
    """

    __slots__ = ("_by_key", "_versions")

    def __init__(self, descriptors: Sequence[ToolDescriptor] = ()) -> None:
        self._by_key: dict[str, ToolDescriptor] = {}
        self._versions: dict[str, list[str]] = {}
        for descriptor in descriptors:
            self.register(descriptor)

    def register(self, descriptor: ToolDescriptor) -> None:
        """Add a descriptor.  Re-registering the identical descriptor is a no-op."""

        existing = self._by_key.get(descriptor.key)
        if existing is not None:
            if existing.digest != descriptor.digest:
                raise KernelError(
                    code="TOOL_REGISTRY_CONFLICT",
                    message=(
                        f"tool {descriptor.key} is already registered with a different "
                        "ABI; a version is immutable"
                    ),
                    recommended_action="publish the change under a new tool version",
                    details={"toolId": descriptor.tool_id, "version": descriptor.version},
                )
            return
        self._by_key[descriptor.key] = descriptor
        versions = self._versions.setdefault(descriptor.tool_id, [])
        versions.append(descriptor.version)
        versions.sort()

    def get(self, tool_id: str, version: str | None = None) -> ToolDescriptor:
        """Resolve a tool.  An unknown tool is denied, never guessed."""

        versions = self._versions.get(tool_id)
        if not versions:
            raise KernelError(
                code="TOOL_DENIED",
                message=f"tool {tool_id!r} is not registered",
                retryable=False,
                recommended_action=(
                    "register the tool descriptor; the runtime does not guess or "
                    "fuzzy-match tool identifiers"
                ),
                details={"toolId": tool_id},
            )
        if version is None:
            version = versions[-1]
        descriptor = self._by_key.get(f"{tool_id}@{version}")
        if descriptor is None:
            raise KernelError(
                code="TOOL_DENIED",
                message=f"tool {tool_id!r} has no version {version!r}",
                retryable=False,
                recommended_action="request a registered version",
                details={"toolId": tool_id, "requestedVersion": version,
                         "knownVersions": list(versions)},
            )
        return descriptor

    def tool_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._versions))

    def __len__(self) -> int:
        return len(self._by_key)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One proposed invocation.

    ``attempt_no`` is part of the call's identity: a retry of a non-idempotent
    tool is a *different* effect and must not collapse onto the first attempt's
    idempotency key.
    """

    tool_id: str
    arguments: Mapping[str, Any]
    run_id: str
    step_id: str
    attempt_no: int = 1
    tool_version: str | None = None

    def __post_init__(self) -> None:
        require_identifier(self.tool_id, "tool_id")
        require_mapping(self.arguments, "arguments")
        require_identifier(self.run_id, "run_id")
        require_identifier(self.step_id, "step_id")
        require_int(self.attempt_no, "attempt_no", minimum=1)
        if self.tool_version is not None:
            require_str(self.tool_version, "tool_version", max_length=64)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ToolCall:
        payload = require_mapping(payload, "tool_call")
        known = {"toolId", "arguments", "runId", "stepId", "attemptNo", "toolVersion"}
        reject_unknown_fields(payload, known, field_name="tool_call")
        for name in ("toolId", "arguments", "runId", "stepId"):
            if name not in payload:
                raise KernelError(
                    code="MISSING_REQUIRED_INPUT",
                    message=f"tool_call.{name} is required",
                    recommended_action=f"supply tool_call.{name}",
                )
        version = payload.get("toolVersion")
        return cls(
            tool_id=require_identifier(payload["toolId"], "tool_call.toolId"),
            arguments=require_mapping(payload["arguments"], "tool_call.arguments"),
            run_id=require_identifier(payload["runId"], "tool_call.runId"),
            step_id=require_identifier(payload["stepId"], "tool_call.stepId"),
            attempt_no=require_int(payload.get("attemptNo", 1), "tool_call.attemptNo",
                                   minimum=1),
            tool_version=None if version is None else require_str(version,
                                                                  "tool_call.toolVersion",
                                                                  max_length=64),
        )


class ToolState(StrEnum):
    """Lifecycle states, taken from ``contracts/schemas/tool-call.schema.json``.

    ``DENIED`` means the call never ran; ``FAILED`` means it ran and the verdict
    is negative; ``INTERRUPTED``/``TIMED_OUT`` mean no verdict was reached.
    Collapsing any pair of these is how a half-applied effect gets reported as
    a clean failure and retried.
    """

    PROPOSED = "PROPOSED"
    DENIED = "DENIED"
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"
    TIMED_OUT = "TIMED_OUT"


class ToolEventType(StrEnum):
    """Audit event kinds.  Every call emits exactly one terminal event."""

    REQUESTED = "REQUESTED"
    COMPLETED = "COMPLETED"
    DENIED = "DENIED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ToolEvent:
    """One audit record.

    The event carries the *digest* of the arguments, never their text.  Tool
    arguments are untrusted data; copying them into the audit trail would put
    attacker-controlled prose into every downstream reader of that trail, and
    would make the trail non-deterministic in size.
    """

    event_type: ToolEventType
    sequence: int
    tool_call_id: str
    tool_id: str
    tool_version: str
    state: ToolState
    idempotency_key: str
    arguments_digest: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "eventType": str(self.event_type),
            "sequence": self.sequence,
            "toolCallId": self.tool_call_id,
            "toolId": self.tool_id,
            "toolVersion": self.tool_version,
            "state": str(self.state),
            "idempotencyKey": self.idempotency_key,
            "argumentsDigest": self.arguments_digest,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A validated tool outcome plus the audit pair that proves how it got there."""

    tool_call_id: str
    tool_id: str
    tool_version: str
    state: ToolState
    output: Mapping[str, Any]
    idempotency_key: str
    arguments_digest: str
    events: tuple[ToolEvent, ...]
    side_effect: Mapping[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "toolCallId": self.tool_call_id,
            "toolId": self.tool_id,
            "toolVersion": self.tool_version,
            "state": str(self.state),
            "output": dict(self.output),
            "idempotencyKey": self.idempotency_key,
            "argumentsDigest": self.arguments_digest,
            "events": [event.to_payload() for event in self.events],
        }
        if self.side_effect is not None:
            payload["sideEffect"] = dict(self.side_effect)
        return payload

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


# --- authority handling ------------------------------------------------------

_SCOPE_SOURCES: Mapping[str, str] = {
    "path": "path_scopes",
    "net": "network_scopes",
    "secret": "secret_bindings",
    "tool": "allowed_tools",
}


def _safe_digest(value: Any) -> str:
    """Digest ``value``, degrading to a shape digest when it is not canonicalisable.

    An argument object containing a float cannot be hashed, but the call it
    belongs to still has to appear in the audit trail as a denied call.  The
    fallback is explicitly marked so it can never be mistaken for a real
    content address.
    """

    try:
        return digest(value)
    except KernelError:
        keys = sorted(str(key) for key in value) if isinstance(value, Mapping) else []
        return digest({"unrepresentable": True, "keys": keys})


def _authority_scopes(authority: Any, attribute: str) -> frozenset[str]:
    if not hasattr(authority, attribute):
        raise KernelError(
            code="TOOL_DENIED",
            message=f"execution authority does not declare {attribute!r}",
            recommended_action="supply a complete ExecutionAuthority; absence is a deny",
            details={"missingAttribute": attribute},
        )
    value = getattr(authority, attribute)
    if isinstance(value, Mapping):
        return frozenset(str(key) for key in value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(item) for item in value)
    raise KernelError(
        code="TOOL_DENIED",
        message=f"execution authority {attribute!r} is not a collection",
        recommended_action="declare the scope set as a sequence or mapping",
    )


def _decision_allows(decision: Any) -> bool | None:
    """Interpret whatever ``authority.authorize`` returned.

    ``None`` is returned for a shape the runtime does not understand, and the
    caller turns that into a deny.  Guessing that an unparseable verdict means
    "allow" is the exact failure this kernel exists to prevent.
    """

    if isinstance(decision, bool):
        return decision
    for attribute in ("allowed", "is_allowed"):
        if hasattr(decision, attribute):
            value = getattr(decision, attribute)
            if isinstance(value, bool):
                return value
    if isinstance(decision, Mapping):
        if isinstance(decision.get("allowed"), bool):
            return bool(decision["allowed"])
        verdict = decision.get("decision")
        if isinstance(verdict, str):
            return verdict.upper() == "ALLOW"
    verdict = getattr(decision, "decision", None)
    if isinstance(verdict, str):
        return verdict.upper() == "ALLOW"
    return None


class ToolRuntime:
    """Validates, authorises, invokes and re-validates.

    The order of operations is the security property: arguments are shape-checked
    before authority is consulted (so a malformed call cannot probe the authority
    surface), authority is consulted before the invoker is touched (so a denied
    call never reaches an executor), and the executor's answer is validated before
    it is believed (so a compromised tool cannot return a shape the caller trusts).
    """

    __slots__ = ("_registry", "_events", "_sequence")

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._events: list[ToolEvent] = []
        self._sequence = 0

    @property
    def events(self) -> tuple[ToolEvent, ...]:
        return tuple(self._events)

    def _emit(self, event_type: ToolEventType, *, tool_call_id: str, tool_id: str,
              tool_version: str, state: ToolState, idempotency_key: str,
              arguments_digest: str, detail: Mapping[str, Any]) -> ToolEvent:
        self._sequence += 1
        event = ToolEvent(
            event_type=event_type,
            sequence=self._sequence,
            tool_call_id=tool_call_id,
            tool_id=tool_id,
            tool_version=tool_version,
            state=state,
            idempotency_key=idempotency_key,
            arguments_digest=arguments_digest,
            detail=dict(detail),
        )
        self._events.append(event)
        return event

    def invoke(self, call: ToolCall, authority: Any, invoker: Any) -> ToolResult:
        """Run one tool call end to end, or raise a structured denial/failure."""

        environment_id = str(getattr(authority, "environment_id", "") or "")
        workspace_id = str(getattr(authority, "workspace_id", "") or "")
        arguments_digest = _safe_digest(call.arguments)
        version_hint = call.tool_version or "unresolved"
        call_id = compute_tool_call_id(call, environment_id=environment_id,
                                       workspace_id=workspace_id,
                                       arguments_digest=arguments_digest,
                                       tool_version=version_hint)

        try:
            descriptor = self._registry.get(call.tool_id, call.tool_version)
        except KernelError as exc:
            self._deny_pair(exc, call_id=call_id, tool_id=call.tool_id,
                            tool_version=version_hint, idempotency_key="",
                            arguments_digest=arguments_digest)
            raise self._with_events(exc) from None

        # Re-derive the identity now that the true version is known; the audit
        # trail must key on the ABI that actually ran, not on the caller's hint.
        call_id = compute_tool_call_id(call, environment_id=environment_id,
                                       workspace_id=workspace_id,
                                       arguments_digest=arguments_digest,
                                       tool_version=descriptor.version)
        idempotency_key = compute_idempotency_key(call, descriptor,
                                                  workspace_id=workspace_id,
                                                  arguments_digest=arguments_digest)

        # 1. Arguments first.  Nothing else has looked at them yet.
        try:
            descriptor.input_validator.validate(call.arguments)
        except KernelError as exc:
            self._deny_pair(exc, call_id=call_id, tool_id=descriptor.tool_id,
                            tool_version=descriptor.version,
                            idempotency_key=idempotency_key,
                            arguments_digest=arguments_digest)
            raise self._with_events(exc) from None

        self._emit(ToolEventType.REQUESTED, tool_call_id=call_id,
                   tool_id=descriptor.tool_id, tool_version=descriptor.version,
                   state=ToolState.PROPOSED, idempotency_key=idempotency_key,
                   arguments_digest=arguments_digest,
                   detail={"runId": call.run_id, "stepId": call.step_id,
                           "attemptNo": call.attempt_no,
                           "descriptorDigest": descriptor.digest,
                           "sideEffecting": descriptor.side_effecting})

        # 2. Authority.  Every check below reads declared fields only.
        try:
            self._check_authority(descriptor, authority)
        except KernelError as exc:
            self._emit(ToolEventType.DENIED, tool_call_id=call_id,
                       tool_id=descriptor.tool_id, tool_version=descriptor.version,
                       state=ToolState.DENIED, idempotency_key=idempotency_key,
                       arguments_digest=arguments_digest,
                       detail={"code": exc.code, "reason": exc.message})
            raise self._with_events(exc) from None

        fencing_token = getattr(authority, "fencing_token", None)
        if descriptor.side_effecting:
            if not isinstance(fencing_token, int) or isinstance(fencing_token, bool) \
                    or fencing_token < 1:
                exc = KernelError(
                    code="FENCING_REJECTED",
                    message=(
                        f"tool {descriptor.key} is side-effecting and requires a fencing "
                        "token; the authority presented none"
                    ),
                    retryable=False,
                    recommended_action="acquire a workspace lease and retry with its token",
                    details={"toolId": descriptor.tool_id},
                )
                self._emit(ToolEventType.DENIED, tool_call_id=call_id,
                           tool_id=descriptor.tool_id, tool_version=descriptor.version,
                           state=ToolState.DENIED, idempotency_key=idempotency_key,
                           arguments_digest=arguments_digest,
                           detail={"code": exc.code, "reason": exc.message})
                raise self._with_events(exc)

        # 3. Execute.
        try:
            raw = invoker.invoke(descriptor.key, call.arguments, authority=authority)
        except KernelError as exc:
            state = ToolState.FAILED
            if exc.code == "TOOL_TIMEOUT":
                state = ToolState.TIMED_OUT
            elif exc.interrupted:
                state = ToolState.INTERRUPTED
            elif exc.partial:
                state = ToolState.PARTIAL
            self._emit(ToolEventType.FAILED, tool_call_id=call_id,
                       tool_id=descriptor.tool_id, tool_version=descriptor.version,
                       state=state, idempotency_key=idempotency_key,
                       arguments_digest=arguments_digest,
                       detail={"code": exc.code, "reason": exc.message})
            raise self._with_events(exc) from None

        # 4. Believe nothing until the result validates.
        if not isinstance(raw, Mapping):
            exc = KernelError(
                code="SCHEMA_MISMATCH",
                message=(
                    f"tool {descriptor.key} returned {type(raw).__name__}, "
                    "expected an object"
                ),
                recommended_action="treat the tool as faulty; its result is not usable",
                details={"pointer": "", "keyword": "type"},
            )
            self._emit(ToolEventType.FAILED, tool_call_id=call_id,
                       tool_id=descriptor.tool_id, tool_version=descriptor.version,
                       state=ToolState.FAILED, idempotency_key=idempotency_key,
                       arguments_digest=arguments_digest,
                       detail={"code": exc.code, "reason": exc.message})
            raise self._with_events(exc)

        try:
            descriptor.output_validator.validate(raw)
        except KernelError as exc:
            self._emit(ToolEventType.FAILED, tool_call_id=call_id,
                       tool_id=descriptor.tool_id, tool_version=descriptor.version,
                       state=ToolState.FAILED, idempotency_key=idempotency_key,
                       arguments_digest=arguments_digest,
                       detail={"code": exc.code, "reason": exc.message,
                               "pointer": exc.details.get("pointer", "")})
            raise self._with_events(exc) from None

        side_effect: Mapping[str, Any] | None = None
        if descriptor.side_effecting:
            side_effect = {
                "toolId": descriptor.tool_id,
                "toolVersion": descriptor.version,
                "declaredEffects": list(descriptor.declared_effects),
                "idempotencyKey": idempotency_key,
                "idempotent": descriptor.idempotent,
                "fencingToken": fencing_token,
                "workspaceId": workspace_id,
            }

        completed = self._emit(
            ToolEventType.COMPLETED, tool_call_id=call_id, tool_id=descriptor.tool_id,
            tool_version=descriptor.version, state=ToolState.SUCCEEDED,
            idempotency_key=idempotency_key, arguments_digest=arguments_digest,
            detail={"outputDigest": digest(dict(raw))},
        )
        requested = next(
            event for event in reversed(self._events[:-1])
            if event.tool_call_id == call_id and event.event_type is ToolEventType.REQUESTED
        )
        return ToolResult(
            tool_call_id=call_id,
            tool_id=descriptor.tool_id,
            tool_version=descriptor.version,
            state=ToolState.SUCCEEDED,
            output=dict(raw),
            idempotency_key=idempotency_key,
            arguments_digest=arguments_digest,
            events=(requested, completed),
            side_effect=side_effect,
        )

    def _deny_pair(self, exc: KernelError, *, call_id: str, tool_id: str,
                   tool_version: str, idempotency_key: str,
                   arguments_digest: str) -> None:
        self._emit(ToolEventType.REQUESTED, tool_call_id=call_id, tool_id=tool_id,
                   tool_version=tool_version, state=ToolState.PROPOSED,
                   idempotency_key=idempotency_key, arguments_digest=arguments_digest,
                   detail={})
        self._emit(ToolEventType.DENIED, tool_call_id=call_id, tool_id=tool_id,
                   tool_version=tool_version, state=ToolState.DENIED,
                   idempotency_key=idempotency_key, arguments_digest=arguments_digest,
                   detail={"code": exc.code, "reason": exc.message,
                           "pointer": exc.details.get("pointer", "")})

    def _with_events(self, exc: KernelError) -> KernelError:
        """Attach this call's audit pair to the error so the caller can persist it."""

        details = dict(exc.details)
        details["events"] = [event.to_payload() for event in self._events[-2:]]
        return KernelError(
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            partial=exc.partial,
            interrupted=exc.interrupted,
            evidence_ids=exc.evidence_ids,
            recommended_action=exc.recommended_action,
            details=details,
        )

    def _check_authority(self, descriptor: ToolDescriptor, authority: Any) -> None:
        allowed = _authority_scopes(authority, "allowed_tools")
        if descriptor.tool_id not in allowed and descriptor.key not in allowed:
            raise KernelError(
                code="TOOL_DENIED",
                message=f"tool {descriptor.tool_id!r} is not in the authority's allowed tools",
                retryable=False,
                recommended_action="grant the tool in the permission profile, not in the prompt",
                details={"toolId": descriptor.tool_id},
            )
        for scope in descriptor.required_scopes:
            prefix, _, _ = scope.partition(":")
            attribute = _SCOPE_SOURCES.get(prefix)
            if attribute is None:
                raise KernelError(
                    code="AUTHORITY_SCOPE_MISMATCH",
                    message=(
                        f"tool {descriptor.tool_id!r} requires scope {scope!r} whose "
                        "prefix is not a known scope family"
                    ),
                    recommended_action="use a path:, net:, secret: or tool: scope",
                    details={"scope": scope},
                )
            if scope not in _authority_scopes(authority, attribute):
                raise KernelError(
                    code="AUTHORITY_SCOPE_MISMATCH",
                    message=(
                        f"tool {descriptor.tool_id!r} requires scope {scope!r}, which the "
                        "authority does not grant"
                    ),
                    retryable=False,
                    recommended_action="widen the permission profile deliberately, or pick "
                                       "a tool that fits the granted scopes",
                    details={"scope": scope, "toolId": descriptor.tool_id},
                )

        authorize = getattr(authority, "authorize", None)
        if callable(authorize):
            decision = authorize({
                "kind": "tool-call",
                "toolId": descriptor.tool_id,
                "toolVersion": descriptor.version,
                "sideEffecting": descriptor.side_effecting,
                "requiredScopes": list(descriptor.required_scopes),
            })
            verdict = _decision_allows(decision)
            if verdict is not True:
                raise KernelError(
                    code="TOOL_DENIED",
                    message=(
                        f"execution authority denied {descriptor.tool_id!r}"
                        if verdict is False
                        else f"execution authority returned an uninterpretable verdict for "
                             f"{descriptor.tool_id!r}; an unreadable verdict is a deny"
                    ),
                    retryable=False,
                    recommended_action="inspect the authority decision record",
                    details={"toolId": descriptor.tool_id},
                )


def compute_tool_call_id(call: ToolCall, *, environment_id: str, workspace_id: str,
                         arguments_digest: str, tool_version: str) -> str:
    """Deterministic identity of one invocation attempt.

    Two kernels replaying the same run must produce the same id, so nothing
    environmental (time, pid, uuid4) may enter it.
    """

    body = {
        "toolId": call.tool_id,
        "toolVersion": tool_version,
        "runId": call.run_id,
        "stepId": call.step_id,
        "attemptNo": call.attempt_no,
        "argumentsDigest": arguments_digest,
        "environmentId": environment_id,
        "workspaceId": workspace_id,
    }
    return "tc-" + digest(body).split(":", 1)[1][:32]


def compute_idempotency_key(call: ToolCall, descriptor: ToolDescriptor, *,
                            workspace_id: str, arguments_digest: str) -> str:
    """Key under which a duplicate delivery must collapse.

    For an idempotent tool the key deliberately omits ``stepId`` and
    ``attemptNo``: replaying the same arguments is the same effect, so a retry
    after a crash must hit the recorded outcome instead of doing the work twice.
    For a non-idempotent tool the attempt is part of the identity, because a
    second attempt genuinely is a second effect and must not be silently
    deduplicated into the first.
    """

    body: dict[str, Any] = {
        "toolId": call.tool_id,
        "toolVersion": descriptor.version,
        "argumentsDigest": arguments_digest,
        "workspaceId": workspace_id,
        "runId": call.run_id,
    }
    if not descriptor.idempotent:
        body["stepId"] = call.step_id
        body["attemptNo"] = call.attempt_no
    return "idem-" + digest(body).split(":", 1)[1][:32]


# --- registry entry point ----------------------------------------------------


class _AuthorityView:
    """Read-only adapter over a wire-form execution authority.

    The registry entry point receives JSON, not the live ``ExecutionAuthority``
    object.  This view exposes exactly the declared fields the runtime is
    allowed to read, so a payload carrying extra keys cannot influence any
    decision even if a future field name collides.
    """

    __slots__ = ("environment_id", "workspace_id", "fencing_token", "allowed_tools",
                 "path_scopes", "network_scopes", "secret_bindings",
                 "policy_snapshot_hash")

    def __init__(self, payload: Mapping[str, Any]) -> None:
        payload = require_mapping(payload, "execution_authority")
        known = {"environmentId", "workspaceId", "fencingToken", "allowedTools",
                 "pathScopes", "networkScopes", "secretBindings", "policySnapshotHash"}
        reject_unknown_fields(payload, known, field_name="execution_authority")
        self.environment_id = require_identifier(payload.get("environmentId", "env-unknown"),
                                                 "execution_authority.environmentId")
        self.workspace_id = require_identifier(payload.get("workspaceId", "ws-unknown"),
                                               "execution_authority.workspaceId")
        token = payload.get("fencingToken")
        self.fencing_token = (
            None if token is None
            else require_int(token, "execution_authority.fencingToken", minimum=1)
        )
        self.allowed_tools = require_str_seq(payload.get("allowedTools", ()),
                                             "execution_authority.allowedTools")
        self.path_scopes = require_str_seq(payload.get("pathScopes", ()),
                                           "execution_authority.pathScopes")
        self.network_scopes = require_str_seq(payload.get("networkScopes", ()),
                                              "execution_authority.networkScopes")
        self.secret_bindings = require_str_seq(payload.get("secretBindings", ()),
                                               "execution_authority.secretBindings")
        snapshot = payload.get("policySnapshotHash")
        self.policy_snapshot_hash = (
            None if snapshot is None
            else require_str(snapshot, "execution_authority.policySnapshotHash")
        )


class _StaticInvoker:
    """Replays a transport-supplied result.

    ``handle`` is a pure decision function: it must not spawn anything.  The
    caller that already executed the tool hands the raw result back in, and the
    runtime still validates it against the declared output schema — which is the
    whole point, because that is where a lying tool is caught.
    """

    __slots__ = ("_result",)

    def __init__(self, result: Any) -> None:
        self._result = result

    def invoke(self, descriptor_id: str, arguments: Mapping[str, Any], *,
               authority: Any) -> Any:
        return self._result


@register("typed-tool-runtime")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point for ``typed-tool-runtime``."""

    request = require_mapping(request, "request")
    known = {"tool_descriptor", "tool_call_request", "execution_authority",
             "policy_snapshot", "tool_output"}
    reject_unknown_fields(request, known, field_name="request")
    for name in ("tool_descriptor", "tool_call_request", "execution_authority"):
        if name not in request:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{name} is required",
                recommended_action=f"supply request.{name}",
            )

    raw_descriptors = request["tool_descriptor"]
    if isinstance(raw_descriptors, Mapping):
        raw_descriptors = [raw_descriptors]
    if not isinstance(raw_descriptors, Sequence) or isinstance(raw_descriptors, (str, bytes)):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="tool_descriptor must be an object or an array of objects",
            recommended_action="supply one or more tool descriptors",
        )
    registry = ToolRegistry(
        [ToolDescriptor.from_payload(item) for item in raw_descriptors]
    )

    call = ToolCall.from_payload(request["tool_call_request"])
    authority = _AuthorityView(request["execution_authority"])

    snapshot = request.get("policy_snapshot")
    if snapshot is not None:
        snapshot = require_mapping(snapshot, "policy_snapshot")
        declared = snapshot.get("hash")
        if declared is not None and authority.policy_snapshot_hash is not None \
                and declared != authority.policy_snapshot_hash:
            raise KernelError(
                code="STALE_POLICY_SNAPSHOT",
                message=(
                    "the policy snapshot presented with the call is not the one the "
                    "authority was minted against"
                ),
                retryable=False,
                recommended_action="re-mint the execution authority against the current "
                                   "policy snapshot",
                details={"authoritySnapshot": authority.policy_snapshot_hash},
            )

    runtime = ToolRuntime(registry)
    result = runtime.invoke(call, authority, _StaticInvoker(request.get("tool_output", {})))
    return {
        "tool_call_record": {
            "toolCallId": result.tool_call_id,
            "toolId": result.tool_id,
            "toolVersion": result.tool_version,
            "runId": call.run_id,
            "stepId": call.step_id,
            "attemptNo": call.attempt_no,
            "state": str(result.state),
            "idempotencyKey": result.idempotency_key,
            "argumentsDigest": result.arguments_digest,
            "argumentKeys": sorted(str(key) for key in call.arguments),
        },
        "typed_result": dict(result.output),
        "side_effect_record": dict(result.side_effect) if result.side_effect else None,
        "tool_events": [event.to_payload() for event in result.events],
        "digest": result.digest,
    }
