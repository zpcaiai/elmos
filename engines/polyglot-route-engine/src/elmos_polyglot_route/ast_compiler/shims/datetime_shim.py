"""DateTime standard library shim across 8 languages."""

from __future__ import annotations


def now_iso(lang: str) -> str:
    lang = lang.lower()
    if lang in ("csharp", "cs"):
        return "DateTime.UtcNow.ToString(\"o\")"
    elif lang == "java":
        return "Instant.now().toString()"
    elif lang in ("python", "py"):
        return "datetime.now(timezone.utc).isoformat()"
    elif lang in ("typescript", "ts"):
        return "new Date().toISOString()"
    elif lang in ("go", "golang"):
        return "time.Now().UTC().Format(time.RFC3339)"
    elif lang in ("rust", "rs"):
        return "chrono::Utc::now().to_rfc3339()"
    elif lang in ("kotlin", "kt"):
        return "Instant.now().toString()"
    elif lang == "php":
        return "(new DateTimeImmutable(\"now\", new DateTimeZone(\"UTC\")))->format(DateTimeInterface::ATOM)"
    return "\"\""
