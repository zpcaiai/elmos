from __future__ import annotations
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict

@dataclass
class BeanDefinition:
    name: str
    class_name: str
    scope: str
    qualifiers: List[str]
    dependencies: List[str]
    init_method: str = ""
    destroy_method: str = ""

@dataclass
class SpringBeanGraph:
    beans: List[BeanDefinition]
    dependencies: Dict[str, List[str]]
    scopes: Dict[str, str]

@dataclass
class SecurityFilterChain:
    filters: List[str]
    matchers: List[str]
    authorization_rules: List[str]

@dataclass
class TransactionBoundary:
    method: str
    propagation: str
    isolation: str
    read_only: bool
    timeout: int

@dataclass
class SpringSemanticIR:
    bean_graph: SpringBeanGraph
    security_chains: List[SecurityFilterChain]
    transaction_boundaries: List[TransactionBoundary]
    endpoints: List[str]
    scheduled_tasks: List[str]

class SpringSemanticExtractor:
    """
    Industrial-grade semantic IR extractor for Spring repositories.
    Performs static AST/regex analysis over Java source trees to extract:
    - Spring Bean graphs and injection dependencies
    - SecurityFilterChain rules and custom filters
    - Transactional boundaries and propagation semantics
    - HTTP REST/MVC Endpoints and URI routing paths
    - Scheduled cron and delay background tasks
    """

    EXCLUDED_DIRS = {
        ".git", ".svn", ".hg", "target", "build", "node_modules", ".venv",
        "tmp", "temp", "Library", "System", "private", ".idea", ".vscode"
    }

    def _walk_java_files(self, project_root: str) -> Iterator[Path]:
        root = Path(project_root)
        if not root.exists():
            return
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in self.EXCLUDED_DIRS]
            for f in filenames:
                if f.endswith(".java"):
                    yield Path(dirpath) / f

    def extract_bean_graph(self, project_root: str) -> SpringBeanGraph:
        beans: List[BeanDefinition] = []
        dependencies: Dict[str, List[str]] = {}
        scopes: Dict[str, str] = {}

        for java_file in self._walk_java_files(project_root):
            try:
                content = java_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # Class-level bean detection
            class_match = re.search(r"(?:public\s+)?(?:class|interface|record)\s+([A-Za-z0-9_$]+)", content)
            if not class_match:
                continue
            class_name = class_match.group(1)

            # Check stereotype annotations: @Component, @Service, @Repository, @Controller, @RestController, @Configuration
            stereotype_match = re.search(
                r"@(?:Component|Service|Repository|Controller|RestController|Configuration)\b(?:\s*\(\s*(?:value\s*=\s*)?\"([^\"]+)\"\s*\))?",
                content
            )
            if stereotype_match:
                custom_name = stereotype_match.group(1)
                bean_name = custom_name if custom_name else (class_name[0].lower() + class_name[1:])

                # Scope extraction
                scope = "singleton"
                scope_match = re.search(r"@Scope\s*\(\s*(?:value\s*=\s*)?\"([^\"]+)\"\s*\)", content)
                if scope_match:
                    scope = scope_match.group(1)

                # Qualifiers
                qualifiers: List[str] = []
                for qm in re.finditer(r"@Qualifier\s*\(\s*\"([^\"]+)\"\s*\)", content):
                    qualifiers.append(qm.group(1))

                # Dependencies from @Autowired / @Resource / @Inject fields or constructors
                deps: List[str] = []
                # Field injections
                field_dep_matches = re.finditer(
                    r"@(?:Autowired|Resource|Inject)\b(?:\s*@Qualifier\(\"[^\"]+\"\))?\s*(?:private|protected|public)?\s+(?:final\s+)?([A-Za-z0-9_$]+(?:<[^>]+>)?)\s+([A-Za-z0-9_$]+)\s*;",
                    content
                )
                for fdm in field_dep_matches:
                    dep_name = fdm.group(2)
                    deps.append(dep_name)

                # Constructor injections (e.g. constructor parameters)
                ctor_matches = re.finditer(
                    rf"(?:public\s+)?{re.escape(class_name)}\s*\(([^)]+)\)",
                    content
                )
                for cm in ctor_matches:
                    params_str = cm.group(1).strip()
                    if params_str:
                        for param in params_str.split(","):
                            parts = param.strip().split()
                            if len(parts) >= 2:
                                param_name = parts[-1]
                                if param_name not in deps:
                                    deps.append(param_name)

                # Init / Destroy methods
                init_method = ""
                destroy_method = ""
                init_match = re.search(r"@PostConstruct\s+(?:public\s+)?void\s+([A-Za-z0-9_$]+)\s*\(", content)
                if init_match:
                    init_method = init_match.group(1)
                destroy_match = re.search(r"@PreDestroy\s+(?:public\s+)?void\s+([A-Za-z0-9_$]+)\s*\(", content)
                if destroy_match:
                    destroy_method = destroy_match.group(1)

                bean_def = BeanDefinition(
                    name=bean_name,
                    class_name=class_name,
                    scope=scope,
                    qualifiers=qualifiers,
                    dependencies=deps,
                    init_method=init_method,
                    destroy_method=destroy_method
                )
                beans.append(bean_def)
                dependencies[bean_name] = deps
                scopes[bean_name] = scope

            # Method-level @Bean detection in @Configuration classes
            if "@Configuration" in content:
                for bean_method in re.finditer(
                    r"@Bean\b(?:\s*\([^)]*\))?\s*(?:public\s+)?([A-Za-z0-9_$]+(?:<[^>]+>)?)\s+([A-Za-z0-9_$]+)\s*\(([^)]*)\)",
                    content
                ):
                    ret_type = bean_method.group(1)
                    method_bean_name = bean_method.group(2)
                    method_params = bean_method.group(3).strip()

                    method_deps: List[str] = []
                    if method_params:
                        for param in method_params.split(","):
                            parts = param.strip().split()
                            if len(parts) >= 2:
                                method_deps.append(parts[-1])

                    bean_def = BeanDefinition(
                        name=method_bean_name,
                        class_name=ret_type,
                        scope="singleton",
                        qualifiers=[],
                        dependencies=method_deps
                    )
                    beans.append(bean_def)
                    dependencies[method_bean_name] = method_deps
                    scopes[method_bean_name] = "singleton"

        return SpringBeanGraph(beans=beans, dependencies=dependencies, scopes=scopes)

    def extract_security_config(self, project_root: str) -> List[SecurityFilterChain]:
        chains: List[SecurityFilterChain] = []

        for java_file in self._walk_java_files(project_root):
            try:
                content = java_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if not ("WebSecurityConfigurerAdapter" in content or "SecurityFilterChain" in content or "@EnableWebSecurity" in content):
                continue

            filters: List[str] = []
            matchers: List[str] = []
            rules: List[str] = []

            # Extract filter chain registrations
            for add_filter in re.finditer(r"\.addFilter(?:Before|After|At)\s*\(\s*new\s+([A-Za-z0-9_$]+)", content):
                filters.append(add_filter.group(1))

            # Extract antMatchers or requestMatchers with rules
            pattern_regex = re.compile(
                r"\.(?:antMatchers|requestMatchers)\s*\(\s*([^)]+)\s*\)\s*\.([A-Za-z0-9_$]+(?:\([^)]*\))?)",
                re.MULTILINE
            )
            for pm in pattern_regex.finditer(content):
                raw_patterns = pm.group(1)
                rule = pm.group(2)
                for p in re.findall(r"\"([^\"]+)\"", raw_patterns):
                    matchers.append(p)
                    rules.append(f"{p} -> {rule}")

            if filters or matchers or rules or "SecurityFilterChain" in content:
                chains.append(SecurityFilterChain(
                    filters=filters,
                    matchers=matchers,
                    authorization_rules=rules
                ))

        return chains

    def extract_transaction_boundaries(self, project_root: str) -> List[TransactionBoundary]:
        boundaries: List[TransactionBoundary] = []

        for java_file in self._walk_java_files(project_root):
            try:
                content = java_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if "@Transactional" not in content:
                continue

            class_match = re.search(r"(?:public\s+)?class\s+([A-Za-z0-9_$]+)", content)
            class_name = class_match.group(1) if class_match else java_file.stem

            # Class-level default transaction policy
            class_tx_match = re.search(r"@Transactional\b(?:\s*\(([^)]*)\))?", content.split("class")[0] if "class" in content else "")
            default_propagation = "REQUIRED"
            default_isolation = "DEFAULT"
            default_read_only = False
            default_timeout = -1

            if class_tx_match and class_tx_match.group(1):
                params = class_tx_match.group(1)
                default_propagation = self._extract_param(params, "propagation", "REQUIRED")
                default_isolation = self._extract_param(params, "isolation", "DEFAULT")
                default_read_only = "readOnly=true" in params.replace(" ", "")
                timeout_match = re.search(r"timeout\s*=\s*(\d+)", params)
                if timeout_match:
                    default_timeout = int(timeout_match.group(1))

            # Method-level transactions
            method_regex = re.compile(
                r"@Transactional\b(?:\s*\(([^)]*)\))?\s*(?:public\s+)?(?:[A-Za-z0-9_$<>,\[\]\s]+)\s+([A-Za-z0-9_$]+)\s*\([^)]*\)",
                re.MULTILINE
            )
            for mm in method_regex.finditer(content):
                params = mm.group(1) or ""
                method_name = mm.group(2)
                full_method = f"{class_name}.{method_name}"

                propagation = self._extract_param(params, "propagation", default_propagation)
                isolation = self._extract_param(params, "isolation", default_isolation)
                read_only = ("readOnly=true" in params.replace(" ", "")) if "readOnly" in params else default_read_only
                timeout = default_timeout
                timeout_match = re.search(r"timeout\s*=\s*(\d+)", params)
                if timeout_match:
                    timeout = int(timeout_match.group(1))

                boundaries.append(TransactionBoundary(
                    method=full_method,
                    propagation=propagation,
                    isolation=isolation,
                    read_only=read_only,
                    timeout=timeout
                ))

        return boundaries

    def _extract_param(self, params_str: str, key: str, default: str) -> str:
        match = re.search(rf"{key}\s*=\s*(?:[A-Za-z0-9_.]+\.)?([A-Za-z0-9_]+)", params_str)
        return match.group(1) if match else default

    def extract_endpoints(self, project_root: str) -> List[str]:
        endpoints: List[str] = []

        for java_file in self._walk_java_files(project_root):
            try:
                content = java_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if not ("@Controller" in content or "@RestController" in content):
                continue

            # Class-level path
            class_path = ""
            class_req = re.search(
                r"@RequestMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?",
                content.split("class")[0] if "class" in content else ""
            )
            if class_req and class_req.group(1):
                class_path = class_req.group(1).rstrip("/")
                if not class_path.startswith("/"):
                    class_path = "/" + class_path

            # Method-level mappings
            mapping_patterns = [
                ("GET", r"@GetMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?"),
                ("POST", r"@PostMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?"),
                ("PUT", r"@PutMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?"),
                ("DELETE", r"@DeleteMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?"),
                ("PATCH", r"@PatchMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?"),
                ("REQUEST", r"@RequestMapping\b(?:\s*\(\s*(?:value\s*=\s*|path\s*=\s*)?\"([^\"]*)\"\s*\))?"),
            ]

            for verb, pattern in mapping_patterns:
                for match in re.finditer(pattern, content):
                    subpath = match.group(1) or ""
                    if subpath and not subpath.startswith("/"):
                        subpath = "/" + subpath
                    full_path = (class_path + subpath) if (class_path or subpath) else "/"
                    endpoint_signature = f"{verb} {full_path}"
                    if endpoint_signature not in endpoints:
                        endpoints.append(endpoint_signature)

        return sorted(endpoints)

    def extract_scheduled_tasks(self, project_root: str) -> List[str]:
        tasks: List[str] = []

        for java_file in self._walk_java_files(project_root):
            try:
                content = java_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            if "@Scheduled" not in content:
                continue

            class_match = re.search(r"(?:public\s+)?class\s+([A-Za-z0-9_$]+)", content)
            class_name = class_match.group(1) if class_match else java_file.stem

            for sm in re.finditer(
                r"@Scheduled\s*\(([^)]+)\)\s*(?:public\s+)?(?:void|Future<[^>]+>)\s+([A-Za-z0-9_$]+)\s*\(",
                content
            ):
                sched_params = sm.group(1)
                method_name = sm.group(2)
                tasks.append(f"{class_name}.{method_name} -> {sched_params.strip()}")

        return sorted(tasks)

    def extract_full_ir(self, project_root: str) -> SpringSemanticIR:
        return SpringSemanticIR(
            bean_graph=self.extract_bean_graph(project_root),
            security_chains=self.extract_security_config(project_root),
            transaction_boundaries=self.extract_transaction_boundaries(project_root),
            endpoints=self.extract_endpoints(project_root),
            scheduled_tasks=self.extract_scheduled_tasks(project_root)
        )
