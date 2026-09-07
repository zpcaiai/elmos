---
name: python-packaging-dependency-and-native-extension-modernizer
description: Modernize setup.py, setup.cfg, requirements, dependency groups, build backends, wheels, sdists, C/Cython/Fortran/Rust extensions, system libraries, and NumPy ABI into controlled pyproject-based packaging. Use for Python packaging conversion, wheel availability, native ABI, or supply-chain work.
---

# Python Packaging, Dependency, and Native Extension Modernizer

## Produce a declarative package model

Extract name/version, `requires-python`, dependencies and groups, entry points, package data, build requirements, classifiers, license, URLs, and dynamic metadata without executing setup code. Generate PEP 517/621-compatible `pyproject.toml` using a customer-compatible backend; do not force one backend.

Separate runtime, development, test, docs, build, optional, GPU, and platform dependencies. Apply `SECURITY_ONLY`, `MINIMUM_COMPATIBLE`, `FRAMEWORK_ALIGNED`, `BALANCED`, or `LATEST_SUPPORTED` policy explicitly. Never upgrade everything by default.

Inventory C, Cython, pybind11, SWIG, Rust/maturin, Fortran/f2py, NumPy C API, OpenMP, BLAS/LAPACK, and CUDA. Build a wheel matrix across CPython, ABI, OS, architecture, glibc/musl, and CUDA. Block when source or a compatible trusted wheel is unavailable.

Fix compiler, linker, headers, libraries, build dependencies, flags, and environment for source builds. Require artifact hashes, index allowlists, isolated builds, SBOM, license evidence, and post-install import smoke capturing DLL/shared-object/ABI failures.

Accept only when the generated project is declarative, backend and manager remain replaceable, native extensions are separate work items, NumPy ABI breaks are detected, and every target platform has an evidenced wheel/build path.

