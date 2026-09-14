import pytest
from elmos_spring_modernization.java_ast import (
    JavaLexer,
    JavaASTParser,
    JavaASTRewriter,
    TokenType,
    SpringMvcAnnotationVisitor,
    WebMvcConfigurerAdapterVisitor,
    SymbolResolutionContext,
    ImportDeclaration
)


def test_lexer_tokenizes_code_and_attaches_trivia():
    code = (
        "package com.example;\n"
        "// Leading line comment\n"
        "/* Block comment */\n"
        "@RestController\n"
        "public class UserController {\n"
        '    String str = "Hello \\"World\\"";\n'
        "}\n"
    )
    lexer = JavaLexer(code)
    tokens = lexer.tokenize()

    assert any(t.type == TokenType.ANNOTATION_AT for t in tokens)
    assert any(t.type == TokenType.STRING_LITERAL and 'Hello \\"World\\"' in t.value for t in tokens)
    # Verify comments are attached as trivia to the following token
    anno_token = next(t for t in tokens if t.type == TokenType.ANNOTATION_AT)
    assert "// Leading line comment" in anno_token.leading_trivia
    assert "/* Block comment */" in anno_token.leading_trivia


def test_ast_parser_builds_strongly_typed_unit():
    code = (
        "package com.example.api;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "@RestController\n"
        "public class OrderController extends BaseController implements Serializable {\n"
        '    @RequestMapping(value = "/orders", method = RequestMethod.GET)\n'
        "    public List<Order> getOrders() {}\n"
        "}\n"
    )
    lexer = JavaLexer(code)
    tokens = lexer.tokenize()
    parser = JavaASTParser(tokens)
    unit = parser.parse()

    assert unit.package_decl is not None
    assert unit.package_decl.name == "com.example.api"
    assert len(unit.imports) == 2
    assert len(unit.type_declarations) == 1

    type_decl = unit.type_declarations[0]
    assert type_decl.name == "OrderController"
    assert type_decl.kind == "class"
    assert len(type_decl.extends_types) == 1
    assert type_decl.extends_types[0].name == "BaseController"
    assert len(type_decl.implements_types) == 1
    assert type_decl.implements_types[0].name == "Serializable"

    assert len(type_decl.members) == 1
    method = type_decl.members[0]
    assert method.name == "getOrders"
    assert len(method.annotations) == 1
    anno = method.annotations[0]
    assert anno.name == "RequestMapping"
    assert anno.get_arg("method") is not None
    assert anno.get_arg("method").value == "RequestMethod.GET"


def test_symbol_resolution_context():
    imports = [
        ImportDeclaration(name="org.springframework.web.bind.annotation.RequestMapping"),
        ImportDeclaration(name="org.springframework.web.bind.annotation.RequestMethod"),
    ]
    ctx = SymbolResolutionContext(imports)
    assert ctx.resolve("RequestMapping") == "org.springframework.web.bind.annotation.RequestMapping"
    assert ctx.resolve("RequestMethod.GET") == "org.springframework.web.bind.annotation.RequestMethod.GET"
    assert ctx.resolve("WebMvcConfigurerAdapter") == "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter"


def test_ast_rewriter_replaces_spring_mvc_annotations_compiler_grade():
    code = (
        "package com.example.api;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMethod;\n"
        "public class ApiController {\n"
        '    @RequestMapping(value = "/users", method = RequestMethod.GET)\n'
        "    public List<User> getUsers() { return userService.findAll(); }\n"
        '    @RequestMapping(method = RequestMethod.POST, path = "/users")\n'
        "    public User createUser() { return userService.create(); }\n"
        '    @RequestMapping(value = "/users/{id}", method = RequestMethod.DELETE)\n'
        "    public void deleteUser() {}\n"
        "}\n"
    )

    rewritten, count = JavaASTRewriter.rewrite_spring_mvc_annotations(code)
    assert count == 3
    assert '@GetMapping("/users")' in rewritten
    assert '@PostMapping("/users")' in rewritten
    assert '@DeleteMapping("/users/{id}")' in rewritten
    assert "@RequestMapping" not in rewritten

    # Invariants: method bodies and implementations are 100% preserved
    assert "return userService.findAll();" in rewritten
    assert "return userService.create();" in rewritten


def test_ast_rewriter_replaces_webmvc_configurer_adapter():
    code = (
        "package com.example.config;\n"
        "import org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter;\n"
        "public class AppWebConfig extends WebMvcConfigurerAdapter {\n"
        "    public void addCors() {}\n"
        "}\n"
    )

    rewritten, count = JavaASTRewriter.rewrite_webmvc_configurer_adapter(code)
    assert count == 2
    assert "implements WebMvcConfigurer" in rewritten
    assert "import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;" in rewritten
    assert "WebMvcConfigurerAdapter" not in rewritten
    assert "public void addCors() {}" in rewritten


def test_ast_ignores_annotations_in_comments_and_strings():
    code = (
        "package com.example.api;\n"
        "// @RequestMapping(value = \"/comment\", method = RequestMethod.GET)\n"
        "public class FakeController {\n"
        '    private String doc = "@RequestMapping(value = \\"/doc\\", method = RequestMethod.GET)";\n'
        "}\n"
    )

    rewritten, count = JavaASTRewriter.rewrite_spring_mvc_annotations(code)
    assert count == 0
    assert rewritten == code
