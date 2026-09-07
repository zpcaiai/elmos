from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path


class PackagingModernizationAdvisor:
    NATIVE_SUFFIXES = {".so", ".pyd", ".dylib", ".dll", ".c", ".cc", ".cpp", ".pyx", ".rs", ".f", ".f90"}
    BACKENDS = ("setuptools", "hatchling", "flit", "poetry-core", "maturin", "scikit-build-core")

    def assess(
        self,
        root: Path,
        *,
        target_python: str = "3.14",
        target_numpy_major: int = 2,
        cuda: str | None = None,
    ) -> dict[str, object]:
        files = [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]
        source = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in files
            if path.suffix in ({".py", ".toml", ".cfg", ".txt"} | self.NATIVE_SUFFIXES)
            and path.stat().st_size < 2_000_000
        )
        findings: set[str] = set()
        native = [path.relative_to(root).as_posix() for path in files if path.suffix.lower() in self.NATIVE_SUFFIXES]
        if (root / "setup.py").exists():
            findings.add("LEGACY_SETUP_EXECUTION")
        if native:
            findings.add("NATIVE_EXTENSION_REBUILD")
        uses_numpy_c_api = bool(re.search(r"(?:numpy/arrayobject\.h|NPY_|PyArray_|numpy\.get_include)", source))
        if uses_numpy_c_api and target_numpy_major >= 2:
            findings.add("NUMPY_ABI_BREAK")
        wheel_files = [path for path in files if path.suffix == ".whl"]
        if native and not wheel_files:
            findings.add("NO_TARGET_WHEEL")
        if re.search(r"git\+[^\s]+(?:@(?:main|master|develop))?(?:\s|$)", source):
            findings.add("UNPINNED_GIT_DEPENDENCY")
        backend = self._backend(source)
        if backend is None:
            findings.add("BUILD_BACKEND_UNRESOLVED")
        wheel_matrix = [
            {
                "python": target_python,
                "abi": f"cp{target_python.replace('.', '')}",
                "os": os_name,
                "architecture": architecture,
                "libc": libc,
                "cuda": cuda or "CPU",
                "status": "SOURCE_BUILD_REQUIRED" if native and not wheel_files else "CANDIDATE",
            }
            for os_name, architecture, libc in (
                ("LINUX", "x86_64", "glibc"),
                ("LINUX", "arm64", "glibc"),
                ("WINDOWS", "x64", "msvc"),
                ("MACOS", "arm64", "darwin"),
            )
        ]
        return {
            "target": {
                "format": "PYPROJECT_PEP517_PEP621",
                "backend": backend or "CUSTOMER_APPROVAL_REQUIRED",
                "manager": "REPLACEABLE_ADAPTER",
            },
            "nativeExtensions": native,
            "numpyCApiDetected": uses_numpy_c_api,
            "wheelMatrix": wheel_matrix,
            "artifacts": [
                {
                    "path": path.relative_to(root).as_posix(),
                    "sha256": sha256(path.read_bytes()).hexdigest(),
                }
                for path in wheel_files
            ],
            "sourceBuildPolicy": {
                "sandbox": True,
                "network": "DENY_BY_DEFAULT",
                "secrets": "NONE",
                "fixedBuildDependenciesRequired": True,
                "sbomRequired": True,
            },
            "importSmoke": "REQUIRED_AFTER_INSTALL_IN_RUNNER",
            "findings": sorted(findings),
        }

    def _backend(self, source: str) -> str | None:
        for backend in self.BACKENDS:
            if backend in source:
                return backend
        return None
