from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum

class AnnotationType(Enum):
    EXPLANATION = "EXPLANATION"
    WARNING = "WARNING"
    TODO = "TODO"
    ARCHITECTURE_DECISION = "ARCHITECTURE_DECISION"
    SECURITY_NOTE = "SECURITY_NOTE"
    PERFORMANCE_NOTE = "PERFORMANCE_NOTE"
    DEBT_MARKER = "DEBT_MARKER"

@dataclass
class SourceAnchor:
    file_path: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int

@dataclass
class Annotation:
    annotation_id: str
    anchor: SourceAnchor
    content: str
    annotation_type: AnnotationType
    author: str
    created_at: str
    tags: List[str] = field(default_factory=list)

class AnnotationStore:
    def __init__(self):
        self.annotations: Dict[str, Annotation] = {}

    def create(self, annotation: Annotation) -> None:
        self.annotations[annotation.annotation_id] = annotation

    def read(self, annotation_id: str) -> Optional[Annotation]:
        return self.annotations.get(annotation_id)

    def update(self, annotation: Annotation) -> None:
        self.annotations[annotation.annotation_id] = annotation

    def delete(self, annotation_id: str) -> None:
        if annotation_id in self.annotations:
            del self.annotations[annotation_id]

    def query(self, file_path: Optional[str] = None, type: Optional[AnnotationType] = None, tag: Optional[str] = None) -> List[Annotation]:
        res = list(self.annotations.values())
        if file_path:
            res = [a for a in res if a.anchor.file_path == file_path]
        if type:
            res = [a for a in res if a.annotation_type == type]
        if tag:
            res = [a for a in res if tag in a.tags]
        return res

class CodeHighlighter:
    def map_symbols(self, symbols: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"mapped": len(symbols)}
