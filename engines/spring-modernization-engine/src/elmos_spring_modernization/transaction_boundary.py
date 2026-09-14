from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

MAX_TX = 500

VALID_PROPAGATIONS = {
    "REQUIRED", "REQUIRES_NEW", "SUPPORTS", "NOT_SUPPORTED", "MANDATORY", "NEVER", "NESTED"
}

VALID_ISOLATIONS = {
    "DEFAULT", "READ_UNCOMMITTED", "READ_COMMITTED", "REPEATABLE_READ", "SERIALIZABLE"
}

@dataclass(frozen=True)
class TransactionPolicy:
    propagation: str
    isolation: str
    read_only: bool
    rollback_for: list[str]
    timeout: int = -1
    anti_patterns: list[str] = field(default_factory=list)

@dataclass(frozen=True)
class TransactionConfig:
    method_policies: dict[str, TransactionPolicy]
    propagation_chains: list[list[str]]
    anti_patterns: list[str] = field(default_factory=list)

class TransactionBoundaryExtractor:
    """
    Industrial-grade extractor for Spring transaction boundaries.
    Validates propagation/isolation semantics, analyzes call-graph propagation
    chains, and detects proxy bypass anti-patterns (e.g. self-invocation).
    """

    def extract(self, methods: list[dict]) -> TransactionConfig:
        if len(methods) > MAX_TX:
            raise ValueError(f"Too many methods. Max allowed is {MAX_TX}")

        policies: dict[str, TransactionPolicy] = {}
        calls_map: dict[str, list[str]] = {}
        class_map: dict[str, str] = {}
        global_anti_patterns: list[str] = []

        for m in methods:
            name = m.get("name")
            if not name:
                continue

            propagation = m.get("propagation", "REQUIRED").upper()
            if propagation not in VALID_PROPAGATIONS:
                propagation = "REQUIRED"

            isolation = m.get("isolation", "DEFAULT").upper()
            if isolation not in VALID_ISOLATIONS:
                isolation = "DEFAULT"

            read_only = bool(m.get("read_only", False))
            rollback_for = [str(e) for e in m.get("rollback_for", ["Exception"])]
            timeout = int(m.get("timeout", -1))
            calls = [str(c) for c in m.get("calls", [])]
            calls_map[name] = calls

            # Extract class name from name or explicit attribute
            explicit_class = m.get("class_name")
            if explicit_class:
                class_map[name] = explicit_class
            elif "." in name:
                class_map[name] = name.rsplit(".", 1)[0]
            else:
                class_map[name] = ""

            method_anti_patterns: list[str] = []

            # Check for suspicious rollback_for
            if rollback_for and "Exception" not in rollback_for and "RuntimeException" not in rollback_for and "Throwable" not in rollback_for:
                method_anti_patterns.append(
                    f"Non-standard rollback_for={rollback_for}: unhandled RuntimeExceptions may not trigger rollback."
                )

            policies[name] = TransactionPolicy(
                propagation=propagation,
                isolation=isolation,
                read_only=read_only,
                rollback_for=rollback_for,
                timeout=timeout,
                anti_patterns=method_anti_patterns
            )

        # Detect cross-method anti-patterns and propagation chains
        propagation_chains = self._compute_propagation_chains(policies, calls_map)
        detected_anti_patterns = self._detect_anti_patterns(policies, calls_map, class_map)
        global_anti_patterns.extend(detected_anti_patterns)

        return TransactionConfig(
            method_policies=policies,
            propagation_chains=propagation_chains,
            anti_patterns=global_anti_patterns
        )

    def _compute_propagation_chains(
        self,
        policies: dict[str, TransactionPolicy],
        calls_map: dict[str, list[str]]
    ) -> list[list[str]]:
        chains: list[list[str]] = []
        visited: set[str] = set()

        def trace(current: str, current_chain: list[str], path_set: set[str]) -> None:
            policy = policies.get(current)
            label = f"{current} ({policy.propagation if policy else 'NON_TX'})"
            current_chain.append(label)
            path_set.add(current)

            downstream = calls_map.get(current, [])
            if not downstream:
                if len(current_chain) > 1:
                    chains.append(list(current_chain))
            else:
                has_valid_next = False
                for callee in downstream:
                    if callee in path_set:
                        # Cycle detected in calls
                        chains.append(list(current_chain) + [f"{callee} (RECURSION)"])
                        has_valid_next = True
                    elif callee in policies or callee in calls_map:
                        trace(callee, current_chain, path_set)
                        has_valid_next = True
                if not has_valid_next and len(current_chain) > 1:
                    chains.append(list(current_chain))

            current_chain.pop()
            path_set.remove(current)

        # Start traces from methods with calls
        for root_method in policies:
            if calls_map.get(root_method):
                trace(root_method, [], set())

        return chains

    def _detect_anti_patterns(
        self,
        policies: dict[str, TransactionPolicy],
        calls_map: dict[str, list[str]],
        class_map: dict[str, str]
    ) -> list[str]:
        findings: list[str] = []

        for caller, callees in calls_map.items():
            caller_policy = policies.get(caller)
            caller_class = class_map.get(caller, "")

            for callee in callees:
                callee_policy = policies.get(callee)
                callee_class = class_map.get(callee, "")

                # 1. Spring AOP self-invocation proxy bypass
                if caller_class and caller_class == callee_class and caller != callee:
                    findings.append(
                        f"CRITICAL: Self-invocation proxy bypass detected from '{caller}' to '{callee}' in class '{caller_class}'. "
                        "Spring AOP proxies do not intercept internal method calls; transaction attributes on the callee will be ignored."
                    )

                if caller_policy and callee_policy:
                    # 2. NEVER called from within active transaction
                    if caller_policy.propagation in ("REQUIRED", "REQUIRES_NEW", "MANDATORY") and callee_policy.propagation == "NEVER":
                        findings.append(
                            f"ERROR: Transaction propagation conflict: '{caller}' ({caller_policy.propagation}) calls '{callee}' (NEVER), "
                            "which will trigger an IllegalTransactionStateException at runtime."
                        )

                    # 3. Read-only transaction calling mutable transaction
                    if caller_policy.read_only and not callee_policy.read_only and callee_policy.propagation not in ("REQUIRES_NEW", "NOT_SUPPORTED"):
                        findings.append(
                            f"WARNING: Read-only transaction leak: read-only method '{caller}' calls read-write method '{callee}' under shared transaction."
                        )

        return findings
