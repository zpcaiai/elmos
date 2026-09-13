"""DateTime, Timestamps, and Clock standard library shim across 11 enterprise languages."""

from __future__ import annotations


def now_iso(lang: str) -> str:
    language = lang.lower().strip()
    if language in ("csharp", "cs"):
        return 'DateTime.UtcNow.ToString("o")'
    elif language in ("java", "kotlin"):
        return "java.time.Instant.now().toString()"
    elif language in ("python", "py"):
        return "datetime.now(timezone.utc).isoformat()"
    elif language in ("typescript", "ts", "javascript", "js"):
        return "new Date().toISOString()"
    elif language in ("go", "golang"):
        return "time.Now().UTC().Format(time.RFC3339)"
    elif language in ("rust", "rs"):
        return "chrono::Utc::now().to_rfc3339()"
    elif language == "php":
        return '(new DateTimeImmutable("now", new DateTimeZone("UTC")))->format(DateTimeInterface::ATOM)'
    elif language in ("cpp", "c++"):
        return 'std::format("{:%FT%TZ}", std::chrono::system_clock::now())'
    elif language == "swift":
        return "ISO8601DateFormatter().string(from: Date())"
    elif language in ("objc", "objective-c"):
        return "[[[NSISO8601DateFormatter alloc] init] stringFromDate:[NSDate date]]"
    return '""'


def epoch_millis(lang: str) -> str:
    language = lang.lower().strip()
    if language in ("csharp", "cs"):
        return "DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()"
    elif language in ("java", "kotlin"):
        return "System.currentTimeMillis()"
    elif language in ("python", "py"):
        return "int(time.time() * 1000)"
    elif language in ("typescript", "ts", "javascript", "js"):
        return "Date.now()"
    elif language in ("go", "golang"):
        return "time.Now().UnixMilli()"
    elif language in ("rust", "rs"):
        return "std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_millis() as i64"
    elif language == "php":
        return "round(microtime(true) * 1000)"
    elif language in ("cpp", "c++"):
        return "std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::system_clock::now().time_since_epoch()).count()"  # noqa: E501
    elif language == "swift":
        return "Int64(Date().timeIntervalSince1970 * 1000)"
    elif language in ("objc", "objective-c"):
        return "(long long)([[NSDate date] timeIntervalSince1970] * 1000)"
    return "0"


def sleep_millis(ms_expr: str, lang: str) -> str:
    language = lang.lower().strip()
    if language in ("csharp", "cs"):
        return f"Thread.Sleep({ms_expr})"
    elif language in ("java", "kotlin"):
        return f"Thread.sleep({ms_expr})"
    elif language in ("python", "py"):
        return f"time.sleep({ms_expr} / 1000.0)"
    elif language in ("typescript", "ts", "javascript", "js"):
        return f"await new Promise(resolve => setTimeout(resolve, {ms_expr}))"
    elif language in ("go", "golang"):
        return f"time.Sleep(time.Duration({ms_expr}) * time.Millisecond)"
    elif language in ("rust", "rs"):
        return f"std::thread::sleep(std::time::Duration::from_millis({ms_expr} as u64))"
    elif language == "php":
        return f"usleep({ms_expr} * 1000)"
    elif language in ("cpp", "c++"):
        return f"std::this_thread::sleep_for(std::chrono::milliseconds({ms_expr}))"
    elif language == "swift":
        return f"try await Task.sleep(nanoseconds: UInt64({ms_expr}) * 1_000_000)"
    return f"time.sleep({ms_expr})"
