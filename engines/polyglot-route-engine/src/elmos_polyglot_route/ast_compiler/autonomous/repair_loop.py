"""Level 4 Autonomous Self-Healing and Repair Loop across 15 Languages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Any
from .compiler_diagnostics import CompilerDiagnosticParser, NativeCompilerDiagnostic


@dataclass
class RepairFix:
    iteration: int
    rule: str
    description: str
    diff_summary: str


@dataclass
class RepairResult:
    status: str  # clean, auto_repaired, blocked
    iterations: int
    final_code: str
    fixes: list[RepairFix] = field(default_factory=list)
    remaining_diagnostics: list[NativeCompilerDiagnostic] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return self.status in ("clean", "auto_repaired") and len(self.remaining_diagnostics) == 0

    @property
    def fixed(self) -> bool:
        return self.status in ("clean", "auto_repaired")

    @property
    def iterations_taken(self) -> int:
        return self.iterations

    @property
    def diagnostics(self) -> list[NativeCompilerDiagnostic]:
        return self.remaining_diagnostics


class AutonomousRepairLoop:
    """Iterative compiler-driven diagnostic and self-repair loop covering all 15 languages."""

    MAX_ITERATIONS = 4

    @classmethod
    def repair_code(cls, initial_code: str, target_lang: str, max_iterations: int = 4) -> RepairResult:
        return cls.run(initial_code, target_lang)

    @classmethod
    def run(cls, initial_code: str, target_lang: str) -> RepairResult:
        current_code = initial_code
        fixes: list[RepairFix] = []
        lang = target_lang.lower().strip()

        for i in range(1, cls.MAX_ITERATIONS + 1):
            ret_code, diags, raw_out = CompilerDiagnosticParser.check_syntax(current_code, lang)
            if ret_code == 0 and not any(d.severity == "error" for d in diags):
                # Clean compilation
                return RepairResult(
                    status="clean" if i == 1 else "auto_repaired",
                    iterations=i - 1,
                    final_code=current_code,
                    fixes=fixes,
                    remaining_diagnostics=[]
                )

            # Apply targeted heuristic repair based on target language and diagnostics
            new_code, applied_fix = cls._apply_repair_heuristics(current_code, lang, diags, i)
            if applied_fix:
                fixes.append(applied_fix)
                current_code = new_code
            else:
                # No rule matched to repair further, stop loop
                break

        # Final check
        ret_code, diags, raw_out = CompilerDiagnosticParser.check_syntax(current_code, lang)
        final_status = "auto_repaired" if (ret_code == 0 and not any(d.severity == "error" for d in diags)) else "blocked"
        return RepairResult(
            status=final_status,
            iterations=len(fixes),
            final_code=current_code,
            fixes=fixes,
            remaining_diagnostics=diags
        )

    @classmethod
    def _apply_repair_heuristics(
        cls, code: str, lang: str, diags: list[NativeCompilerDiagnostic], iteration: int
    ) -> tuple[str, Optional[RepairFix]]:
        new_code = code

        for d in diags:
            msg = d.message
            low_msg = msg.lower()

            # -------------------------------------------------------------
            # 1. C++ / C++20 Heuristics
            # -------------------------------------------------------------
            if lang in ("cpp", "c++"):
                if "#include <iostream>" not in new_code and ("cout" in low_msg or "ostream" in low_msg):
                    return "#include <iostream>\n" + new_code, RepairFix(
                        iteration, "cpp_missing_iostream", "Injected <iostream>", "+ #include <iostream>"
                    )
                if "#include <string>" not in new_code and ("string" in low_msg or "undeclared identifier 'std'" in low_msg):
                    return "#include <string>\n" + new_code, RepairFix(
                        iteration, "cpp_missing_string", "Injected <string>", "+ #include <string>"
                    )
                if "#include <algorithm>" not in new_code and any(k in low_msg for k in ("min", "max", "sort", "count")):
                    return "#include <algorithm>\n" + new_code, RepairFix(
                        iteration, "cpp_missing_algorithm", "Injected <algorithm>", "+ #include <algorithm>"
                    )
                if "#include <cmath>" not in new_code and any(k in low_msg for k in ("abs", "sqrt", "pow", "sin", "cos")):
                    return "#include <cmath>\n" + new_code, RepairFix(
                        iteration, "cpp_missing_cmath", "Injected <cmath>", "+ #include <cmath>"
                    )
                if "#include <vector>" not in new_code and "vector" in low_msg:
                    return "#include <vector>\n" + new_code, RepairFix(
                        iteration, "cpp_missing_vector", "Injected <vector>", "+ #include <vector>"
                    )
                if "#include <memory>" not in new_code and any(k in low_msg for k in ("unique_ptr", "shared_ptr", "make_unique", "make_shared")):
                    return "#include <memory>\n" + new_code, RepairFix(
                        iteration, "cpp_missing_memory", "Injected <memory>", "+ #include <memory>"
                    )
                if d.category == "type_mismatch" and "return {};" in new_code and "std::future" in low_msg:
                    fixed = new_code.replace("return {};", "return std::async(std::launch::deferred, [] { return {}; });")
                    return fixed, RepairFix(
                        iteration, "cpp_async_return_wrapping", "Wrapped return in std::async future", "return {} -> std::async"
                    )

            # -------------------------------------------------------------
            # 2. VC++6 MFC Heuristics
            # -------------------------------------------------------------
            elif lang in ("vcpp6", "mfc"):
                if "#include <afxwin.h>" not in new_code:
                    return "#include <afxwin.h>\n" + new_code, RepairFix(
                        iteration, "vcpp6_missing_afxwin", "Injected MFC afxwin.h header", "+ #include <afxwin.h>"
                    )

            # -------------------------------------------------------------
            # 3. Swift 6.0 Heuristics
            # -------------------------------------------------------------
            elif lang == "swift":
                if "import Foundation" not in new_code:
                    return "import Foundation\n" + new_code, RepairFix(
                        iteration, "swift_missing_foundation", "Injected import Foundation", "+ import Foundation"
                    )

            # -------------------------------------------------------------
            # 4. Objective-C ARC Heuristics
            # -------------------------------------------------------------
            elif lang in ("objc", "objective-c"):
                if "#import <Foundation/Foundation.h>" not in new_code:
                    return "#import <Foundation/Foundation.h>\n" + new_code, RepairFix(
                        iteration, "objc_missing_foundation", "Injected #import <Foundation/Foundation.h>", "+ #import <Foundation/Foundation.h>"
                    )

            # -------------------------------------------------------------
            # 5. Java Heuristics
            # -------------------------------------------------------------
            elif lang == "java":
                if any(k in msg or k in new_code for k in ("List", "Map", "Set", "ArrayList", "HashMap")) and "import java.util.*;" not in new_code:
                    if "package " in new_code:
                        fixed = re.sub(r'(package\s+[^;]+;\s*)', r'\1\nimport java.util.*;\n', new_code, count=1)
                    else:
                        fixed = "import java.util.*;\n" + new_code
                    return fixed, RepairFix(
                        iteration, "java_missing_util", "Injected import java.util.*", "+ import java.util.*;"
                    )
                if any(k in msg or k in new_code for k in ("CompletableFuture", "ExecutorService", "Callable")) and "import java.util.concurrent.*;" not in new_code:
                    if "package " in new_code:
                        fixed = re.sub(r'(package\s+[^;]+;\s*)', r'\1\nimport java.util.concurrent.*;\n', new_code, count=1)
                    else:
                        fixed = "import java.util.concurrent.*;\n" + new_code
                    return fixed, RepairFix(
                        iteration, "java_missing_concurrent", "Injected import java.util.concurrent.*", "+ import java.util.concurrent.*;"
                    )

            # -------------------------------------------------------------
            # 6. C# Heuristics
            # -------------------------------------------------------------
            elif lang in ("csharp", "cs"):
                if any(k in msg for k in ("List", "Dictionary", "HashSet", "IEnumerable")) and "using System.Collections.Generic;" not in new_code:
                    return "using System.Collections.Generic;\n" + new_code, RepairFix(
                        iteration, "csharp_missing_collections", "Injected using System.Collections.Generic;", "+ using System.Collections.Generic;"
                    )
                if "Task" in msg and "using System.Threading.Tasks;" not in new_code:
                    return "using System.Threading.Tasks;\n" + new_code, RepairFix(
                        iteration, "csharp_missing_tasks", "Injected using System.Threading.Tasks;", "+ using System.Threading.Tasks;"
                    )
                if "using System;" not in new_code:
                    return "using System;\n" + new_code, RepairFix(
                        iteration, "csharp_missing_system", "Injected using System;", "+ using System;"
                    )

            # -------------------------------------------------------------
            # 7. Go Heuristics
            # -------------------------------------------------------------
            elif lang in ("go", "golang"):
                if "fmt." in new_code and '"fmt"' not in new_code:
                    return new_code.replace("package enterprise", 'package enterprise\nimport "fmt"'), RepairFix(
                        iteration, "go_missing_fmt", "Injected import fmt", '+ import "fmt"'
                    )
                if "sync." in new_code and '"sync"' not in new_code:
                    return new_code.replace("package enterprise", 'package enterprise\nimport "sync"'), RepairFix(
                        iteration, "go_missing_sync", "Injected import sync", '+ import "sync"'
                    )
                unused_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s+declared and not used", msg)
                if unused_match:
                    var_name = unused_match.group(1)
                    # Add _ = var_name at end of function
                    lines = new_code.splitlines()
                    for idx in range(len(lines) - 1, -1, -1):
                        if "}" in lines[idx]:
                            lines.insert(idx, f"    _ = {var_name}")
                            break
                    return "\n".join(lines), RepairFix(
                        iteration, "go_suppress_unused", f"Suppressed unused variable {var_name}", f"+ _ = {var_name}"
                    )

            # -------------------------------------------------------------
            # 8. Rust Heuristics
            # -------------------------------------------------------------
            elif lang in ("rust", "rs"):
                if "Arc" in msg and "use std::sync::Arc;" not in new_code:
                    return "use std::sync::Arc;\n" + new_code, RepairFix(
                        iteration, "rust_missing_arc", "Injected use std::sync::Arc;", "+ use std::sync::Arc;"
                    )
                if "HashMap" in msg and "use std::collections::HashMap;" not in new_code:
                    return "use std::collections::HashMap;\n" + new_code, RepairFix(
                        iteration, "rust_missing_hashmap", "Injected use std::collections::HashMap;", "+ use std::collections::HashMap;"
                    )

            # -------------------------------------------------------------
            # 9. Python Heuristics
            # -------------------------------------------------------------
            elif lang == "python":
                if any(k in msg for k in ("List", "Dict", "Optional", "Any", "Tuple")) and "from typing import" not in new_code:
                    return "from typing import List, Dict, Optional, Any, Tuple\n" + new_code, RepairFix(
                        iteration, "python_missing_typing", "Injected from typing import ...", "+ from typing import ..."
                    )

            # -------------------------------------------------------------
            # 10. TypeScript / React Heuristics
            # -------------------------------------------------------------
            elif lang in ("typescript", "ts", "react"):
                if "React" in msg and "import React" not in new_code:
                    return "import React from 'react';\n" + new_code, RepairFix(
                        iteration, "react_missing_import", "Injected import React from 'react';", "+ import React from 'react';"
                    )

            # -------------------------------------------------------------
            # 11. Flutter (Dart) Heuristics
            # -------------------------------------------------------------
            elif lang in ("flutter", "dart"):
                if any(k in msg for k in ("Widget", "StatelessWidget", "StatefulWidget")) and "package:flutter/material.dart" not in new_code:
                    return "import 'package:flutter/material.dart';\n" + new_code, RepairFix(
                        iteration, "flutter_missing_material", "Injected flutter material import", "+ import 'package:flutter/material.dart';"
                    )

            # -------------------------------------------------------------
            # 12. PHP Heuristics
            # -------------------------------------------------------------
            elif lang == "php":
                if not new_code.strip().startswith("<?php"):
                    return "<?php\n" + new_code, RepairFix(
                        iteration, "php_missing_tag", "Injected <?php opening tag", "+ <?php"
                    )

            # -------------------------------------------------------------
            # 13. VB6 MS-VBLS Heuristics
            # -------------------------------------------------------------
            elif lang in ("vb6", "vb"):
                not_def_match = re.search(r"Variable Not Defined: '([A-Za-z0-9_]+)'", msg)
                if not_def_match:
                    var_name = not_def_match.group(1)
                    if "Option Explicit" in new_code:
                        fixed = new_code.replace("Option Explicit", f"Option Explicit\nDim {var_name} As String")
                    else:
                        fixed = f"Dim {var_name} As String\n" + new_code
                    return fixed, RepairFix(
                        iteration, "vb6_declare_variable", f"Declared variable {var_name} under Option Explicit", f"+ Dim {var_name} As String"
                    )

            # -------------------------------------------------------------
            # 14. Kotlin Heuristics
            # -------------------------------------------------------------
            elif lang in ("kotlin", "kt"):
                if "Unbalanced braces" in msg:
                    return new_code + "\n}", RepairFix(
                        iteration, "kotlin_close_brace", "Appended missing closing brace", "+ }"
                    )

        return code, None
