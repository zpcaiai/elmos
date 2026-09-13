"""Certified REST + constructor DI + DTO framework subset."""

from __future__ import annotations

from copy import deepcopy

from elmos_polyglot_route.ast_compiler.ir import UniversalAnnotation, UniversalClass, UniversalModule
from elmos_polyglot_route.industrial.concurrency import normalize_language

FRAMEWORK_RUNTIME: dict[str, dict[str, str]] = {
    "java": {"controller": "@RestController", "get": "@GetMapping", "post": "@PostMapping", "di": "@Service"},
    "csharp": {"controller": "[ApiController]", "get": "[HttpGet]", "post": "[HttpPost]", "di": "[FromServices]"},
    "python": {"controller": "APIRouter", "get": "@router.get", "post": "@router.post", "di": "Depends"},
    "typescript": {"controller": "@Controller", "get": "@Get", "post": "@Post", "di": "@Injectable"},
    "go": {"controller": "http.HandleFunc", "get": "GET", "post": "POST", "di": "struct-inject"},
    "rust": {"controller": "axum::Router", "get": "get", "post": "post", "di": "State"},
    "kotlin": {"controller": "@RestController", "get": "@GetMapping", "post": "@PostMapping", "di": "@Service"},
    "php": {"controller": "Route::", "get": "Route::get", "post": "Route::post", "di": "container"},
    "cpp": {"controller": "httplib::Server", "get": "Get", "post": "Post", "di": "ctor"},
    "objc": {"controller": "NSURLSession", "get": "GET", "post": "POST", "di": "initWith"},
    "swift": {"controller": "Vapor.Route", "get": "GET", "post": "POST", "di": "init"},
    "react": {"controller": "express.Router", "get": "router.get", "post": "router.post", "di": "props"},
    "flutter": {"controller": "shelf.Router", "get": "get", "post": "post", "di": "ctor"},
    "vb6": {"controller": "WebClass", "get": "GET", "post": "POST", "di": "New"},
    "vcpp6": {"controller": "CHttpServer", "get": "GET", "post": "POST", "di": "ctor"},
}


def framework_runtime(language: str) -> dict[str, str]:
    key = normalize_language(language)
    if key not in FRAMEWORK_RUNTIME:
        raise ValueError(f"No industrial framework mapping for {language}")
    return FRAMEWORK_RUNTIME[key]


class FrameworkSubsetEngine:
    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = normalize_language(target_language)
        runtime = framework_runtime(target)
        out = deepcopy(module)
        out.metadata = dict(out.metadata)
        out.metadata["framework_runtime"] = runtime
        for klass in out.classes:
            cls._lower_class(klass, target, runtime)
        return out

    @classmethod
    def _lower_class(cls, klass: UniversalClass, target: str, runtime: dict[str, str]) -> None:
        if not klass.is_controller and not any(
            "controller" in a.name.lower() or "router" in a.name.lower() for a in klass.annotations
        ):
            if not any(m.http_method for m in klass.methods):
                return
            klass.is_controller = True
        klass.is_controller = True
        klass.base_route = klass.base_route or "/api/v1/inventory"
        klass.annotations = [
            UniversalAnnotation(name="IndustrialController", kwargs={"style": runtime["controller"]})
        ]
        for method in klass.methods:
            if not method.http_method:
                lowered = method.name.lower()
                if lowered.startswith("get"):
                    method.http_method = "GET"
                elif lowered.startswith("create") or lowered.startswith("post"):
                    method.http_method = "POST"
            if method.http_method == "GET":
                method.annotations.append(UniversalAnnotation(name="HttpGet", args=[method.http_path or "/{sku}"]))
            elif method.http_method == "POST":
                method.annotations.append(UniversalAnnotation(name="HttpPost", args=[method.http_path or ""]))
