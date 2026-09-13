"""Cross-language math, arithmetic, UUID, and crypto standard library shim across 11 enterprise languages."""

from __future__ import annotations

def math_abs(expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"Math.abs({expr})"
    elif l in ('csharp', 'cs'):
        return f"Math.Abs({expr})"
    elif l in ('python', 'py', 'php'):
        return f"abs({expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"Math.abs({expr})"
    elif l in ('go', 'golang'):
        return f"math.Abs(float64({expr}))"
    elif l in ('rust', 'rs'):
        return f"({expr}).abs()"
    elif l in ('cpp', 'c++'):
        return f"std::abs({expr})"
    elif l in ('swift', 'objc', 'objective-c'):
        return f"abs({expr})"
    return f"abs({expr})"

def math_min(a: str, b: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"Math.min({a}, {b})"
    elif l in ('csharp', 'cs'):
        return f"Math.Min({a}, {b})"
    elif l in ('python', 'py', 'php'):
        return f"min({a}, {b})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"Math.min({a}, {b})"
    elif l in ('go', 'golang'):
        return f"math.Min(float64({a}), float64({b}))"
    elif l in ('rust', 'rs'):
        return f"std::cmp::min({a}, {b})"
    elif l in ('cpp', 'c++'):
        return f"std::min({a}, {b})"
    elif l in ('swift', 'objc', 'objective-c'):
        return f"min({a}, {b})"
    return f"min({a}, {b})"

def math_max(a: str, b: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"Math.max({a}, {b})"
    elif l in ('csharp', 'cs'):
        return f"Math.Max({a}, {b})"
    elif l in ('python', 'py', 'php'):
        return f"max({a}, {b})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"Math.max({a}, {b})"
    elif l in ('go', 'golang'):
        return f"math.Max(float64({a}), float64({b}))"
    elif l in ('rust', 'rs'):
        return f"std::cmp::max({a}, {b})"
    elif l in ('cpp', 'c++'):
        return f"std::max({a}, {b})"
    elif l in ('swift', 'objc', 'objective-c'):
        return f"max({a}, {b})"
    return f"max({a}, {b})"

def math_sqrt(expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"Math.sqrt({expr})"
    elif l in ('csharp', 'cs'):
        return f"Math.Sqrt({expr})"
    elif l in ('python', 'py'):
        return f"math.sqrt({expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"Math.sqrt({expr})"
    elif l in ('go', 'golang'):
        return f"math.Sqrt(float64({expr}))"
    elif l in ('rust', 'rs'):
        return f"({expr} as f64).sqrt()"
    elif l == 'php':
        return f"sqrt({expr})"
    elif l in ('cpp', 'c++'):
        return f"std::sqrt({expr})"
    elif l == 'swift':
        return f"sqrt(Double({expr}))"
    return f"math.sqrt({expr})"

def uuid_v4(lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return "java.util.UUID.randomUUID().toString()"
    elif l in ('csharp', 'cs'):
        return "Guid.NewGuid().ToString()"
    elif l in ('python', 'py'):
        return "str(uuid.uuid4())"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return "crypto.randomUUID()"
    elif l in ('go', 'golang'):
        return "uuid.NewString()"
    elif l in ('rust', 'rs'):
        return "uuid::Uuid::new_v4().to_string()"
    elif l == 'php':
        return "bin2hex(random_bytes(16))"
    elif l in ('cpp', 'c++'):
        return "boost::uuids::to_string(boost::uuids::random_generator()())"
    elif l == 'swift':
        return "UUID().uuidString"
    elif l in ('objc', 'objective-c'):
        return "[[NSUUID UUID] UUIDString]"
    return "uuid.uuid4().hex"

def sha256_hex(expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance(\"SHA-256\").digest(({expr}).getBytes(java.nio.charset.StandardCharsets.UTF_8)))"
    elif l in ('csharp', 'cs'):
        return f"Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes({expr}))).ToLowerInvariant()"
    elif l in ('python', 'py'):
        return f"hashlib.sha256(({expr}).encode('utf-8')).hexdigest()"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"crypto.createHash('sha256').update({expr}).digest('hex')"
    elif l in ('go', 'golang'):
        return f"fmt.Sprintf(\"%x\", sha256.Sum256([]byte({expr})))"
    elif l in ('rust', 'rs'):
        return f"sha256::digest({expr})"
    elif l == 'php':
        return f"hash('sha256', {expr})"
    elif l == 'swift':
        return f"SHA256.hash(data: ({expr}).data(using: .utf8)!).compactMap {{ String(format: \"%02x\", $0) }}.joined()"
    return f"hashlib.sha256(({expr}).encode()).hexdigest()"

