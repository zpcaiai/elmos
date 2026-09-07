from __future__ import annotations

import re
from pathlib import Path


class DjangoModernizationAdvisor:
    def assess(
        self,
        root: Path,
        current_version: str | None,
        target_version: str | None,
        third_party_compatibility: dict[str, bool] | None = None,
    ) -> dict[str, object]:
        text = self._all_python(root)
        findings = []
        blockers: list[str] = []
        if re.search(r"\burl\s*\(", text):
            findings.append("DJANGO_URL_BREAKING")
        if "MIDDLEWARE_CLASSES" in text:
            findings.append("DJANGO_INCREMENTAL_UPGRADE_REQUIRED")
        if re.search(r"(?i)(secret_key|password)\s*=\s*['\"][^'\"]+", text):
            findings.append("DJANGO_SETTINGS_SECRET")
        third_party_compatibility = third_party_compatibility or {}
        unsupported_apps = sorted(name for name, supported in third_party_compatibility.items() if not supported)
        if unsupported_apps:
            findings.append("DJANGO_THIRD_PARTY_APP_BLOCKER")
            blockers.extend(f"DJANGO_PLUGIN_UNSUPPORTED:{name}" for name in unsupported_apps)
        stages = []
        if current_version and target_version:
            current_major = int(current_version.split(".")[0])
            target_major = int(target_version.split(".")[0])
            stages = [f"DJANGO_{major}.LATEST_PATCH" for major in range(current_major, target_major + 1)]
        return {
            "strategy": "INCREMENTAL_FEATURE_VERSIONS",
            "stages": stages,
            "deprecationGateEachStage": True,
            "wsgiToAsgi": "NOT_FORCED",
            "requiredValidation": ["SYSTEM_CHECK", "MIGRATIONS", "HTTP", "AUTH", "SESSION", "DATABASE", "STATIC"],
            "thirdPartyCompatibility": dict(sorted(third_party_compatibility.items())),
            "blockers": blockers,
            "findings": findings,
        }

    @staticmethod
    def _all_python(root: Path) -> str:
        return "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in root.rglob("*.py")
            if path.is_file() and not path.is_symlink()
        )


class FlaskModernizationAdvisor:
    def assess(self, root: Path, requires_asgi: bool = False) -> dict[str, object]:
        text = DjangoModernizationAdvisor._all_python(root)
        findings = []
        if re.search(r"(?:thread|executor|background).*current_app", text, re.IGNORECASE | re.DOTALL):
            findings.append("FLASK_CONTEXT_LIFETIME_RISK")
        if "Flask(__name__)" in text and "create_app" not in text:
            findings.append("FLASK_GLOBAL_APP_STATE")
        extensions = sorted(set(re.findall(r"(?m)^\s*from\s+(flask_[A-Za-z0-9_]+)\s+import", text)))
        context_symbols = sorted(
            name for name in ("current_app", "g", "request", "session") if re.search(rf"\b{name}\b", text)
        )
        strategy = "EVALUATE_ASGI_ADAPTER_OR_SERVICE_SPLIT" if requires_asgi else "KEEP_FLASK_WSGI"
        return {
            "strategy": strategy,
            "automaticFrameworkReplacement": False,
            "extensions": extensions,
            "contextSymbols": context_symbols,
            "requiredValidation": ["ROUTES", "CONTEXT", "SESSION", "JSON", "GRACEFUL_SHUTDOWN"],
            "findings": findings,
        }
