"""Cross-language string manipulation standard library shim across 11 enterprise languages."""

from __future__ import annotations

def string_length(var_name: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{var_name}.length()"
    elif l in ('csharp', 'cs'):
        return f"{var_name}.Length"
    elif l in ('python', 'py', 'go', 'golang'):
        return f"len({var_name})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{var_name}.length"
    elif l in ('rust', 'rs'):
        return f"{var_name}.len()"
    elif l == 'php':
        return f"strlen({var_name})"
    elif l in ('cpp', 'c++'):
        return f"{var_name}.length()"
    elif l == 'swift':
        return f"{var_name}.count"
    elif l in ('objc', 'objective-c'):
        return f"[{var_name} length]"
    return f"len({var_name})"

def string_trim(var_name: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{var_name}.trim()"
    elif l in ('csharp', 'cs'):
        return f"{var_name}.Trim()"
    elif l in ('python', 'py'):
        return f"{var_name}.strip()"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{var_name}.trim()"
    elif l in ('go', 'golang'):
        return f"strings.TrimSpace({var_name})"
    elif l in ('rust', 'rs'):
        return f"{var_name}.trim().to_string()"
    elif l == 'php':
        return f"trim({var_name})"
    elif l == 'swift':
        return f'{var_name}.trimmingCharacters(in: .whitespacesAndNewlines)'
    elif l in ('objc', 'objective-c'):
        return f'[{var_name} stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]]'
    return f"{var_name}.trim()"

def string_contains(haystack: str, needle: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{haystack}.contains({needle})"
    elif l in ('csharp', 'cs'):
        return f"{haystack}.Contains({needle})"
    elif l in ('python', 'py'):
        return f"({needle} in {haystack})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{haystack}.includes({needle})"
    elif l in ('go', 'golang'):
        return f"strings.Contains({haystack}, {needle})"
    elif l in ('rust', 'rs'):
        return f"{haystack}.contains({needle})"
    elif l == 'php':
        return f"str_contains({haystack}, {needle})"
    elif l in ('cpp', 'c++'):
        return f"({haystack}.find({needle}) != std::string::npos)"
    elif l == 'swift':
        return f"{haystack}.contains({needle})"
    elif l in ('objc', 'objective-c'):
        return f"([{haystack} containsString:{needle}])"
    return f"{haystack}.contains({needle})"

def string_starts_with(haystack: str, prefix: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{haystack}.startsWith({prefix})"
    elif l in ('csharp', 'cs'):
        return f"{haystack}.StartsWith({prefix})"
    elif l in ('python', 'py'):
        return f"{haystack}.startswith({prefix})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{haystack}.startsWith({prefix})"
    elif l in ('go', 'golang'):
        return f"strings.HasPrefix({haystack}, {prefix})"
    elif l in ('rust', 'rs'):
        return f"{haystack}.starts_with({prefix})"
    elif l == 'php':
        return f"str_starts_with({haystack}, {prefix})"
    elif l in ('cpp', 'c++'):
        return f"{haystack}.rfind({prefix}, 0) == 0"
    elif l == 'swift':
        return f"{haystack}.hasPrefix({prefix})"
    elif l in ('objc', 'objective-c'):
        return f"[{haystack} hasPrefix:{prefix}]"
    return f"{haystack}.startswith({prefix})"

def string_ends_with(haystack: str, suffix: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{haystack}.endsWith({suffix})"
    elif l in ('csharp', 'cs'):
        return f"{haystack}.EndsWith({suffix})"
    elif l in ('python', 'py'):
        return f"{haystack}.endswith({suffix})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{haystack}.endsWith({suffix})"
    elif l in ('go', 'golang'):
        return f"strings.HasSuffix({haystack}, {suffix})"
    elif l in ('rust', 'rs'):
        return f"{haystack}.ends_with({suffix})"
    elif l == 'php':
        return f"str_ends_with({haystack}, {suffix})"
    elif l in ('cpp', 'c++'):
        return f"({haystack}.length() >= {suffix}.length() && {haystack}.compare({haystack}.length() - {suffix}.length(), {suffix}.length(), {suffix}) == 0)"
    elif l == 'swift':
        return f"{haystack}.hasSuffix({suffix})"
    elif l in ('objc', 'objective-c'):
        return f"[{haystack} hasSuffix:{suffix}]"
    return f"{haystack}.endswith({suffix})"

def string_replace(var_name: str, old_val: str, new_val: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{var_name}.replace({old_val}, {new_val})"
    elif l in ('csharp', 'cs'):
        return f"{var_name}.Replace({old_val}, {new_val})"
    elif l in ('python', 'py'):
        return f"{var_name}.replace({old_val}, {new_val})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{var_name}.replaceAll({old_val}, {new_val})"
    elif l in ('go', 'golang'):
        return f"strings.ReplaceAll({var_name}, {old_val}, {new_val})"
    elif l in ('rust', 'rs'):
        return f"{var_name}.replace({old_val}, {new_val})"
    elif l == 'php':
        return f"str_replace({old_val}, {new_val}, {var_name})"
    elif l == 'swift':
        return f"{var_name}.replacingOccurrences(of: {old_val}, with: {new_val})"
    elif l in ('objc', 'objective-c'):
        return f"[{var_name} stringByReplacingOccurrencesOfString:{old_val} withString:{new_val}]"
    return f"{var_name}.replace({old_val}, {new_val})"

def string_to_lower(var_name: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{var_name}.toLowerCase()"
    elif l in ('csharp', 'cs'):
        return f"{var_name}.ToLowerInvariant()"
    elif l in ('python', 'py'):
        return f"{var_name}.lower()"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{var_name}.toLowerCase()"
    elif l in ('go', 'golang'):
        return f"strings.ToLower({var_name})"
    elif l in ('rust', 'rs'):
        return f"{var_name}.to_lowercase()"
    elif l == 'php':
        return f"strtolower({var_name})"
    elif l == 'swift':
        return f"{var_name}.lowercased()"
    elif l in ('objc', 'objective-c'):
        return f"[{var_name} lowercaseString]"
    return f"{var_name}.lower()"

def string_to_upper(var_name: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{var_name}.toUpperCase()"
    elif l in ('csharp', 'cs'):
        return f"{var_name}.ToUpperInvariant()"
    elif l in ('python', 'py'):
        return f"{var_name}.upper()"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{var_name}.toUpperCase()"
    elif l in ('go', 'golang'):
        return f"strings.ToUpper({var_name})"
    elif l in ('rust', 'rs'):
        return f"{var_name}.to_uppercase()"
    elif l == 'php':
        return f"strtoupper({var_name})"
    elif l == 'swift':
        return f"{var_name}.uppercased()"
    elif l in ('objc', 'objective-c'):
        return f"[{var_name} uppercaseString]"
    return f"{var_name}.upper()"

def string_split(var_name: str, delim: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"{var_name}.split({delim})"
    elif l in ('csharp', 'cs'):
        return f"{var_name}.Split({delim})"
    elif l in ('python', 'py'):
        return f"{var_name}.split({delim})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{var_name}.split({delim})"
    elif l in ('go', 'golang'):
        return f"strings.Split({var_name}, {delim})"
    elif l in ('rust', 'rs'):
        return f"{var_name}.split({delim}).collect::<Vec<_>>()"
    elif l == 'php':
        return f"explode({delim}, {var_name})"
    elif l == 'swift':
        return f"{var_name}.components(separatedBy: {delim})"
    elif l in ('objc', 'objective-c'):
        return f"[{var_name} componentsSeparatedByString:{delim}]"
    return f"{var_name}.split({delim})"

def string_join(delim: str, list_expr: str, lang: str) -> str:
    l = lang.lower().strip()
    if l in ('java', 'kotlin'):
        return f"String.join({delim}, {list_expr})"
    elif l in ('csharp', 'cs'):
        return f"string.Join({delim}, {list_expr})"
    elif l in ('python', 'py'):
        return f"{delim}.join({list_expr})"
    elif l in ('typescript', 'ts', 'javascript', 'js'):
        return f"{list_expr}.join({delim})"
    elif l in ('go', 'golang'):
        return f"strings.Join({list_expr}, {delim})"
    elif l in ('rust', 'rs'):
        return f"{list_expr}.join({delim})"
    elif l == 'php':
        return f"implode({delim}, {list_expr})"
    elif l == 'swift':
        return f"{list_expr}.joined(separator: {delim})"
    elif l in ('objc', 'objective-c'):
        return f"[{list_expr} componentsJoinedByString:{delim}]"
    return f"{delim}.join({list_expr})"

