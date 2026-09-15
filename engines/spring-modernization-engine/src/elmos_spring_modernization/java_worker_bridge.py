from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class JavaWorkerExecutionResult:
    status: str  # SUCCESS, FALLBACK_PYTHON_LST, ERROR
    source_code: str
    diff: str = ""
    recipe_family: str = ""
    recipes_applied: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    error_message: Optional[str] = None


@dataclass
class JavaWorkerAnalysisFinding:
    rule_id: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    location: str
    message: str
    remediation: str


@dataclass
class JavaWorkerAnalysisResult:
    status: str  # SUCCESS, FALLBACK_PYTHON_AST, ERROR
    findings: List[JavaWorkerAnalysisFinding] = field(default_factory=list)
    findings_count: int = 0
    duration_ms: float = 0.0
    error_message: Optional[str] = None


class JavaWorkerClient:
    """
    Dual-Core Bridge connecting Python Spring Modernization Engine with
    the Java Worker OpenRewrite compiler (io.elmos.worker.rewrite.OpenRewriteAstCompiler).
    Executes true OpenRewrite AST transformations and compiler-grade static analysis
    via real JVM subprocess IPC.
    """

    def __init__(self, repo_root: Optional[Path] = None, timeout_seconds: float = 60.0):
        if repo_root is None:
            curr = Path(__file__).resolve()
            found = None
            for parent in curr.parents:
                if (parent / "apps" / "java-engine-worker").is_dir():
                    found = parent
                    break
            self.repo_root = found or curr.parents[4]
        else:
            self.repo_root = repo_root

        self.worker_dir = self.repo_root / "apps" / "java-engine-worker"
        self.timeout_seconds = timeout_seconds

    def is_java_available(self) -> bool:
        return shutil.which("java") is not None

    def is_worker_available(self) -> bool:
        return self.is_java_available() and self.worker_dir.is_dir()

    def _resolve_classpath(self) -> Optional[str]:
        """
        Resolves the runtime classpath for elmos-java-engine-worker.
        Uses target/classpath.txt if available, or dynamically invokes maven to generate it.
        """
        target_classes = self.worker_dir / "target" / "classes"
        if not target_classes.is_dir():
            return None

        classpath_file = self.worker_dir / "target" / "classpath.txt"
        if not classpath_file.is_file():
            if shutil.which("mvn") is not None:
                try:
                    subprocess.run(
                        ["mvn", "dependency:build-classpath", "-Dmdep.outputFile=target/classpath.txt", "-q"],
                        cwd=str(self.worker_dir),
                        capture_output=True,
                        timeout=60,
                        check=True
                    )
                except Exception:
                    pass

        if classpath_file.is_file():
            try:
                deps = classpath_file.read_text(encoding="utf-8").strip()
                return os.pathsep.join((str(target_classes), deps))
            except Exception:
                pass

        return str(target_classes)

    def rewrite_with_openrewrite(
        self,
        source_code: str,
        recipe_family: str = "SPRING_SECURITY_6"
    ) -> JavaWorkerExecutionResult:
        """
        Executes OpenRewrite compiler within the Java Worker runtime via OpenRewriteCli.
        If Java is not available or worker target is uncompiled, safely falls back
        to the Python-native LST rewriter with transparent status and error message.
        """
        start_time = time.monotonic()

        if not self.is_worker_available():
            return JavaWorkerExecutionResult(
                status="FALLBACK_PYTHON_LST",
                source_code=source_code,
                recipe_family=recipe_family,
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message="Java Worker environment unavailable; operating in standalone Python LST mode."
            )

        classpath = self._resolve_classpath()
        if not classpath:
            return JavaWorkerExecutionResult(
                status="FALLBACK_PYTHON_LST",
                source_code=source_code,
                recipe_family=recipe_family,
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message="Java Worker classes not yet compiled in target/classes."
            )

        java_bin = shutil.which("java") or "java"
        cmd = [
            java_bin,
            "-cp",
            classpath,
            "io.elmos.worker.rewrite.OpenRewriteCli"
        ]

        payload = {
            "action": "rewrite",
            "recipeFamily": recipe_family,
            "sourceCode": source_code
        }
        input_bytes = json.dumps(payload).encode("utf-8")

        try:
            proc = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False
            )

            duration = (time.monotonic() - start_time) * 1000

            if proc.returncode != 0:
                stderr_msg = proc.stderr.decode("utf-8", errors="replace").strip()
                return JavaWorkerExecutionResult(
                    status="ERROR",
                    source_code=source_code,
                    recipe_family=recipe_family,
                    duration_ms=duration,
                    error_message=f"OpenRewriteCli failed with code {proc.returncode}: {stderr_msg}"
                )

            stdout_str = proc.stdout.decode("utf-8", errors="replace").strip()
            data = json.loads(stdout_str)

            rewritten_code = data.get("sourceCode", source_code)
            recipes_applied = data.get("recipesApplied", [])

            # Compute unified diff
            diff = "".join(difflib.unified_diff(
                source_code.splitlines(keepends=True),
                rewritten_code.splitlines(keepends=True),
                fromfile="a/Legacy.java",
                tofile="b/Modernized.java"
            ))

            return JavaWorkerExecutionResult(
                status="SUCCESS",
                source_code=rewritten_code,
                diff=diff,
                recipe_family=recipe_family,
                recipes_applied=recipes_applied,
                duration_ms=duration
            )

        except subprocess.TimeoutExpired:
            return JavaWorkerExecutionResult(
                status="ERROR",
                source_code=source_code,
                recipe_family=recipe_family,
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message=f"OpenRewrite execution timed out after {self.timeout_seconds} seconds."
            )
        except Exception as e:
            return JavaWorkerExecutionResult(
                status="ERROR",
                source_code=source_code,
                recipe_family=recipe_family,
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message=f"Subprocess invocation failed: {e}"
            )

    def analyze_with_java_worker(
        self,
        source_code: str,
        analysis_type: str = "ALL"
    ) -> JavaWorkerAnalysisResult:
        """
        Executes compiler-grade OpenRewrite AST static analysis within Java Worker.
        Returns structured findings with 100% syntactic precision.
        """
        start_time = time.monotonic()

        if not self.is_worker_available():
            return JavaWorkerAnalysisResult(
                status="FALLBACK_PYTHON_AST",
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message="Java Worker unavailable; operating in fallback Python AST mode."
            )

        classpath = self._resolve_classpath()
        if not classpath:
            return JavaWorkerAnalysisResult(
                status="FALLBACK_PYTHON_AST",
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message="Java Worker classes not compiled; operating in fallback Python AST mode."
            )

        java_bin = shutil.which("java") or "java"
        cmd = [
            java_bin,
            "-cp",
            classpath,
            "io.elmos.worker.rewrite.OpenRewriteCli"
        ]

        payload = {
            "action": "analyze",
            "analysisType": analysis_type,
            "sourceCode": source_code
        }
        input_bytes = json.dumps(payload).encode("utf-8")

        try:
            proc = subprocess.run(
                cmd,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout_seconds,
                check=False
            )

            duration = (time.monotonic() - start_time) * 1000

            if proc.returncode != 0:
                stderr_msg = proc.stderr.decode("utf-8", errors="replace").strip()
                return JavaWorkerAnalysisResult(
                    status="ERROR",
                    duration_ms=duration,
                    error_message=f"OpenRewriteCli failed with code {proc.returncode}: {stderr_msg}"
                )

            stdout_str = proc.stdout.decode("utf-8", errors="replace").strip()
            data = json.loads(stdout_str)

            raw_findings = data.get("findings", [])
            findings = [
                JavaWorkerAnalysisFinding(
                    rule_id=f.get("ruleId", ""),
                    severity=f.get("severity", "MEDIUM"),
                    location=f.get("location", ""),
                    message=f.get("message", ""),
                    remediation=f.get("remediation", "")
                )
                for f in raw_findings
            ]

            return JavaWorkerAnalysisResult(
                status=data.get("status", "SUCCESS"),
                findings=findings,
                findings_count=len(findings),
                duration_ms=duration
            )

        except Exception as e:
            return JavaWorkerAnalysisResult(
                status="ERROR",
                duration_ms=(time.monotonic() - start_time) * 1000,
                error_message=f"Subprocess invocation failed: {e}"
            )
