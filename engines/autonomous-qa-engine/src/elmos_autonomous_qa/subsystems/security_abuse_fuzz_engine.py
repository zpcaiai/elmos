"""Industrial Security Abuse & OWASP Top 10 Fuzzing Mutation Engine.

Synthesizes active mutation payloads for SQL Injection, Cross-Site Scripting (XSS),
SSRF, OS Command Injection, and Path Traversal vulnerabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class SecurityVulnerabilityReport:
    vulnerable: bool
    attack_category: str
    payload: str
    evidence: str


class SecurityAbuseFuzzEngine:
    """Security fuzzing mutator and input vulnerability scanner."""

    OWASP_PAYLOADS: Dict[str, List[str]] = {
        "SQL_INJECTION": [
            "' OR '1'='1",
            "admin' --",
            "1; DROP TABLE users--",
            "' UNION SELECT null, username, password FROM users--",
            "1' AND SLEEP(5)--",
        ],
        "XSS": [
            "<script>alert(1)</script>",
            '"><img src=x onerror=alert(document.domain)>',
            "javascript:/*--></title></style></textarea></script></xmp><svg/onload='+/'/+/onmouseover=1/+/[*/[]/+alert(1)//'>",
            "<iframe src=javascript:alert(1)>",
        ],
        "SSRF": [
            "http://127.0.0.1:80/admin",
            "http://localhost:22",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/internal",
        ],
        "COMMAND_INJECTION": [
            "; cat /etc/passwd",
            "| whoami",
            "& ping -c 3 127.0.0.1 &",
            "`id`",
            "$(uname -a)",
        ],
        "PATH_TRAVERSAL": [
            "../../../../etc/passwd",
            "..\\..\\..\\..\\windows\\win.ini",
            "/var/www/../../etc/shadow",
            "....//....//....//etc/passwd",
        ],
    }

    @classmethod
    def get_payloads(cls, category: str) -> List[str]:
        if category not in cls.OWASP_PAYLOADS:
            raise ValueError(f"Unknown attack category: {category}")
        return list(cls.OWASP_PAYLOADS[category])

    @staticmethod
    def audit_input_sanitization(
        raw_input: str,
        sanitizer_fn: Callable[[str], str],
    ) -> List[SecurityVulnerabilityReport]:
        """Audits if dangerous payload sequences survive the sanitizer."""
        reports = []
        for cat, payloads in SecurityAbuseFuzzEngine.OWASP_PAYLOADS.items():
            for p in payloads:
                cleaned = sanitizer_fn(p)
                if cat == "SQL_INJECTION" and ("' OR" in cleaned or "UNION SELECT" in cleaned):
                    reports.append(SecurityVulnerabilityReport(True, cat, p, f"Unescaped SQL syntax survived: {cleaned}"))
                elif cat == "XSS" and ("<script>" in cleaned or "onerror=" in cleaned or "<svg" in cleaned):
                    reports.append(SecurityVulnerabilityReport(True, cat, p, f"Unescaped HTML tags survived: {cleaned}"))
                elif cat == "COMMAND_INJECTION" and (";" in cleaned or "|" in cleaned or "`" in cleaned):
                    reports.append(SecurityVulnerabilityReport(True, cat, p, f"Command separator survived: {cleaned}"))
                elif cat == "PATH_TRAVERSAL" and ("../" in cleaned or "..\\" in cleaned):
                    reports.append(SecurityVulnerabilityReport(True, cat, p, f"Relative traversal path survived: {cleaned}"))
        return reports
