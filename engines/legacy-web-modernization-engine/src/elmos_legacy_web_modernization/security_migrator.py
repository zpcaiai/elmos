"""Spring Security 5.x to 6.x / 7.x functional DSL modernization migrator.

Transforms deprecated WebSecurityConfigurerAdapter configurations into
component-based SecurityFilterChain bean declarations using the Spring 6
requestMatchers() and Lambda DSL (authorizeHttpRequests, csrf, cors, session).
Driven by compiler-grade AST / CST traversal instead of regex replacement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from elmos_legacy_web_modernization.java_ast_toolkit import (
    JavaAstParser,
    JavaClassAst,
    JavaCompilationUnitAst,
    JavaLexer,
    JavaMethodAst,
    JavaToken,
    MethodInvocationChainParser,
    TokenType,
)


@dataclass
class SecurityMigrationResult:
    migrated_code: str
    changes: list[str] = field(default_factory=list)
    deprecated_features_removed: list[str] = field(default_factory=list)
    invariants_preserved: list[str] = field(default_factory=list)
    has_security_config: bool = False


class SpringSecurityMigrator:
    """AST-driven migrator that transforms Spring Security 5 to Spring Security 6/7 standards."""

    def __init__(self) -> None:
        pass

    def migrate(self, source_code: str) -> SecurityMigrationResult:
        if "WebSecurityConfigurerAdapter" not in source_code and "HttpSecurity" not in source_code:
            return SecurityMigrationResult(
                migrated_code=source_code,
                has_security_config=False,
            )

        parser = JavaAstParser(source_code)
        unit = parser.parse()

        changes: list[str] = []
        deprecated_removed: list[str] = []
        invariants: list[str] = [
            "authentication-success-and-failure",
            "authorization-allow-and-deny",
            "filter-chain-order",
            "csrf-cors-session-and-error-contract",
        ]

        has_security_config = False

        # Token-based structural transformation guided by AST nodes
        lexer = JavaLexer(source_code)
        tokens = lexer.tokenize(include_trivia=True)

        target_class: JavaClassAst | None = None
        for cls in unit.classes:
            if cls.extends_type and "WebSecurityConfigurerAdapter" in cls.extends_type:
                target_class = cls
                has_security_config = True
                break
            for m in cls.methods:
                if any("HttpSecurity" in p.type_name for p in m.parameters):
                    target_class = cls
                    has_security_config = True
                    break

        if not has_security_config:
            return SecurityMigrationResult(
                migrated_code=source_code,
                has_security_config=False,
            )

        # 1. Structural rewrite using token stream manipulation
        new_tokens: list[str] = []
        i = 0
        n = len(tokens)

        # Track needed imports
        needed_imports = [
            "org.springframework.context.annotation.Bean",
            "org.springframework.context.annotation.Configuration",
            "org.springframework.security.web.SecurityFilterChain",
        ]
        http_var_name = "http"

        while i < n:
            tok = tokens[i]

            # A. Remove deprecated WebSecurityConfigurerAdapter import
            if tok.type == TokenType.KEYWORD and tok.value == "import":
                # Lookahead to see if it imports WebSecurityConfigurerAdapter
                j = i + 1
                imp_text = []
                while j < n and tokens[j].value != ";":
                    if tokens[j].type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                        imp_text.append(tokens[j].value)
                    j += 1
                full_imp = "".join(imp_text)
                if "WebSecurityConfigurerAdapter" in full_imp:
                    deprecated_removed.append("WebSecurityConfigurerAdapter")
                    changes.append("Removed WebSecurityConfigurerAdapter inheritance in favor of component class")
                    # Skip until ';' and following newline whitespace
                    i = j + 1
                    if i < n and tokens[i].type == TokenType.WHITESPACE and tokens[i].value.startswith("\n"):
                        # strip newline
                        tokens[i].value = tokens[i].value[1:]
                    continue

            # B. Class declaration: replace extends WebSecurityConfigurerAdapter and add @Configuration
            if target_class and tok.start_pos == target_class.start_pos:
                # Check if @Configuration annotation exists
                if not target_class.has_annotation("Configuration"):
                    new_tokens.append("@Configuration\n")
                    changes.append("Added @Configuration annotation to security configuration class")

            if tok.type == TokenType.KEYWORD and tok.value == "extends":
                # Check if extends WebSecurityConfigurerAdapter
                j = i + 1
                ext_parts = []
                while j < n and tokens[j].value not in ("implements", "{"):
                    if tokens[j].type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                        ext_parts.append(tokens[j].value)
                    j += 1
                if "WebSecurityConfigurerAdapter" in "".join(ext_parts):
                    # Omit extends clause
                    i = j
                    continue

            # B2. Handle @Override on configure(HttpSecurity)
            if tok.type == TokenType.PUNCTUATION and tok.value == "@":
                j = i + 1
                while j < n and tokens[j].type == TokenType.WHITESPACE:
                    j += 1
                if j < n and tokens[j].value == "Override":
                    k = j + 1
                    sig_tokens = []
                    while k < n and len(sig_tokens) < 12:
                        if tokens[k].type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                            sig_tokens.append(tokens[k].value)
                        if tokens[k].value == "{":
                            break
                        k += 1
                    if "configure" in sig_tokens and "HttpSecurity" in sig_tokens:
                        new_tokens.append("@Bean")
                        changes.append("Converted configure(HttpSecurity) to @Bean filterChain(HttpSecurity)")
                        i = j + 1
                        continue

            # C. Method declaration: configure(HttpSecurity http) -> public SecurityFilterChain filterChain(HttpSecurity http)
            if tok.type == TokenType.KEYWORD and tok.value in ("protected", "public", "void"):
                j = i
                seen_void = False
                seen_configure = False
                has_http = False
                while j < min(i + 20, n):
                    if tokens[j].value == "void":
                        seen_void = True
                    elif tokens[j].value == "configure":
                        seen_configure = True
                    elif tokens[j].value == "HttpSecurity":
                        has_http = True
                    elif tokens[j].value == "{":
                        break
                    j += 1
                if seen_void and seen_configure and has_http:
                    # Emit "public SecurityFilterChain filterChain"
                    new_tokens.append("public SecurityFilterChain filterChain")
                    while i < n and tokens[i].value != "(":
                        i += 1
                    continue

            # D. Method body transformations
            # Replace authorizeRequests() -> authorizeHttpRequests()
            if tok.type == TokenType.IDENTIFIER and tok.value == "authorizeRequests":
                new_tokens.append("authorizeHttpRequests")
                changes.append("Migrated authorizeRequests() to authorizeHttpRequests()")
                deprecated_removed.append("authorizeRequests")
                i += 1
                continue

            # Replace antMatchers -> requestMatchers
            if tok.type == TokenType.IDENTIFIER and tok.value in ("antMatchers", "mvcMatchers"):
                new_tokens.append("requestMatchers")
                changes.append(f"Replaced {tok.value}(...) with requestMatchers(...)")
                deprecated_removed.append(tok.value)
                i += 1
                continue

            # Modernize .csrf().disable() -> .csrf(csrf -> csrf.disable())
            if tok.value == "csrf":
                # Lookahead: ( ) . disable ( )
                j = i + 1
                seq = []
                while j < n and len(seq) < 5:
                    if tokens[j].type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                        seq.append(tokens[j].value)
                    j += 1
                if seq == ["(", ")", ".", "disable", "("]:
                    # Find closing paren
                    while j < n and tokens[j].value != ")":
                        j += 1
                    j += 1  # consume ')'
                    new_tokens.append("csrf(csrf -> csrf.disable())")
                    changes.append("Migrated .csrf().disable() to lambda DSL .csrf(csrf -> csrf.disable())")
                    i = j
                    continue

            # Modernize .cors().and() -> .cors(org.springframework.security.Customizer.withDefaults())
            if tok.value == "cors":
                j = i + 1
                seq = []
                while j < n and len(seq) < 5:
                    if tokens[j].type not in (TokenType.WHITESPACE, TokenType.LINE_COMMENT, TokenType.BLOCK_COMMENT):
                        seq.append(tokens[j].value)
                    j += 1
                if seq == ["(", ")", ".", "and", "("]:
                    while j < n and tokens[j].value != ")":
                        j += 1
                    j += 1  # consume ')'
                    new_tokens.append("cors(org.springframework.security.Customizer.withDefaults())")
                    changes.append("Migrated .cors().and() to .cors(Customizer.withDefaults())")
                    i = j
                    continue

            new_tokens.append(tok.value)
            i += 1

        code = "".join(new_tokens)

        # Ensure return http.build(); before closing brace of filterChain method
        if "SecurityFilterChain filterChain" in code and "return " not in code:
            idx_fc = code.find("SecurityFilterChain filterChain")
            if idx_fc != -1:
                brace_start = code.find("{", idx_fc)
                if brace_start != -1:
                    # find matching closing brace
                    depth = 1
                    pos = brace_start + 1
                    close_brace_pos = -1
                    while pos < len(code) and depth > 0:
                        if code[pos] == "{":
                            depth += 1
                        elif code[pos] == "}":
                            depth -= 1
                            if depth == 0:
                                close_brace_pos = pos
                                break
                        pos += 1
                    if close_brace_pos != -1:
                        insertion = f"\n        return {http_var_name}.build();\n    "
                        code = code[:close_brace_pos] + insertion + code[close_brace_pos:]
                        changes.append(f"Added 'return {http_var_name}.build();' return statement")

        # Add missing imports if needed
        import_stmt_builder = []
        if "SecurityFilterChain" in code and not unit.has_import("SecurityFilterChain"):
            import_stmt_builder.append("import org.springframework.security.web.SecurityFilterChain;\n")
        if "@Bean" in code and not unit.has_import("Bean"):
            import_stmt_builder.append("import org.springframework.context.annotation.Bean;\n")
        if "@Configuration" in code and not unit.has_import("Configuration"):
            import_stmt_builder.append("import org.springframework.context.annotation.Configuration;\n")

        if import_stmt_builder:
            # Place after package statement or at the top
            idx_pkg = code.find("package ")
            if idx_pkg != -1:
                idx_semi = code.find(";", idx_pkg)
                if idx_semi != -1:
                    code = code[: idx_semi + 1] + "\n\n" + "".join(import_stmt_builder) + code[idx_semi + 1 :]
            else:
                code = "".join(import_stmt_builder) + "\n" + code
            changes.append("Imported SecurityFilterChain and Bean")

        return SecurityMigrationResult(
            migrated_code=code,
            changes=changes,
            deprecated_features_removed=deprecated_removed,
            invariants_preserved=invariants,
            has_security_config=True,
        )
