from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid

@dataclass
class Breakpoint:
    file_path: str
    line: int
    condition: Optional[str] = None
    hit_count: int = 0
    enabled: bool = True

@dataclass
class Variable:
    name: str
    value: str
    type_name: str
    scope: str
    children: List['Variable'] = field(default_factory=list)

@dataclass
class CallFrame:
    function_name: str
    file_path: str
    line: int
    arguments: Dict[str, str] = field(default_factory=dict)
    locals: Dict[str, str] = field(default_factory=dict)

@dataclass
class DebugSession:
    session_id: str
    project_root: str
    language: str
    status: str
    breakpoints: List[Breakpoint] = field(default_factory=list)
    variables: List[Variable] = field(default_factory=list)
    call_stack: List[CallFrame] = field(default_factory=list)

@dataclass
class LogFilter:
    level: str
    pattern: str
    time_range: str
    source_file: Optional[str] = None

class DebugWorkbenchService:
    def __init__(self):
        self.sessions: Dict[str, DebugSession] = {}

    def create_session(self, project_root: str, language: str) -> DebugSession:
        sid = str(uuid.uuid4())
        session = DebugSession(session_id=sid, project_root=project_root, language=language, status="initialized")
        self.sessions[sid] = session
        return session

    def set_breakpoint(self, session_id: str, file_path: str, line: int, condition: Optional[str] = None) -> None:
        if session_id in self.sessions:
            self.sessions[session_id].breakpoints.append(Breakpoint(file_path=file_path, line=line, condition=condition))

    def get_variables(self, session_id: str, frame_index: int) -> List[Variable]:
        if session_id in self.sessions:
            return self.sessions[session_id].variables
        return []

    def get_call_stack(self, session_id: str) -> List[CallFrame]:
        if session_id in self.sessions:
            return self.sessions[session_id].call_stack
        return []

    def search_logs(self, session_id: str, filter: LogFilter) -> List[str]:
        return ["Log 1", "Log 2"]

    def generate_debug_mission(self, session_id: str, difficulty: str) -> Dict[str, Any]:
        return {"mission": "Fix the null pointer", "difficulty": difficulty}
