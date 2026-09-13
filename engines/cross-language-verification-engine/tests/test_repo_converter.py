import pytest
from elmos_cross_language_verification.repo_converter import (
    RepoProjectConverter, JavaClassInfo, JavaField, JavaMethod
)
from elmos_cross_language_verification.models import Language

SAMPLE_JAVA_ENTITY = """
package com.example.model;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    private String name;
    private String email;

    public Customer() {
    }

    public Customer(Long id, String name, String email) {
        this.id = id;
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
"""

SAMPLE_JAVA_INTERFACE = """
package com.example.service;

public interface OrderProcessor {
    void processOrder(String orderId);
    boolean validateOrder(String orderId);
}
"""

def test_parse_java_class():
    converter = RepoProjectConverter()
    classes = converter.parse_java_file(SAMPLE_JAVA_ENTITY, "Customer.java")
    assert len(classes) == 1
    c = classes[0]
    assert c.name == "Customer"
    assert c.package == "com.example.model"
    assert not c.is_interface
    assert len(c.fields) == 3
    assert c.fields[0].name == "id"
    assert c.fields[0].is_id
    assert c.fields[1].name == "name"
    assert len(c.methods) == 4

def test_convert_to_typescript():
    converter = RepoProjectConverter()
    classes = converter.parse_java_file(SAMPLE_JAVA_ENTITY, "Customer.java")
    ts_files = converter._convert_to_typescript(classes, "shop-app")
    
    assert "package.json" in ts_files
    assert "tsconfig.json" in ts_files
    assert "src/com/example/model/Customer.ts" in ts_files
    
    ts_code = ts_files["src/com/example/model/Customer.ts"]
    assert "export class Customer" in ts_code
    assert "@PrimaryGeneratedColumn()" in ts_code
    assert "id: number;" in ts_code
    assert "name?: string;" in ts_code
    assert "getName(): string" in ts_code

def test_convert_to_csharp():
    converter = RepoProjectConverter()
    classes = converter.parse_java_file(SAMPLE_JAVA_ENTITY, "Customer.java")
    cs_files = converter._convert_to_csharp(classes, "ShopApp")
    
    assert "ShopApp.csproj" in cs_files
    assert "com/example/model/Customer.cs" in cs_files
    
    cs_code = cs_files["com/example/model/Customer.cs"]
    assert "public class Customer" in cs_code
    assert "public long Id { get; set; }" in cs_code
    assert "public string Name { get; set; }" in cs_code
    assert "public string GetName()" in cs_code

def test_convert_to_python():
    converter = RepoProjectConverter()
    classes = converter.parse_java_file(SAMPLE_JAVA_ENTITY, "Customer.java")
    py_files = converter._convert_to_python(classes, "shop-app")
    
    assert "pyproject.toml" in py_files
    assert "com/example/model/customer.py" in py_files
    
    py_code = py_files["com/example/model/customer.py"]
    assert "class Customer:" in py_code
    assert "id: int" in py_code
    assert "name: Optional[str] = None" in py_code
    assert "def getName(self) -> str:" in py_code

def test_convert_interface_to_csharp():
    converter = RepoProjectConverter()
    classes = converter.parse_java_file(SAMPLE_JAVA_INTERFACE, "OrderProcessor.java")
    cs_files = converter._convert_to_csharp(classes, "ShopApp")
    
    cs_code = cs_files["com/example/service/OrderProcessor.cs"]
    assert "public interface IOrderProcessor" in cs_code
    assert "void ProcessOrder(string orderId)" in cs_code
    assert "bool ValidateOrder(string orderId)" in cs_code
