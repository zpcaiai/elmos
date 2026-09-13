"""Cross-language math, arithmetic, UUID, and crypto standard library shim across 11 enterprise languages."""

from __future__ import annotations


def math_abs(expr: str, lang: str) -> str:
    language = lang.lower().strip()
    if language in ("java", "kotlin"):
        return f"Math.abs({expr})"
    elif language in ("csharp", "cs"):
        return f"Math.Abs({expr})"
    elif language in ("python", "py", "php"):
        return f"abs({expr})"
    elif language in ("typescript", "ts", "javascript", "js"):
        return f"Math.abs({expr})"
    elif language in ("go", "golang"):
        return f"math.Abs(float64({expr}))"
    elif language in ("rust", "rs"):
        return f"({expr}).abs()"
    elif language in ("cpp", "c++"):
        return f"std::abs({expr})"
    elif language in ("swift", "objc", "objective-c"):
        return f"abs({expr})"
    return f"abs({expr})"


def math_min(a: str, b: str, lang: str) -> str:
    language = lang.lower().strip()
    if language in ("java", "kotlin"):
        return f"Math.min({a}, {b})"
    elif language in ("csharp", "cs"):
        return f"Math.Min({a}, {b})"
    elif language in ("python", "py", "php"):
        return f"min({a}, {b})"
    elif language in ("typescript", "ts", "javascript", "js"):
        return f"Math.min({a}, {b})"
    elif language in ("go", "golang"):
        return f"math.Min(float64({a}), float64({b}))"
    elif language in ("rust", "rs"):
        return f"std::cmp::min({a}, {b})"
    elif language in ("cpp", "c++"):
        return f"std::min({a}, {b})"
    elif language in ("swift", "objc", "objective-c"):
        return f"min({a}, {b})"
    return f"min({a}, {b})"


def math_max(a: str, b: str, lang: str) -> str:
    language = lang.lower().strip()
    if language in ("java", "kotlin"):
        return f"Math.max({a}, {b})"
    elif language in ("csharp", "cs"):
        return f"Math.Max({a}, {b})"
    elif language in ("python", "py", "php"):
        return f"max({a}, {b})"
    elif language in ("typescript", "ts", "javascript", "js"):
        return f"Math.max({a}, {b})"
    elif language in ("go", "golang"):
        return f"math.Max(float64({a}), float64({b}))"
    elif language in ("rust", "rs"):
        return f"std::cmp::max({a}, {b})"
    elif language in ("cpp", "c++"):
        return f"std::max({a}, {b})"
    elif language in ("swift", "objc", "objective-c"):
        return f"max({a}, {b})"
    return f"max({a}, {b})"


def math_sqrt(expr: str, lang: str) -> str:
    language = lang.lower().strip()
    if language in ("java", "kotlin"):
        return f"Math.sqrt({expr})"
    elif language in ("csharp", "cs"):
        return f"Math.Sqrt({expr})"
    elif language in ("python", "py"):
        return f"math.sqrt({expr})"
    elif language in ("typescript", "ts", "javascript", "js"):
        return f"Math.sqrt({expr})"
    elif language in ("go", "golang"):
        return f"math.Sqrt(float64({expr}))"
    elif language in ("rust", "rs"):
        return f"({expr} as f64).sqrt()"
    elif language == "php":
        return f"sqrt({expr})"
    elif language in ("cpp", "c++"):
        return f"std::sqrt({expr})"
    elif language == "swift":
        return f"sqrt(Double({expr}))"
    return f"math.sqrt({expr})"


def uuid_v4(lang: str) -> str:
    language = lang.lower().strip()
    if language in ("java", "kotlin"):
        return "java.util.UUID.randomUUID().toString()"
    elif language in ("csharp", "cs"):
        return "Guid.NewGuid().ToString()"
    elif language in ("python", "py"):
        return "str(uuid.uuid4())"
    elif language in ("typescript", "ts", "javascript", "js"):
        return "crypto.randomUUID()"
    elif language in ("go", "golang"):
        return "uuid.NewString()"
    elif language in ("rust", "rs"):
        return "uuid::Uuid::new_v4().to_string()"
    elif language == "php":
        return "bin2hex(random_bytes(16))"
    elif language in ("cpp", "c++"):
        return "boost::uuids::to_string(boost::uuids::random_generator()())"
    elif language == "swift":
        return "UUID().uuidString"
    elif language in ("objc", "objective-c"):
        return "[[NSUUID UUID] UUIDString]"
    return "uuid.uuid4().hex"


def sha256_hex(expr: str, lang: str) -> str:
    language = lang.lower().strip()
    if language in ("java", "kotlin"):
        return (
            "java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("
            f'"SHA-256").digest(({expr}).getBytes(java.nio.charset.StandardCharsets.UTF_8)))'
        )
    elif language in ("csharp", "cs"):
        return (
            "Convert.ToHexString(System.Security.Cryptography.SHA256.HashData("
            f"System.Text.Encoding.UTF8.GetBytes({expr}))).ToLowerInvariant()"
        )
    elif language in ("python", "py"):
        return f"hashlib.sha256(({expr}).encode('utf-8')).hexdigest()"
    elif language in ("typescript", "ts", "javascript", "js"):
        return f"crypto.createHash('sha256').update({expr}).digest('hex')"
    elif language in ("go", "golang"):
        return f'fmt.Sprintf("%x", sha256.Sum256([]byte({expr})))'
    elif language in ("rust", "rs"):
        return f"sha256::digest({expr})"
    elif language == "php":
        return f"hash('sha256', {expr})"
    elif language == "swift":
        return f'SHA256.hash(data: ({expr}).data(using: .utf8)!).compactMap {{ String(format: "%02x", $0) }}.joined()'
    return f"hashlib.sha256(({expr}).encode()).hexdigest()"
