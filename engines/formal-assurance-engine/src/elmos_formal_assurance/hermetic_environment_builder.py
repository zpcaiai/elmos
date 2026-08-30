"""Pinned formal-toolchain environment plan generation.

Generated definitions are plans, not evidence that an image was built, a Nix
closure was realized, the tool digests were checked, networking was denied, or
the environment is reproducible/hermetic. Those outcomes require separately
captured native execution receipts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .canonical import digest_bytes, digest_value, validate_digest, validate_identifier


class EnvironmentPlanError(ValueError):
    """Raised when a toolchain plan is not exactly pinned."""


_REVISION = re.compile(r"^[0-9a-f]{40}$")
_PLATFORM = re.compile(r"^(?:linux|darwin)/(?:amd64|arm64)$")


@dataclass(frozen=True)
class ToolchainArtifact:
    name: str
    version: str
    executable_path: str
    sha256: str

    def __post_init__(self) -> None:
        validate_identifier(self.name, "toolchain.name")
        if not isinstance(self.version, str) or not self.version.strip():
            raise EnvironmentPlanError("toolchain.version is required")
        path = PurePosixPath(self.executable_path)
        if (
            not self.executable_path.startswith("/")
            or ".." in path.parts
            or self.executable_path.endswith("/")
        ):
            raise EnvironmentPlanError("toolchain.executable_path must be absolute and confined")
        validate_digest(self.sha256, "toolchain.sha256")


@dataclass(frozen=True)
class ToolchainManifest:
    target_platform: str
    base_image: str
    base_image_digest: str
    nixpkgs_revision: str
    nixpkgs_source_digest: str
    toolchains: tuple[ToolchainArtifact, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_platform, str) or not _PLATFORM.fullmatch(
            self.target_platform
        ):
            raise EnvironmentPlanError("target_platform must be linux/darwin amd64/arm64")
        if (
            not isinstance(self.base_image, str)
            or not self.base_image
            or any(character.isspace() for character in self.base_image)
            or "@" in self.base_image
        ):
            raise EnvironmentPlanError("base_image must be a registry reference without tag digest")
        validate_digest(self.base_image_digest, "base_image_digest")
        if not isinstance(self.nixpkgs_revision, str) or not _REVISION.fullmatch(
            self.nixpkgs_revision
        ):
            raise EnvironmentPlanError("nixpkgs_revision must be a full Git commit")
        validate_digest(self.nixpkgs_source_digest, "nixpkgs_source_digest")
        if not isinstance(self.toolchains, tuple) or not self.toolchains:
            raise EnvironmentPlanError("at least one toolchain artifact is required")
        if any(not isinstance(item, ToolchainArtifact) for item in self.toolchains):
            raise EnvironmentPlanError("toolchains must contain ToolchainArtifact values")
        names = [item.name for item in self.toolchains]
        if len(names) != len(set(names)):
            raise EnvironmentPlanError("toolchain names must be unique")

    @property
    def manifest_digest(self) -> str:
        return digest_value(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        value = {
            "format": "elmos-pinned-toolchain-manifest/v1",
            "targetPlatform": self.target_platform,
            "baseImage": self.base_image,
            "baseImageDigest": validate_digest(
                self.base_image_digest, "base_image_digest"
            ),
            "nixpkgsRevision": self.nixpkgs_revision,
            "nixpkgsSourceDigest": validate_digest(
                self.nixpkgs_source_digest, "nixpkgs_source_digest"
            ),
            "toolchains": [
                {
                    "name": item.name,
                    "version": item.version,
                    "executablePath": item.executable_path,
                    "sha256": validate_digest(item.sha256, "toolchain.sha256"),
                }
                for item in sorted(self.toolchains, key=lambda item: item.name)
            ],
        }
        if include_digest:
            value["manifestDigest"] = self.manifest_digest
        return value


class HermeticToolchainBuilder:
    """Generate locked environment definitions with conservative outcome state."""

    def __init__(self, manifest: ToolchainManifest) -> None:
        if not isinstance(manifest, ToolchainManifest):
            raise EnvironmentPlanError("a ToolchainManifest is required")
        self.manifest = manifest

    def get_manifest(self) -> ToolchainManifest:
        return self.manifest

    def generate_nix_flake(self) -> str:
        """Generate a commit-pinned flake plan; realization remains NOT_RUN."""
        revision = self.manifest.nixpkgs_revision
        digest = self.manifest.manifest_digest
        return f'''# Generated plan. Nix realization and digest checks are NOT_RUN.
{{
  description = "ELMOS pinned formal-toolchain verification plan";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/{revision}";
  outputs = {{ self, nixpkgs }}:
    let
      system = "{_nix_platform(self.manifest.target_platform)}";
      pkgs = nixpkgs.legacyPackages.${{system}};
    in {{
      devShells.${{system}}.default = pkgs.mkShellNoCC {{
        packages = [ ];
        ELMOS_TOOLCHAIN_MANIFEST_DIGEST = "{digest}";
      }};
    }};
}}
'''

    def generate_dockerfile(self) -> str:
        """Generate a digest-pinned, non-root and network-install-free image plan."""
        image_digest = validate_digest(
            self.manifest.base_image_digest, "base_image_digest"
        ).removeprefix("sha256:")
        return f'''# Generated plan. Image build/runtime verification is NOT_RUN.
FROM {self.manifest.base_image}@sha256:{image_digest}
USER 65532:65532
WORKDIR /workspace
ENV ELMOS_TOOLCHAIN_MANIFEST_DIGEST="{self.manifest.manifest_digest}"
LABEL dev.elmos.formal-assurance.plan="pinned-not-executed"
'''

    def generate_devcontainer_json(self) -> dict[str, Any]:
        """Generate a least-privilege devcontainer plan with an exact image digest."""
        image_digest = validate_digest(
            self.manifest.base_image_digest, "base_image_digest"
        ).removeprefix("sha256:")
        return {
            "name": "ELMOS Formal Assurance Pinned Plan",
            "image": f"{self.manifest.base_image}@sha256:{image_digest}",
            "remoteUser": "65532",
            "containerEnv": {
                "ELMOS_TOOLCHAIN_MANIFEST_DIGEST": self.manifest.manifest_digest,
                "ELMOS_ENVIRONMENT_CLAIM": "PLAN_NOT_EXECUTED",
            },
            "runArgs": [
                "--network=none",
                "--read-only",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
            ],
            "customizations": {},
        }


def export_hermetic_toolchain(
    format_type: str = "nix", *, manifest: ToolchainManifest | None = None
) -> dict[str, Any]:
    """Export an exact plan while keeping execution and certification NOT_RUN."""
    if manifest is None:
        raise EnvironmentPlanError("an exact ToolchainManifest is required")
    builder = HermeticToolchainBuilder(manifest)
    fmt = format_type.lower()
    if fmt == "nix":
        content = builder.generate_nix_flake()
        filename = "flake.nix"
    elif fmt in {"docker", "dockerfile"}:
        fmt = "dockerfile"
        content = builder.generate_dockerfile()
        filename = "Dockerfile.formal-toolchain-plan"
    elif fmt == "devcontainer":
        content = json.dumps(
            builder.generate_devcontainer_json(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        filename = ".devcontainer/devcontainer.json"
    else:
        raise EnvironmentPlanError("format_type must be nix, dockerfile or devcontainer")
    content_digest = digest_bytes(content.encode("utf-8"))
    return {
        "format": fmt,
        "filename": filename,
        "manifest": manifest.to_dict(),
        "content": content,
        "contentDigest": content_digest,
        "planStatus": "GENERATED",
        "nativeBuildStatus": "NOT_RUN",
        "nativeRuntimeStatus": "NOT_RUN",
        "toolDigestVerificationStatus": "NOT_RUN",
        "networkIsolationEvidenceStatus": "NOT_RUN",
        "hermeticityStatus": "NOT_VERIFIED",
        "reproducibilityStatus": "NOT_RUN",
        "slsaLevel": "NOT_ASSESSED",
        "externalEvidenceStatus": "NOT_RUN",
        "independentVerificationStatus": "NOT_RUN",
        "certificationStatus": "NOT_CERTIFIED",
        "requiredEvidence": [
            "digest-pinned base image pull receipt",
            "tool executable digest verification receipt",
            "default-deny network enforcement receipt",
            "read-only/rootless sandbox receipt",
            "independent rebuild comparison",
        ],
    }


def _nix_platform(value: str) -> str:
    mapping = {
        "linux/amd64": "x86_64-linux",
        "linux/arm64": "aarch64-linux",
        "darwin/amd64": "x86_64-darwin",
        "darwin/arm64": "aarch64-darwin",
    }
    try:
        return mapping[value]
    except KeyError as exc:
        raise EnvironmentPlanError("target_platform is not supported") from exc


def toolchain_manifest_from_mapping(value: Mapping[str, Any]) -> ToolchainManifest:
    """Strictly parse a JSON-like manifest; unknown fields fail closed."""
    if not isinstance(value, Mapping):
        raise EnvironmentPlanError("toolchain manifest must be an object")
    expected = {
        "targetPlatform",
        "baseImage",
        "baseImageDigest",
        "nixpkgsRevision",
        "nixpkgsSourceDigest",
        "toolchains",
    }
    if set(value) != expected:
        raise EnvironmentPlanError(
            "toolchain manifest fields are invalid: "
            + ", ".join(sorted(set(value) ^ expected))
        )
    raw_toolchains = value["toolchains"]
    if isinstance(raw_toolchains, (str, bytes)) or not isinstance(
        raw_toolchains, Sequence
    ):
        raise EnvironmentPlanError("toolchains must be an array")
    if len(raw_toolchains) > 128:
        raise EnvironmentPlanError("toolchains exceed the item bound")
    toolchains: list[ToolchainArtifact] = []
    for index, item in enumerate(raw_toolchains):
        if not isinstance(item, Mapping) or set(item) != {
            "name",
            "version",
            "executablePath",
            "sha256",
        }:
            raise EnvironmentPlanError(
                f"toolchains[{index}] fields are invalid"
            )
        toolchains.append(
            ToolchainArtifact(
                name=item["name"],
                version=item["version"],
                executable_path=item["executablePath"],
                sha256=item["sha256"],
            )
        )
    return ToolchainManifest(
        target_platform=value["targetPlatform"],
        base_image=value["baseImage"],
        base_image_digest=value["baseImageDigest"],
        nixpkgs_revision=value["nixpkgsRevision"],
        nixpkgs_source_digest=value["nixpkgsSourceDigest"],
        toolchains=tuple(toolchains),
    )


__all__ = [
    "EnvironmentPlanError",
    "HermeticToolchainBuilder",
    "ToolchainArtifact",
    "ToolchainManifest",
    "export_hermetic_toolchain",
    "toolchain_manifest_from_mapping",
]
