"""Cross-Language Ownership, Borrowing, and Lifetime Region Model.

Models Rust affine types / borrow checking, C++ smart pointer RAII semantics,
Swift ARC reference graphs, and GC managed references.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .base import (
    AssignStmt,
    IdentifierExpr,
    MethodCallExpr,
    ReturnStmt,
    UniversalExpr,
    UniversalMethod,
    UniversalStmt,
    UniversalType,
    VarDeclStmt,
)


class OwnershipKind(str, Enum):
    OWNED = "owned"             # Unique owner (Rust value, C++ unique_ptr)
    SHARED_REF = "shared_ref"   # Immutable borrow (&T, const T&)
    MUT_REF = "mut_ref"         # Mutable borrow (&mut T, T&)
    ARC_MANAGED = "arc_managed" # Atomic ref count (Arc<T>, std::shared_ptr)
    GC_MANAGED = "gc_managed"   # Tracing GC pointer (Java, C#, Go, Python, TS)
    RAW_PTR = "raw_ptr"         # Unmanaged pointer (*mut T, *const T)


@dataclass
class LifetimeRegion:
    region_id: str
    outlives: set[str] = field(default_factory=set)  # regions that this region outlives (rho_self >= rho_other)
    is_static: bool = False

    def can_outlive(self, other_id: str) -> bool:
        if self.is_static:
            return True
        if self.region_id == other_id:
            return True
        return other_id in self.outlives


@dataclass
class BorrowState:
    var_name: str
    ownership_kind: OwnershipKind
    is_moved: bool = False
    moved_at: Optional[str] = None
    active_shared_borrows: int = 0
    active_mut_borrow: bool = False


@dataclass
class OwnershipViolation:
    violation_type: str  # USE_AFTER_MOVE, ALIASING_CONFLICT, MULTIPLE_MUT_BORROW, OUTLIVES_VIOLATION
    var_name: str
    message: str
    location: str


class OwnershipAnalyzer:
    """Simulates borrow checking and affine type moves across statements."""

    def __init__(self, is_rust_mode: bool = True) -> None:
        self.is_rust_mode = is_rust_mode
        self.variables: dict[str, BorrowState] = {}
        self.regions: dict[str, LifetimeRegion] = {
            "'static": LifetimeRegion(region_id="'static", is_static=True)
        }
        self.violations: list[OwnershipViolation] = []

    def declare_variable(self, name: str, kind: OwnershipKind = OwnershipKind.OWNED) -> None:
        self.variables[name] = BorrowState(var_name=name, ownership_kind=kind)

    def record_move(self, var_name: str, location: str = "") -> None:
        """Records moving ownership of a variable."""
        if var_name not in self.variables:
            return
        state = self.variables[var_name]
        if state.is_moved:
            self.violations.append(OwnershipViolation(
                violation_type="USE_AFTER_MOVE",
                var_name=var_name,
                message=f"Variable '{var_name}' used or moved after it was already moved at {state.moved_at}",
                location=location
            ))
            return

        if state.active_shared_borrows > 0 or state.active_mut_borrow:
            self.violations.append(OwnershipViolation(
                violation_type="ALIASING_CONFLICT",
                var_name=var_name,
                message=f"Cannot move out of '{var_name}' while it is borrowed",
                location=location
            ))
            return

        if state.ownership_kind == OwnershipKind.OWNED:
            state.is_moved = True
            state.moved_at = location

    def record_shared_borrow(self, var_name: str, location: str = "") -> None:
        """Records acquiring an immutable shared borrow &T."""
        if var_name not in self.variables:
            return
        state = self.variables[var_name]
        if state.is_moved:
            self.violations.append(OwnershipViolation(
                violation_type="USE_AFTER_MOVE",
                var_name=var_name,
                message=f"Cannot borrow '{var_name}' because it was previously moved at {state.moved_at}",
                location=location
            ))
            return

        if state.active_mut_borrow:
            self.violations.append(OwnershipViolation(
                violation_type="ALIASING_CONFLICT",
                var_name=var_name,
                message=f"Cannot borrow '{var_name}' as immutable because it is already borrowed as mutable",
                location=location
            ))
            return

        state.active_shared_borrows += 1

    def record_mutable_borrow(self, var_name: str, location: str = "") -> None:
        """Records acquiring an exclusive mutable borrow &mut T."""
        if var_name not in self.variables:
            return
        state = self.variables[var_name]
        if state.is_moved:
            self.violations.append(OwnershipViolation(
                violation_type="USE_AFTER_MOVE",
                var_name=var_name,
                message=f"Cannot borrow '{var_name}' as mutable because it was previously moved at {state.moved_at}",
                location=location
            ))
            return

        if state.active_shared_borrows > 0:
            self.violations.append(OwnershipViolation(
                violation_type="ALIASING_CONFLICT",
                var_name=var_name,
                message=f"Cannot borrow '{var_name}' as mutable because it is also borrowed as immutable ({state.active_shared_borrows} active borrows)",
                location=location
            ))
            return

        if state.active_mut_borrow:
            self.violations.append(OwnershipViolation(
                violation_type="MULTIPLE_MUT_BORROW",
                var_name=var_name,
                message=f"Cannot borrow '{var_name}' as mutable more than once at a time",
                location=location
            ))
            return

        state.active_mut_borrow = True

    def release_borrows(self, var_name: str) -> None:
        if var_name in self.variables:
            self.variables[var_name].active_shared_borrows = 0
            self.variables[var_name].active_mut_borrow = False

    def check_method(self, method: UniversalMethod) -> list[OwnershipViolation]:
        """Analyzes a method body for ownership and borrow violations."""
        for p in method.params:
            self.declare_variable(p.name, OwnershipKind.OWNED)

        for idx, stmt in enumerate(method.body):
            loc = f"{method.name}:stmt_{idx}"
            if isinstance(stmt, VarDeclStmt):
                self.declare_variable(stmt.name, OwnershipKind.OWNED)
                if isinstance(stmt.initial_value, IdentifierExpr):
                    # In Rust/C++ move semantics, assigning owned value moves it
                    self.record_move(stmt.initial_value.name, loc)

            elif isinstance(stmt, AssignStmt):
                if isinstance(stmt.value, IdentifierExpr):
                    self.record_move(stmt.value.name, loc)
                elif isinstance(stmt.target, IdentifierExpr):
                    # Re-assigning revives a moved variable
                    if stmt.target.name in self.variables:
                        self.variables[stmt.target.name].is_moved = False

        return self.violations
