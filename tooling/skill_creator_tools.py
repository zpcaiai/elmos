"""Repository-pinned subset of the Codex skill-creator validation contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MAX_SKILL_NAME_LENGTH = 64
ACRONYMS = {
    "GH",
    "MCP",
    "API",
    "CI",
    "CLI",
    "LLM",
    "PDF",
    "PR",
    "UI",
    "URL",
    "SQL",
}
BRANDS = {
    "openai": "OpenAI",
    "openapi": "OpenAPI",
    "github": "GitHub",
    "pagerduty": "PagerDuty",
    "datadog": "DataDog",
    "sqlite": "SQLite",
    "fastapi": "FastAPI",
}
SMALL_WORDS = {"and", "or", "to", "up", "with"}
ALLOWED_FRONTMATTER = {"name", "description", "license", "allowed-tools", "metadata"}


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def format_display_name(skill_name: str) -> str:
    words = [word for word in skill_name.split("-") if word]
    formatted: list[str] = []
    for index, word in enumerate(words):
        lower = word.lower()
        upper = word.upper()
        if upper in ACRONYMS:
            formatted.append(upper)
        elif lower in BRANDS:
            formatted.append(BRANDS[lower])
        elif index > 0 and lower in SMALL_WORDS:
            formatted.append(lower)
        else:
            formatted.append(word.capitalize())
    return " ".join(formatted)


def write_openai_yaml(
    skill_dir: str | Path,
    skill_name: str,
    interface_overrides: list[str] | None = None,
) -> Path:
    """Write the deterministic interface subset used by repository importers."""
    interface = {
        "display_name": format_display_name(skill_name),
        "short_description": "Run this ELMOS Skill with evidence controls",
        "default_prompt": (
            f"Use ${skill_name} to execute this ELMOS Skill with fail-closed evidence."
        ),
    }
    for override in interface_overrides or []:
        if "=" not in override:
            raise ValueError(f"Invalid interface override: {override}")
        key, value = override.split("=", 1)
        if key not in interface or not value.strip():
            raise ValueError(f"Invalid interface override: {override}")
        interface[key] = value
    target = Path(skill_dir) / "agents" / "openai.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "interface:",
                f"  display_name: {yaml_quote(interface['display_name'])}",
                f"  short_description: {yaml_quote(interface['short_description'])}",
                f"  default_prompt: {yaml_quote(interface['default_prompt'])}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return target


def validate_skill(skill_path: str | Path) -> tuple[bool, str]:
    """Validate the frontmatter contract used by Codex skill-creator."""
    try:
        import yaml
    except ModuleNotFoundError:
        return False, "PyYAML is required for Skill frontmatter validation"
    skill_md = Path(skill_path) / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match is None:
        return False, "Invalid frontmatter format"
    try:
        frontmatter: Any = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return False, f"Invalid YAML in frontmatter: {exc}"
    if not isinstance(frontmatter, dict):
        return False, "Frontmatter must be a YAML dictionary"
    unexpected = set(frontmatter) - ALLOWED_FRONTMATTER
    if unexpected:
        allowed = ", ".join(sorted(ALLOWED_FRONTMATTER))
        keys = ", ".join(sorted(unexpected))
        return False, (
            f"Unexpected key(s) in SKILL.md frontmatter: {keys}. "
            f"Allowed properties are: {allowed}"
        )
    if "name" not in frontmatter:
        return False, "Missing 'name' in frontmatter"
    if "description" not in frontmatter:
        return False, "Missing 'description' in frontmatter"
    name = frontmatter["name"]
    if not isinstance(name, str):
        return False, f"Name must be a string, got {type(name).__name__}"
    name = name.strip()
    if name:
        if re.fullmatch(r"[a-z0-9-]+", name) is None:
            return False, (
                f"Name '{name}' should be hyphen-case "
                "(lowercase letters, digits, and hyphens only)"
            )
        if name.startswith("-") or name.endswith("-") or "--" in name:
            return False, (
                f"Name '{name}' cannot start/end with hyphen "
                "or contain consecutive hyphens"
            )
        if len(name) > MAX_SKILL_NAME_LENGTH:
            return False, (
                f"Name is too long ({len(name)} characters). "
                f"Maximum is {MAX_SKILL_NAME_LENGTH} characters."
            )
    description = frontmatter["description"]
    if not isinstance(description, str):
        return False, (
            f"Description must be a string, got {type(description).__name__}"
        )
    description = description.strip()
    if description:
        if "<" in description or ">" in description:
            return False, "Description cannot contain angle brackets (< or >)"
        if len(description) > 1024:
            return False, (
                f"Description is too long ({len(description)} characters). "
                "Maximum is 1024 characters."
            )
    return True, "Skill is valid!"
