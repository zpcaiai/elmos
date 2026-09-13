"""Fail-closed detectors for leftover template / string-only industrial claims."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_TEMPLATE_SNIPPETS: tuple[str, ...] = (
    "EnterpriseAssetService",
    "GetAssetBySerialAsync",
    "AST-DEFAULT",
    'new Asset("AST-DEFAULT"',
    'return Asset(serial="AST-DEFAULT"',
    'status: "ACTIVE".to_string()',
    'resChan <- &Asset{Serial: serial, Status: "ACTIVE", Value: 100.0}',
)

FORBIDDEN_AUDIT_SNIPPETS: tuple[str, ...] = (
    'assert len(transpiled) > 100',
    'assert "Asset" in transpiled',
    '"bounded_certified_coverage_percent": 100.0',
)


def emission_is_template(source: str) -> list[str]:
    return [snippet for snippet in FORBIDDEN_TEMPLATE_SNIPPETS if snippet in source]


def scan_path_for_templates(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    hits = emission_is_template(text)
    if path.name == "run_polyglot_enterprise_audit.py":
        hits.extend(snippet for snippet in FORBIDDEN_AUDIT_SNIPPETS if snippet in text)
    return hits


def domain_tokens(language: str, domain: str, corpus_id: str = "") -> tuple[str, ...]:
    if corpus_id == "payment-clearing":
        table = {
            "go": ("go func", "sync.Mutex"),
            "java": ("EXECUTOR.submit", "synchronized"),
            "csharp": ("Task.Run", "lock"),
            "python": ("threading.Thread", "Lock"),
            "rust": ("std::thread::spawn", "Mutex"),
            "typescript": ("Promise",),
            "react": ("Promise",),
            "kotlin": ("thread", "synchronized"),
            "php": ("inline-worker",),
            "cpp": ("std::thread", "std::mutex"),
            "objc": ("dispatch_async",),
            "swift": ("Task",),
            "flutter": ("Future",),
            "vb6": ("inline-worker", "critical-section"),
            "vcpp6": ("AfxBeginThread", "CCriticalSection"),
        }
        return table.get(language, ("spawn",))
    if corpus_id == "order-pipeline":
        table = {
            "go": ("go func", "make(chan"),
            "java": ("EXECUTOR.submit", "BlockingQueue"),
            "csharp": ("Task.Run", "Channel"),
            "python": ("threading.Thread", "queue.Queue"),
            "rust": ("std::thread::spawn", "mpsc"),
            "typescript": ("AsyncQueue",),
            "react": ("AsyncQueue",),
            "kotlin": ("LinkedBlockingQueue",),
            "php": ("SplQueue",),
            "cpp": ("std::thread",),
            "objc": ("dispatch_async",),
            "swift": ("AsyncChannel",),
            "flutter": ("StreamController",),
            "vb6": ("Collection",),
            "vcpp6": ("AfxBeginThread",),
        }
        return table.get(language, ("channel",))
    if domain == "object-graph-lifecycle" or corpus_id == "asset-ledger":
        table = {
            "rust": ("move owned",),
            "python": ("unique move",),
            "go": ("// move",),
            "java": ("unique move",),
            "cpp": ("unique move",),
            "vcpp6": ("unique move",),
        }
        return table.get(language, ("move",))
    if domain == "system-io" or corpus_id == "file-settlement":
        table = {
            "python": ("write_text", "read_text"),
            "go": ("os.WriteFile", "os.ReadFile"),
            "java": ("Files.writeString", "Files.readString"),
            "csharp": ("File.WriteAllText", "File.ReadAllText"),
            "rust": ("std::fs::write", "read_to_string"),
            "php": ("file_put_contents", "file_get_contents"),
            "typescript": ("writeFileSync", "readFileSync"),
            "react": ("writeFileSync", "readFileSync"),
            "kotlin": ("Files.writeString", "Files.readString"),
            "vb6": ("Print #", "Input #"),
            "flutter": ("writeAsStringSync", "readAsStringSync"),
            "cpp": ("std::ofstream",),
            "vcpp6": ("std::ofstream",),
            "swift": ("write",),
            "objc": ("write",),
        }
        return table.get(language, ("write",))
    if domain == "complex-framework-and-ui" or corpus_id == "rest-inventory":
        table = {
            "java": ("@RestController", "@GetMapping"),
            "csharp": ("[ApiController]", "[HttpGet]"),
            "python": ("raise ValueError",),
            "kotlin": ("@RestController",),
            "php": ("Route::get",),
            "typescript": ("@Get()",),
            "react": ("@Get()",),
            "go": ("recover()",),
            "rust": ("Err(",),
            "vb6": ("Err.Raise",),
        }
        return table.get(language, ("Get",))
    return ()


def missing_domain_tokens(source: str, language: str, domain: str, corpus_id: str = "") -> list[str]:
    required = domain_tokens(language, domain, corpus_id)
    return [token for token in required if token not in source]
