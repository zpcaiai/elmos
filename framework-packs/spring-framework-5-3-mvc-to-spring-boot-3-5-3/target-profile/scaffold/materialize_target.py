#!/usr/bin/env python3
"""Materialize the exact, fail-closed legacy MVC fixture as a Boot executable WAR.

The emitter accepts only the construct set described by this pack's FCM. It
creates a new target tree and never edits or deletes the source. Runtime build,
startup, and behavior evidence remain separate NOT_RUN gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PACK_KEY = "spring-framework-5-3-mvc-to-spring-boot-3-5-3"
SOURCE_FRAMEWORK = "5.3.39"
TARGET_BOOT = "3.5.3"
SOURCE_JAVA = "11"
TARGET_JAVA = "21"
MAVEN_VERSION = "3.9.11"
MAVEN_NS = "http://maven.apache.org/POM/4.0.0"
WEB_NS = "http://xmlns.jcp.org/xml/ns/javaee"
BEANS_NS = "http://www.springframework.org/schema/beans"
CONTEXT_NS = "http://www.springframework.org/schema/context"
MVC_NS = "http://www.springframework.org/schema/mvc"

EXPECTED_DEPENDENCIES = {
    ("org.springframework", "spring-webmvc"): ("${spring-framework.version}", ""),
    ("javax.servlet", "javax.servlet-api"): ("${servlet-api.version}", "provided"),
    ("javax.validation", "validation-api"): ("${validation-api.version}", ""),
    ("org.hibernate.validator", "hibernate-validator"): ("${hibernate-validator.version}", ""),
    ("org.glassfish", "javax.el"): ("3.0.1-b12", ""),
    ("com.fasterxml.jackson.core", "jackson-databind"): ("${jackson.version}", ""),
    ("org.springframework", "spring-test"): ("${spring-framework.version}", "test"),
    ("org.junit.jupiter", "junit-jupiter"): ("${junit.version}", "test"),
    ("org.hamcrest", "hamcrest"): ("${hamcrest.version}", "test"),
    ("com.jayway.jsonpath", "json-path"): ("${json-path.version}", "test"),
}
EXPECTED_PLUGINS = {
    ("org.apache.maven.plugins", "maven-compiler-plugin"): (
        "3.13.0", "release", SOURCE_JAVA,
    ),
    ("org.apache.maven.plugins", "maven-surefire-plugin"): (
        "3.5.2", "useModulePath", "false",
    ),
    ("org.apache.maven.plugins", "maven-war-plugin"): (
        "3.4.0", "failOnMissingWebXml", "true",
    ),
}
EXPECTED_MAIN_JAVA_STEREOTYPES = {
    "io/elmos/legacy/service/LegacyOrderService.java": {"Service"},
    "io/elmos/legacy/web/ApiExceptionHandler.java": {"ControllerAdvice"},
    "io/elmos/legacy/web/LegacyOrderController.java": {"Controller"},
    "io/elmos/legacy/web/LegacyOrderForm.java": set(),
    "io/elmos/legacy/web/RequestAuditInterceptor.java": set(),
}
STEREOTYPE_ANNOTATIONS = {
    "Component", "Configuration", "Controller", "ControllerAdvice",
    "Repository", "RestController", "Service",
}
FORBIDDEN_CONFIGURATION_ANNOTATIONS = {
    "Bean", "ComponentScan", "EnableWebMvc", "Import", "ImportResource",
    "WebFilter", "WebListener", "WebServlet",
}
BLOCKED_SOURCE_TOKENS = {
    "WebApplicationInitializer": "programmatic servlet bootstrap",
    "ServletContainerInitializer": "container initializer",
    "AbstractAnnotationConfigDispatcherServletInitializer": "programmatic servlet bootstrap",
    "org.springframework.security": "Spring Security profile",
    "javax.persistence": "persistence profile",
    "jakarta.persistence": "persistence profile",
    "@Transactional": "transaction profile",
    "JmsTemplate": "messaging profile",
    "RabbitTemplate": "messaging profile",
    "CacheManager": "cache profile",
    "@Scheduled": "scheduler profile",
}


class UnsupportedSource(RuntimeError):
    pass


def q(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


def child_text(parent: ET.Element, namespace: str, local: str) -> str:
    node = parent.find(q(namespace, local))
    return "" if node is None or node.text is None else node.text.strip()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise UnsupportedSource(message)


def local_name(tag: str) -> str:
    return tag.split("}")[-1]


def require_child_tags(element: ET.Element, expected: list[str], label: str) -> None:
    actual = [child.tag for child in element]
    require(actual == expected, f"{label} child graph is not the exact admitted contract")


def require_attributes(element: ET.Element, expected: dict[str, str], label: str) -> None:
    require(element.attrib == expected, f"{label} attributes are not the exact admitted contract")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_xml(path: Path) -> ET.Element:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise UnsupportedSource(f"cannot parse {path}: {exc}") from exc


def validate_pom(source: Path) -> None:
    root = parse_xml(source / "pom.xml")
    require(root.tag == q(MAVEN_NS, "project"), "POM must use the Maven namespace")
    require_child_tags(
        root,
        [
            q(MAVEN_NS, "modelVersion"), q(MAVEN_NS, "groupId"),
            q(MAVEN_NS, "artifactId"), q(MAVEN_NS, "version"),
            q(MAVEN_NS, "packaging"), q(MAVEN_NS, "properties"),
            q(MAVEN_NS, "dependencies"), q(MAVEN_NS, "build"),
        ],
        "source POM",
    )
    require(root.find(q(MAVEN_NS, "parent")) is None, "existing Maven parent requires an approved parent/BOM strategy")
    require(child_text(root, MAVEN_NS, "modelVersion") == "4.0.0", "source POM modelVersion must be 4.0.0")
    require(child_text(root, MAVEN_NS, "groupId") == "io.elmos.fixtures", "source POM groupId must be io.elmos.fixtures")
    require(child_text(root, MAVEN_NS, "artifactId") == "legacy-spring-mvc", "source POM artifactId must be legacy-spring-mvc")
    require(child_text(root, MAVEN_NS, "version") == "1.0.0", "source POM version must be 1.0.0")
    require(child_text(root, MAVEN_NS, "packaging") == "war", "source packaging must be war")
    properties = root.find(q(MAVEN_NS, "properties"))
    require(properties is not None, "source POM properties are required")
    expected_properties = {
        "project.build.sourceEncoding": "UTF-8",
        "maven.compiler.release": SOURCE_JAVA,
        "spring-framework.version": SOURCE_FRAMEWORK,
        "servlet-api.version": "4.0.1",
        "validation-api.version": "2.0.1.Final",
        "hibernate-validator.version": "6.2.5.Final",
        "jackson.version": "2.17.2",
        "junit.version": "5.10.3",
        "hamcrest.version": "2.2",
        "json-path.version": "2.7.0",
    }
    require_child_tags(
        properties,
        [q(MAVEN_NS, name) for name in expected_properties],
        "source POM properties",
    )
    for name, expected in expected_properties.items():
        require(child_text(properties, MAVEN_NS, name) == expected, f"source POM {name} must equal {expected}")
    dependencies = root.find(q(MAVEN_NS, "dependencies"))
    require(dependencies is not None, "source POM dependencies are required")
    dependency_nodes = dependencies.findall(q(MAVEN_NS, "dependency"))
    coordinates = [
        (child_text(item, MAVEN_NS, "groupId"), child_text(item, MAVEN_NS, "artifactId"))
        for item in dependency_nodes
    ]
    require(len(coordinates) == len(set(coordinates)), "duplicate source dependency coordinates are not admitted")
    require(
        set(coordinates) == set(EXPECTED_DEPENDENCIES),
        f"source dependency graph must equal the exact admitted profile; found: {sorted(coordinates)}",
    )
    for item, coordinate in zip(dependency_nodes, coordinates, strict=True):
        expected_version, expected_scope = EXPECTED_DEPENDENCIES[coordinate]
        expected_children = [q(MAVEN_NS, name) for name in ("groupId", "artifactId", "version")]
        if expected_scope:
            expected_children.append(q(MAVEN_NS, "scope"))
        require_child_tags(item, expected_children, f"dependency {coordinate[0]}:{coordinate[1]}")
        require(child_text(item, MAVEN_NS, "version") == expected_version, f"dependency {coordinate[0]}:{coordinate[1]} version must equal {expected_version}")
        require(child_text(item, MAVEN_NS, "scope") == expected_scope, f"dependency {coordinate[0]}:{coordinate[1]} scope must equal {expected_scope or 'compile'}")

    build = root.find(q(MAVEN_NS, "build"))
    require(build is not None, "source POM build is required")
    require_child_tags(build, [q(MAVEN_NS, "finalName"), q(MAVEN_NS, "plugins")], "source POM build")
    require(child_text(build, MAVEN_NS, "finalName") == "legacy-spring-mvc", "source POM finalName must be legacy-spring-mvc")
    plugins = build.find(q(MAVEN_NS, "plugins"))
    require(plugins is not None, "source POM plugins are required")
    plugin_nodes = plugins.findall(q(MAVEN_NS, "plugin"))
    plugin_coordinates = [
        (child_text(item, MAVEN_NS, "groupId"), child_text(item, MAVEN_NS, "artifactId"))
        for item in plugin_nodes
    ]
    require(len(plugin_coordinates) == len(set(plugin_coordinates)), "duplicate source build plugins are not admitted")
    require(set(plugin_coordinates) == set(EXPECTED_PLUGINS), f"source build plugin graph must equal the exact admitted profile; found: {sorted(plugin_coordinates)}")
    for item, coordinate in zip(plugin_nodes, plugin_coordinates, strict=True):
        expected_version, setting_name, setting_value = EXPECTED_PLUGINS[coordinate]
        require_child_tags(
            item,
            [q(MAVEN_NS, "groupId"), q(MAVEN_NS, "artifactId"), q(MAVEN_NS, "version"), q(MAVEN_NS, "configuration")],
            f"plugin {coordinate[0]}:{coordinate[1]}",
        )
        require(child_text(item, MAVEN_NS, "version") == expected_version, f"plugin {coordinate[0]}:{coordinate[1]} version must equal {expected_version}")
        configuration = item.find(q(MAVEN_NS, "configuration"))
        require(configuration is not None, f"plugin {coordinate[0]}:{coordinate[1]} configuration is required")
        require_child_tags(configuration, [q(MAVEN_NS, setting_name)], f"plugin {coordinate[0]}:{coordinate[1]} configuration")
        require(child_text(configuration, MAVEN_NS, setting_name) == setting_value, f"plugin {coordinate[0]}:{coordinate[1]} {setting_name} must equal {setting_value}")


def validate_web_xml(source: Path) -> None:
    root = parse_xml(source / "src/main/webapp/WEB-INF/web.xml")
    require(root.tag == q(WEB_NS, "web-app") and root.get("version") == "4.0", "only Servlet 4.0 web.xml is admitted")
    require_child_tags(
        root,
        [
            q(WEB_NS, "display-name"), q(WEB_NS, "context-param"),
            q(WEB_NS, "listener"), q(WEB_NS, "filter"),
            q(WEB_NS, "filter-mapping"), q(WEB_NS, "servlet"),
            q(WEB_NS, "servlet-mapping"),
        ],
        "web.xml",
    )
    display_name = root.find(q(WEB_NS, "display-name"))
    require(display_name is not None and (display_name.text or "").strip() == "Legacy Spring MVC Orders" and len(display_name) == 0, "unsupported web.xml display-name")
    context_params = root.findall(q(WEB_NS, "context-param"))
    require(len(context_params) == 1, "exactly one root context location is required")
    require_child_tags(context_params[0], [q(WEB_NS, "param-name"), q(WEB_NS, "param-value")], "web.xml context-param")
    require(not context_params[0].attrib, "web.xml context-param attributes are not admitted")
    require(child_text(context_params[0], WEB_NS, "param-name") == "contextConfigLocation" and child_text(context_params[0], WEB_NS, "param-value") == "classpath:/WEB-INF/spring/root-context.xml", "unsupported root context location")
    listeners = root.findall(q(WEB_NS, "listener"))
    require(len(listeners) == 1, "exactly one ContextLoaderListener is required")
    require_child_tags(listeners[0], [q(WEB_NS, "listener-class")], "web.xml listener")
    require(not listeners[0].attrib, "web.xml listener attributes are not admitted")
    require(child_text(listeners[0], WEB_NS, "listener-class") == "org.springframework.web.context.ContextLoaderListener", "unsupported servlet listener")
    filters = root.findall(q(WEB_NS, "filter"))
    require(len(filters) == 1, "only the CharacterEncodingFilter profile is admitted")
    require_child_tags(
        filters[0],
        [q(WEB_NS, "filter-name"), q(WEB_NS, "filter-class"), q(WEB_NS, "init-param"), q(WEB_NS, "init-param")],
        "web.xml filter",
    )
    require(not filters[0].attrib, "web.xml filter attributes are not admitted")
    for index, init_param in enumerate(filters[0].findall(q(WEB_NS, "init-param")), start=1):
        require_child_tags(init_param, [q(WEB_NS, "param-name"), q(WEB_NS, "param-value")], f"web.xml filter init-param {index}")
        require(not init_param.attrib, f"web.xml filter init-param {index} attributes are not admitted")
    require(child_text(filters[0], WEB_NS, "filter-class") == "org.springframework.web.filter.CharacterEncodingFilter", "unsupported servlet filter requires an exact profile")
    init_params = {
        child_text(item, WEB_NS, "param-name"): child_text(item, WEB_NS, "param-value")
        for item in filters[0].findall(q(WEB_NS, "init-param"))
    }
    require(init_params == {"encoding": "UTF-8", "forceEncoding": "true"}, "encoding filter parameters are not the admitted UTF-8 contract")
    mappings = root.findall(q(WEB_NS, "filter-mapping"))
    require(len(mappings) == 1, "exactly one encoding filter mapping is required")
    require_child_tags(
        mappings[0],
        [q(WEB_NS, "filter-name"), q(WEB_NS, "url-pattern"), q(WEB_NS, "dispatcher"), q(WEB_NS, "dispatcher")],
        "web.xml filter-mapping",
    )
    require(not mappings[0].attrib, "web.xml filter-mapping attributes are not admitted")
    dispatchers = [node.text.strip() for node in mappings[0].findall(q(WEB_NS, "dispatcher")) if node.text]
    require(child_text(mappings[0], WEB_NS, "url-pattern") == "/*", "encoding filter must map to /*")
    require(child_text(mappings[0], WEB_NS, "filter-name") == "characterEncodingFilter", "encoding filter mapping name must be exact")
    require(dispatchers == ["REQUEST", "ERROR"], "encoding filter dispatch order must be REQUEST, ERROR")
    servlets = root.findall(q(WEB_NS, "servlet"))
    require(len(servlets) == 1, "exactly one DispatcherServlet is required")
    require_child_tags(
        servlets[0],
        [q(WEB_NS, "servlet-name"), q(WEB_NS, "servlet-class"), q(WEB_NS, "init-param"), q(WEB_NS, "load-on-startup")],
        "web.xml servlet",
    )
    require(not servlets[0].attrib, "web.xml servlet attributes are not admitted")
    require(child_text(servlets[0], WEB_NS, "servlet-name") == "legacy", "DispatcherServlet name must be legacy")
    require(child_text(servlets[0], WEB_NS, "servlet-class") == "org.springframework.web.servlet.DispatcherServlet", "unsupported servlet class")
    servlet_params = servlets[0].findall(q(WEB_NS, "init-param"))
    if servlet_params:
        require_child_tags(servlet_params[0], [q(WEB_NS, "param-name"), q(WEB_NS, "param-value")], "web.xml servlet init-param")
        require(not servlet_params[0].attrib, "web.xml servlet init-param attributes are not admitted")
    require(len(servlet_params) == 1 and child_text(servlet_params[0], WEB_NS, "param-name") == "contextConfigLocation" and child_text(servlet_params[0], WEB_NS, "param-value") == "classpath:/WEB-INF/spring/servlet-context.xml", "unsupported DispatcherServlet context location")
    require(child_text(servlets[0], WEB_NS, "load-on-startup") == "1", "DispatcherServlet must retain load-on-startup 1")
    servlet_mappings = root.findall(q(WEB_NS, "servlet-mapping"))
    if servlet_mappings:
        require_child_tags(servlet_mappings[0], [q(WEB_NS, "servlet-name"), q(WEB_NS, "url-pattern")], "web.xml servlet-mapping")
        require(not servlet_mappings[0].attrib, "web.xml servlet-mapping attributes are not admitted")
    require(len(servlet_mappings) == 1 and child_text(servlet_mappings[0], WEB_NS, "servlet-name") == "legacy" and child_text(servlet_mappings[0], WEB_NS, "url-pattern") == "/", "DispatcherServlet must map to /")
    web_containers = {
        q(WEB_NS, "web-app"), q(WEB_NS, "context-param"), q(WEB_NS, "listener"),
        q(WEB_NS, "filter"), q(WEB_NS, "init-param"), q(WEB_NS, "filter-mapping"),
        q(WEB_NS, "servlet"), q(WEB_NS, "servlet-mapping"),
    }
    for element in root.iter():
        if element is not root:
            require(not element.attrib, f"web.xml {local_name(element.tag)} attributes are not admitted")
        if element.tag not in web_containers:
            require(len(element) == 0, f"web.xml {local_name(element.tag)} must be a leaf element")


def validate_contexts(source: Path) -> None:
    root_context = parse_xml(source / "src/main/resources/WEB-INF/spring/root-context.xml")
    servlet_context = parse_xml(source / "src/main/resources/WEB-INF/spring/servlet-context.xml")
    require(root_context.tag == q(BEANS_NS, "beans"), "root context must be Spring beans XML")
    require(servlet_context.tag == q(BEANS_NS, "beans"), "servlet context must be Spring beans XML")
    require_child_tags(
        root_context,
        [q(CONTEXT_NS, "property-placeholder"), q(CONTEXT_NS, "component-scan")],
        "root Spring context",
    )
    placeholders = root_context.findall(q(CONTEXT_NS, "property-placeholder"))
    scans = root_context.findall(q(CONTEXT_NS, "component-scan"))
    require(len(placeholders) == 1 and placeholders[0].get("location") == "classpath:legacy.properties", "unsupported property source graph")
    require(placeholders[0].get("ignore-unresolvable") == "false", "unresolved placeholders must fail closed")
    require_attributes(placeholders[0], {"location": "classpath:legacy.properties", "ignore-unresolvable": "false"}, "root property-placeholder")
    require(len(placeholders[0]) == 0, "root property-placeholder children are not admitted")
    require(len(scans) == 1 and scans[0].get("base-package") == "io.elmos.legacy.service", "unsupported root component scan")
    require_attributes(scans[0], {"base-package": "io.elmos.legacy.service"}, "root component-scan")
    require(len(scans[0]) == 0, "root component-scan filters require an exact profile")
    require_child_tags(
        servlet_context,
        [
            q(CONTEXT_NS, "component-scan"), q(MVC_NS, "annotation-driven"),
            q(MVC_NS, "resources"), q(MVC_NS, "default-servlet-handler"),
            q(MVC_NS, "interceptors"), q(BEANS_NS, "bean"), q(BEANS_NS, "bean"),
        ],
        "servlet Spring context",
    )
    scans = servlet_context.findall(q(CONTEXT_NS, "component-scan"))
    require(len(scans) == 1 and scans[0].get("base-package") == "io.elmos.legacy.web", "unsupported web component scan")
    require_attributes(scans[0], {"base-package": "io.elmos.legacy.web"}, "web component-scan")
    require(len(scans[0]) == 0, "web component-scan filters require an exact profile")
    annotation_driven = servlet_context.findall(q(MVC_NS, "annotation-driven"))
    require(len(annotation_driven) == 1 and annotation_driven[0].get("validator") == "validator" and len(annotation_driven[0]) == 0, "unsupported annotation-driven configuration")
    require_attributes(annotation_driven[0], {"validator": "validator"}, "annotation-driven")
    resources = servlet_context.findall(q(MVC_NS, "resources"))
    require(len(resources) == 1 and resources[0].get("mapping") == "/assets/**" and resources[0].get("location") == "/assets/" and resources[0].get("cache-period") == "3600", "unsupported static resource contract")
    require_attributes(resources[0], {"mapping": "/assets/**", "location": "/assets/", "cache-period": "3600"}, "MVC resources")
    require(len(resources[0]) == 0, "MVC resource children are not admitted")
    default_handlers = servlet_context.findall(q(MVC_NS, "default-servlet-handler"))
    require(len(default_handlers) == 1 and len(default_handlers[0]) == 0 and not default_handlers[0].attrib, "default servlet handler must be exact")
    bean_nodes = servlet_context.findall(q(BEANS_NS, "bean"))
    bean_classes = [node.get("class") for node in bean_nodes]
    require(len(bean_nodes) == 2 and set(bean_classes) == {"org.springframework.validation.beanvalidation.LocalValidatorFactoryBean", "org.springframework.web.servlet.view.InternalResourceViewResolver"}, "unsupported or duplicate servlet bean graph")
    validator_beans = [node for node in servlet_context.findall(q(BEANS_NS, "bean")) if node.get("class") == "org.springframework.validation.beanvalidation.LocalValidatorFactoryBean"]
    require(len(validator_beans) == 1 and validator_beans[0].get("id") == "validator" and len(validator_beans[0]) == 0, "unsupported validator bean configuration")
    require_attributes(validator_beans[0], {"id": "validator", "class": "org.springframework.validation.beanvalidation.LocalValidatorFactoryBean"}, "validator bean")
    view_beans = [node for node in servlet_context.findall(q(BEANS_NS, "bean")) if node.get("class") == "org.springframework.web.servlet.view.InternalResourceViewResolver"]
    require(len(view_beans) == 1, "exactly one InternalResourceViewResolver is required")
    require_attributes(view_beans[0], {"class": "org.springframework.web.servlet.view.InternalResourceViewResolver"}, "view resolver bean")
    require_child_tags(view_beans[0], [q(BEANS_NS, "property"), q(BEANS_NS, "property"), q(BEANS_NS, "property")], "view resolver bean")
    view_properties = {node.get("name"): node.get("value") for node in view_beans[0].findall(q(BEANS_NS, "property"))}
    require(view_properties == {"prefix": "/WEB-INF/views/", "suffix": ".jsp", "order": "10"}, "unsupported JSP view resolver contract")
    for view_property in view_beans[0].findall(q(BEANS_NS, "property")):
        require(len(view_property) == 0, "nested view resolver property values are not admitted")
        require(set(view_property.attrib) == {"name", "value"}, "view resolver property attributes are not exact")
    interceptor_containers = servlet_context.findall(q(MVC_NS, "interceptors"))
    require(len(interceptor_containers) == 1, "exactly one MVC interceptors container is admitted")
    require(not interceptor_containers[0].attrib, "MVC interceptors container attributes are not admitted")
    require_child_tags(interceptor_containers[0], [q(MVC_NS, "interceptor")], "MVC interceptors container")
    interceptors = interceptor_containers[0].findall(q(MVC_NS, "interceptor"))
    require(len(interceptors) == 1 and not interceptors[0].attrib, "exactly one attribute-free MVC interceptor is admitted")
    require_child_tags(interceptors[0], [q(MVC_NS, "mapping"), q(BEANS_NS, "bean")], "MVC interceptor")
    interceptor_beans = interceptors[0].findall(q(BEANS_NS, "bean"))
    require(len(interceptor_beans) == 1 and interceptor_beans[0].get("class") == "io.elmos.legacy.web.RequestAuditInterceptor", "unsupported interceptor graph")
    require_attributes(interceptor_beans[0], {"class": "io.elmos.legacy.web.RequestAuditInterceptor"}, "MVC interceptor bean")
    require(len(interceptor_beans[0]) == 0, "nested MVC interceptor bean configuration is not admitted")
    interceptor_mappings = interceptors[0].findall(q(MVC_NS, "mapping"))
    require(len(interceptor_mappings) == 1 and interceptor_mappings[0].get("path") == "/api/**", "unsupported interceptor path contract")
    require_attributes(interceptor_mappings[0], {"path": "/api/**"}, "MVC interceptor mapping")
    require(len(interceptor_mappings[0]) == 0, "nested MVC interceptor mapping is not admitted")


def validate_source_tokens(source: Path) -> None:
    main_java_root = source / "src/main/java"
    main_java_files = {
        path.relative_to(main_java_root).as_posix(): path
        for path in main_java_root.rglob("*.java")
    }
    require(
        set(main_java_files) == set(EXPECTED_MAIN_JAVA_STEREOTYPES),
        f"main Java source graph must equal the exact admitted fixture; found: {sorted(main_java_files)}",
    )
    candidates = list((source / "src/main/java").rglob("*.java")) + list((source / "src/main/resources").rglob("*"))
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for token, profile in BLOCKED_SOURCE_TOKENS.items():
            require(token not in text, f"{path.relative_to(source)} requires unsupported {profile}")
        if path.suffix == ".java" and "/main/java/" in path.as_posix():
            package_lines = [line.strip() for line in text.splitlines() if line.strip().startswith("package ")]
            require(len(package_lines) == 1, f"{path.relative_to(source)} must declare exactly one package")
            package_name = package_lines[0].removeprefix("package ").removesuffix(";")
            require(package_name.startswith("io.elmos.legacy.service") or package_name.startswith("io.elmos.legacy.web"), f"{path.relative_to(source)} is outside the admitted component scans")
            relative_java = path.relative_to(main_java_root).as_posix()
            annotation_names = {
                match.split(".")[-1]
                for match in re.findall(r"(?m)^\s*@([A-Za-z_][A-Za-z0-9_.]*)", text)
            }
            actual_stereotypes = annotation_names & STEREOTYPE_ANNOTATIONS
            require(
                actual_stereotypes == EXPECTED_MAIN_JAVA_STEREOTYPES[relative_java],
                f"{path.relative_to(source)} component stereotypes must equal {sorted(EXPECTED_MAIN_JAVA_STEREOTYPES[relative_java])}",
            )
            forbidden_annotations = annotation_names & FORBIDDEN_CONFIGURATION_ANNOTATIONS
            require(
                not forbidden_annotations,
                f"{path.relative_to(source)} contains unsupported configuration annotations: {sorted(forbidden_annotations)}",
            )
    jsp_files = sorted((source / "src/main/webapp/WEB-INF/views").rglob("*.jsp"))
    require(jsp_files, "the admitted executable-WAR profile requires JSP views")
    for jsp in jsp_files:
        text = jsp.read_text(encoding="utf-8")
        require("<%@ taglib" not in text and "<jsp:" not in text, f"{jsp.relative_to(source)} requires an explicit JSP tag-library profile")


def validate_source(source: Path) -> None:
    required = [
        "pom.xml", "src/main/webapp/WEB-INF/web.xml",
        "src/main/resources/WEB-INF/spring/root-context.xml",
        "src/main/resources/WEB-INF/spring/servlet-context.xml",
        "src/main/resources/legacy.properties",
    ]
    missing = [item for item in required if not (source / item).is_file()]
    require(not missing, f"missing required source files: {missing}")
    validate_pom(source)
    validate_web_xml(source)
    validate_contexts(source)
    validate_source_tokens(source)


POM = f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>{TARGET_BOOT}</version><relativePath/></parent>
  <groupId>io.elmos.fixtures</groupId><artifactId>legacy-spring-mvc-boot</artifactId><version>1.0.0</version><packaging>war</packaging>
  <properties><java.version>{TARGET_JAVA}</java.version><maven.compiler.release>{TARGET_JAVA}</maven.compiler.release><spring-boot.version>{TARGET_BOOT}</spring-boot.version></properties>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-actuator</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-tomcat</artifactId><scope>provided</scope></dependency>
    <dependency><groupId>org.apache.tomcat.embed</groupId><artifactId>tomcat-embed-jasper</artifactId><scope>provided</scope></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-test</artifactId><scope>test</scope></dependency>
  </dependencies>
  <build><finalName>legacy-spring-mvc-boot</finalName><plugins>
    <plugin><groupId>org.springframework.boot</groupId><artifactId>spring-boot-maven-plugin</artifactId><version>{TARGET_BOOT}</version><configuration><mainClass>io.elmos.legacy.LegacyMvcApplication</mainClass></configuration><executions><execution><goals><goal>repackage</goal></goals></execution></executions></plugin>
    <plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-war-plugin</artifactId><version>3.4.0</version><configuration><failOnMissingWebXml>false</failOnMissingWebXml></configuration></plugin>
  </plugins></build>
</project>
'''

APPLICATION = '''package io.elmos.legacy;

import io.elmos.legacy.boot.LegacyMvcConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = {"io.elmos.legacy.service", "io.elmos.legacy.web"})
@Import(LegacyMvcConfiguration.class)
public class LegacyMvcApplication extends SpringBootServletInitializer {
    public static void main(String[] args) { SpringApplication.run(LegacyMvcApplication.class, args); }
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) { return application.sources(LegacyMvcApplication.class); }
}
'''

CONFIGURATION = '''package io.elmos.legacy.boot;

import io.elmos.legacy.web.RequestAuditInterceptor;
import jakarta.servlet.DispatcherType;
import java.util.EnumSet;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.validation.Validator;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.filter.CharacterEncodingFilter;
import org.springframework.web.servlet.config.annotation.DefaultServletHandlerConfigurer;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.view.InternalResourceViewResolver;

@Configuration
public class LegacyMvcConfiguration implements WebMvcConfigurer {
    @Bean(name = "validator") public LocalValidatorFactoryBean validator() { return new LocalValidatorFactoryBean(); }
    @Override public Validator getValidator() { return validator(); }
    @Bean public RequestAuditInterceptor requestAuditInterceptor() { return new RequestAuditInterceptor(); }
    @Override public void addInterceptors(InterceptorRegistry registry) { registry.addInterceptor(requestAuditInterceptor()).addPathPatterns("/api/**"); }
    @Override public void configureDefaultServletHandling(DefaultServletHandlerConfigurer configurer) { configurer.enable(); }
    @Override public void addResourceHandlers(ResourceHandlerRegistry registry) { registry.addResourceHandler("/assets/**").addResourceLocations("/assets/").setCachePeriod(3600); }
    @Bean public InternalResourceViewResolver internalResourceViewResolver() {
        InternalResourceViewResolver resolver = new InternalResourceViewResolver();
        resolver.setPrefix("/WEB-INF/views/"); resolver.setSuffix(".jsp"); resolver.setOrder(10); return resolver;
    }
    @Bean public FilterRegistrationBean<CharacterEncodingFilter> characterEncodingFilter() {
        CharacterEncodingFilter filter = new CharacterEncodingFilter(); filter.setEncoding("UTF-8"); filter.setForceEncoding(true);
        FilterRegistrationBean<CharacterEncodingFilter> registration = new FilterRegistrationBean<>(filter);
        registration.setName("characterEncodingFilter"); registration.setUrlPatterns(java.util.List.of("/*"));
        registration.setDispatcherTypes(EnumSet.of(DispatcherType.REQUEST, DispatcherType.ERROR));
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE); return registration;
    }
}
'''

BOOT_PROPERTIES = '''server.servlet.encoding.enabled=false
server.servlet.register-default-servlet=true
server.shutdown=graceful
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
'''

BOOT_TEST = '''package io.elmos.legacy;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LegacyMvcApplicationTest {
    @Autowired MockMvc mvc;
    @Test void bootsWithApiInterceptor() throws Exception {
        mvc.perform(get("/api/orders/42")).andExpect(status().isOk()).andExpect(header().string("X-Legacy-Audit", "GET /api/orders/42")).andExpect(jsonPath("$.currency").value("CNY"));
    }
    @Test void keepsJspRouteOutsideApiInterceptor() throws Exception {
        mvc.perform(get("/orders")).andExpect(status().isOk()).andExpect(view().name("orders/list")).andExpect(header().doesNotExist("X-Legacy-Audit"));
    }
    @Test void exposesOnlyHealthOutsideApiInterceptor() throws Exception {
        mvc.perform(get("/actuator/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("UP")).andExpect(header().doesNotExist("X-Legacy-Audit"));
        mvc.perform(get("/actuator/env")).andExpect(status().isNotFound()).andExpect(header().doesNotExist("X-Legacy-Audit"));
    }
}
'''


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_and_migrate_java(source_root: Path, target_root: Path) -> list[dict[str, str]]:
    source_map: list[dict[str, str]] = []
    for kind in ("main", "test"):
        base = source_root / "src" / kind / "java"
        if not base.exists():
            continue
        for source_file in sorted(base.rglob("*.java")):
            relative = source_file.relative_to(source_root)
            target_file = target_root / relative
            text = source_file.read_text(encoding="utf-8")
            migrated = text.replace("javax.validation", "jakarta.validation").replace("javax.servlet", "jakarta.servlet")
            write_text(target_file, migrated)
            source_map.append({"source": relative.as_posix(), "target": relative.as_posix(), "source_sha256": sha256(source_file), "mapping": "copy-with-exact-javax-validation-and-servlet-namespace-migration"})
    return source_map


def materialize(source: Path, output: Path) -> None:
    validate_source(source)
    require(not output.exists(), f"output already exists; refusing to overwrite: {output}")
    output.mkdir(parents=True)
    source_map = copy_and_migrate_java(source, output)
    shutil.copytree(source / "src/main/webapp/WEB-INF/views", output / "src/main/webapp/WEB-INF/views")
    assets = source / "src/main/webapp/assets"
    if assets.exists():
        shutil.copytree(assets, output / "src/main/webapp/assets")
    write_text(output / "pom.xml", POM)
    write_text(output / "src/main/java/io/elmos/legacy/LegacyMvcApplication.java", APPLICATION)
    write_text(output / "src/main/java/io/elmos/legacy/boot/LegacyMvcConfiguration.java", CONFIGURATION)
    legacy_properties = (source / "src/main/resources/legacy.properties").read_text(encoding="utf-8").rstrip()
    write_text(output / "src/main/resources/application.properties", legacy_properties + "\n" + BOOT_PROPERTIES)
    write_text(output / "src/test/java/io/elmos/legacy/LegacyMvcApplicationTest.java", BOOT_TEST)
    source_inputs = [source / "pom.xml", source / "src/main/webapp/WEB-INF/web.xml", source / "src/main/resources/WEB-INF/spring/root-context.xml", source / "src/main/resources/WEB-INF/spring/servlet-context.xml", source / "src/main/resources/legacy.properties"]
    pack_root = Path(__file__).resolve().parents[2]
    recipe_path = pack_root / "recipes/spring-framework-5.3-mvc-to-spring-boot-3.5.3.yml"
    profile_path = pack_root / "target-profile/profile.json"
    receipt = {
        "schema_version": 1, "pack_key": PACK_KEY, "status": "MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED",
        "generator_binding": {
            "emitter_sha256": sha256(Path(__file__).resolve()),
            "recipe_sha256": sha256(recipe_path),
            "target_profile_sha256": sha256(profile_path),
        },
        "exact_tuple": {
            "source": {"spring_framework": SOURCE_FRAMEWORK, "java": SOURCE_JAVA, "maven": MAVEN_VERSION, "packaging": "war"},
            "target": {"spring_boot": TARGET_BOOT, "java": TARGET_JAVA, "maven": MAVEN_VERSION, "packaging": "executable-war"},
        },
        "source_inputs": [{"path": item.relative_to(source).as_posix(), "sha256": sha256(item)} for item in source_inputs],
        "retired_from_target": [
            {"path": "src/main/webapp/WEB-INF/web.xml", "replacement": "LegacyMvcApplication plus LegacyMvcConfiguration"},
            {"path": "src/main/resources/WEB-INF/spring/root-context.xml", "replacement": "Boot component scan and application.properties"},
            {"path": "src/main/resources/WEB-INF/spring/servlet-context.xml", "replacement": "LegacyMvcConfiguration"},
        ],
        "preserved_contracts": ["DispatcherServlet / through Boot MVC", "UTF-8 CharacterEncodingFilter REQUEST and ERROR dispatch", "service and web component scanning", "fail-fast legacy.orders.currency property resolution", "Jakarta Validation and ControllerAdvice error shape", "RequestAuditInterceptor /api/** mapping", "JSP /WEB-INF/views prefix and .jsp suffix at order 10", "static /assets/** mapping with 3600 second cache", "default servlet fallback", "Actuator health-only exposure", "Boot main and SpringBootServletInitializer executable WAR entry points"],
        "execution": {"source_build": "NOT_RUN", "source_startup": "NOT_RUN", "target_build": "NOT_RUN", "target_startup": "NOT_RUN", "behavior_equivalence": "NOT_RUN"},
    }
    write_text(output / ".elmos/migration-receipt.json", json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    write_text(output / ".elmos/source-map.json", json.dumps({"schema_version": 1, "mappings": source_map}, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        materialize(args.source.resolve(), args.output.resolve())
    except UnsupportedSource as exc:
        print(f"BLOCKED_UNSUPPORTED_SOURCE: {exc}", file=sys.stderr)
        return 2
    print(f"MATERIALIZED_STATIC_NOT_RUNTIME_VERIFIED: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
