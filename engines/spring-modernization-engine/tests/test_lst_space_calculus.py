from __future__ import annotations

import pytest
from elmos_spring_modernization.java_ast import (
    JavaLexer,
    JavaASTParser,
    Space,
    Comment,
    JavaLSTMutator,
    AutoFormatVisitor,
    JavaASTRewriter,
    AnnotationNode,
    AnnotationArgument,
)


def test_space_build_and_comment_parsing():
    raw_trivia = "  \n  // this is a line comment\n  /* block comment */  \n"
    sp = Space.build(raw_trivia)
    assert len(sp.comments) == 2
    assert sp.comments[0].is_multiline is False
    assert "this is a line comment" in sp.comments[0].text
    assert sp.comments[1].is_multiline is True
    assert "block comment" in sp.comments[1].text


def test_lst_mutator_replaces_annotations_in_memory():
    code = """package com.example.demo;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @RequestMapping(value = "/orders", method = RequestMethod.GET)
    public List<Order> listOrders() {
        return orderService.findAll();
    }
}
"""
    lexer = JavaLexer(code)
    tokens = lexer.tokenize()
    parser = JavaASTParser(tokens, source=code)
    unit = parser.parse()

    mutator = JavaLSTMutator(unit)
    # Replace @RequestMapping with @GetMapping("/orders")
    type_decl = unit.type_declarations[0]
    method = type_decl.members[0]

    new_get = AnnotationNode(
        name="GetMapping",
        arguments=[AnnotationArgument(value='"/orders"')]
    )
    mutator.replace_annotation(method, "RequestMapping", new_get)
    mutator.add_import("org.springframework.web.bind.annotation.GetMapping")
    mutator.remove_import("org.springframework.web.bind.annotation.RequestMapping")

    assert mutator.mutations_count == 3
    assert method.annotations[0].name == "GetMapping"

    formatter = AutoFormatVisitor()
    formatted = formatter.format(unit)

    assert "import org.springframework.web.bind.annotation.GetMapping;" in formatted
    assert "import org.springframework.web.bind.annotation.RequestMapping;" not in formatted
    assert "@GetMapping(\"/orders\")" in formatted
    assert "public List<Order> listOrders() {" in formatted
    assert "return orderService.findAll();" in formatted


def test_lst_mutator_extends_to_implements():
    code = """package com.example.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter;

@Configuration
public class WebMvcConfig extends WebMvcConfigurerAdapter {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/**");
    }
}
"""
    lexer = JavaLexer(code)
    tokens = lexer.tokenize()
    parser = JavaASTParser(tokens, source=code)
    unit = parser.parse()

    mutator = JavaLSTMutator(unit)
    type_decl = unit.type_declarations[0]
    mutator.replace_extends(type_decl, "WebMvcConfigurerAdapter", new_implements="WebMvcConfigurer")
    mutator.replace_import(
        "org.springframework.web.servlet.config.annotation.WebMvcConfigurerAdapter",
        "org.springframework.web.servlet.config.annotation.WebMvcConfigurer"
    )

    formatter = AutoFormatVisitor()
    formatted = formatter.format(unit)

    assert "import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;" in formatted
    assert "public class WebMvcConfig implements WebMvcConfigurer {" in formatted
    assert "extends WebMvcConfigurerAdapter" not in formatted
    assert "public void addCorsMappings(CorsRegistry registry) {" in formatted


def test_ast_rewriter_rewrite_with_lst():
    code = """package com.example.api;

public class SampleApi {

    @Deprecated
    public void doOldThing() {
        System.out.println("old");
    }
}
"""
    def transform(mutator: JavaLSTMutator):
        type_decl = mutator.unit.type_declarations[0]
        method = type_decl.members[0]
        mutator.replace_method_body(method, "System.out.println(\"new and improved\");")

    formatted, count = JavaASTRewriter.rewrite_with_lst(code, transform)
    assert count == 1
    assert "System.out.println(\"new and improved\");" in formatted
    assert "System.out.println(\"old\");" not in formatted
