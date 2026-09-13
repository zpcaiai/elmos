from __future__ import annotations
from dataclasses import dataclass, field

MAX_IDENTIFIERS = 1000

@dataclass(frozen=True)
class NameMapping:
    original_to_renamed: dict[str, str]
    conflicts: list[str]

class NameConflictResolver:
    KEYWORDS = {
        "python": {"class", "def", "return", "pass", "import", "type"},
        "go": {"type", "func", "return", "var", "const", "package"},
        "typescript": {"class", "interface", "type", "return", "const"},
        "c#": {"class", "public", "private", "return", "var", "type"}
    }

    def resolve(self, identifiers: set[str], target_language: str) -> NameMapping:
        if len(identifiers) > MAX_IDENTIFIERS:
            raise ValueError(f"Too many identifiers. Max allowed is {MAX_IDENTIFIERS}")
            
        target_lang_lower = "".join(c for c in target_language.lower().strip() if c.isalpha() or c == '#')
        keywords = self.KEYWORDS.get(target_lang_lower, set())
        
        original_to_renamed = {}
        conflicts = []
        
        for identifier in identifiers:
            sanitized = "".join(c for c in identifier if c.isalnum() or c == '_')
            if sanitized in keywords:
                conflicts.append(sanitized)
                original_to_renamed[sanitized] = f"{sanitized}_"
            else:
                original_to_renamed[sanitized] = sanitized
                
        return NameMapping(original_to_renamed=original_to_renamed, conflicts=conflicts)
