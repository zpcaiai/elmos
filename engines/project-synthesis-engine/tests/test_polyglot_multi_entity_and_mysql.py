"""Tests for Polyglot Multi-Entity Domain Models, Canonical Relations, and MySQL 8.x Persistence.

Verifies:
1. Multi-entity domain model and foreign key generation across Go, TypeScript, C#, Java, Rust, PHP, and Kotlin.
2. Accurate parsing of request.canonical_relations into foreign keys, navigation properties, and associations.
3. Native MySQL 8.x drivers, connection strings, and dialects emitted across polyglot targets without PostgreSQL lock-in.
"""

from __future__ import annotations

import pytest

from elmos_project_synthesis.enterprise_dotnet_target import generate_enterprise_dotnet_files
from elmos_project_synthesis.enterprise_go_target import generate_enterprise_go_files
from elmos_project_synthesis.enterprise_java_target import generate_enterprise_java_files
from elmos_project_synthesis.enterprise_polyglot_targets import (
    generate_enterprise_kotlin_files,
    generate_enterprise_php_files,
    generate_enterprise_rust_files,
)
from elmos_project_synthesis.enterprise_typescript_target import generate_enterprise_typescript_files
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.models import SynthesisRequest


def _allow_crud(*resources: str) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "actor": "admin",
            "action": action,
            "resource": resource,
            "effect": "allow",
        }
        for resource in resources
        for action in ("create", "read", "update", "delete")
    )


def _make_multi_entity_request(is_mysql: bool = False, language: str = "go") -> SynthesisRequest:
    draft = create_draft(
        name="polyglot-ecommerce",
        description="Polyglot multi-entity store application",
        entities=(
            {
                "singular": "order",
                "plural": "orders",
                "fields": [
                    {"name": "reference", "type": "string", "required": True},
                    {"name": "total_amount", "type": "number", "required": True},
                ],
            },
            {
                "singular": "order_item",
                "plural": "order_items",
                "fields": [
                    {"name": "order_id", "type": "string", "required": True},
                    {"name": "product_name", "type": "string", "required": True},
                    {"name": "quantity", "type": "integer", "required": True},
                    {"name": "unit_price", "type": "number", "required": True},
                ],
            },
        ),
        relations=(
            {
                "source": "order_item",
                "target": "order",
                "source_field": "order_id",
                "target_field": "id",
                "kind": "many-to-one",
                "required": True,
            },
        ),
        languages=(language,),
        persistence="mysql" if is_mysql else "postgresql",
        auth_mode="jwt",
        permissions=_allow_crud("order", "order_item"),
    )
    approved = approve_request(draft, actor="user:admin")
    return SynthesisRequest.from_mapping(approved)


def test_go_target_multi_entity_and_mysql():
    # PostgreSQL request
    req_pg = _make_multi_entity_request(is_mysql=False, language="go")
    files_pg = generate_enterprise_go_files(req_pg)

    models_go = files_pg["models/models.go"]
    assert "type Order struct" in models_go
    assert "type OrderItem struct" in models_go
    assert "OrderId" in models_go
    assert "Order *Order" in models_go
    assert "OrderItems []OrderItem" in models_go
    assert "gorm.io/driver/postgres" in files_pg["go.mod"]

    main_go = files_pg["main.go"]
    assert "&models.Order{}" in main_go
    assert "&models.OrderItem{}" in main_go

    # MySQL request
    req_mysql = _make_multi_entity_request(is_mysql=True, language="go")
    files_mysql = generate_enterprise_go_files(req_mysql)
    assert "gorm.io/driver/mysql" in files_mysql["go.mod"]
    assert "gorm.io/driver/mysql" in files_mysql["main.go"]


def test_typescript_target_multi_entity_and_mysql():
    req_pg = _make_multi_entity_request(is_mysql=False, language="typescript")
    files_pg = generate_enterprise_typescript_files(req_pg)

    assert "src/entities/order.entity.ts" in files_pg
    assert "src/entities/order_item.entity.ts" in files_pg

    order_entity_ts = files_pg["src/entities/order.entity.ts"]
    item_entity_ts = files_pg["src/entities/order_item.entity.ts"]

    assert "export class OrderEntity" in order_entity_ts
    assert "export class OrderItemEntity" in item_entity_ts
    assert "@ManyToOne(() => OrderEntity" in item_entity_ts
    assert "@OneToMany(() => OrderItemEntity" in order_entity_ts

    app_module_ts = files_pg["src/app.module.ts"]
    assert "OrderEntity" in app_module_ts
    assert "OrderItemEntity" in app_module_ts
    assert "type: 'postgres'" in app_module_ts

    # MySQL request
    req_mysql = _make_multi_entity_request(is_mysql=True, language="typescript")
    files_mysql = generate_enterprise_typescript_files(req_mysql)
    assert '"mysql2"' in files_mysql["package.json"]
    assert "type: 'mysql'" in files_mysql["src/app.module.ts"]


def test_dotnet_target_multi_entity_and_mysql():
    req_pg = _make_multi_entity_request(is_mysql=False, language="csharp")
    files_pg = generate_enterprise_dotnet_files(req_pg)

    entities_cs = files_pg["Models/Entities.cs"]
    assert "public class Order : AuditEntity" in entities_cs
    assert "public class OrderItem : AuditEntity" in entities_cs
    assert "public string OrderId" in entities_cs
    assert "public virtual Order? Order" in entities_cs
    assert "public virtual ICollection<OrderItem> OrderItems" in entities_cs

    dbcontext_cs = files_pg["Data/AppDbContext.cs"]
    assert "public DbSet<Order> Orders" in dbcontext_cs
    assert "public DbSet<OrderItem> OrderItems" in dbcontext_cs

    assert "Npgsql.EntityFrameworkCore.PostgreSQL" in files_pg["PolyglotEcommerce.csproj"]

    # MySQL request
    req_mysql = _make_multi_entity_request(is_mysql=True, language="csharp")
    files_mysql = generate_enterprise_dotnet_files(req_mysql)
    assert "Pomelo.EntityFrameworkCore.MySql" in files_mysql["PolyglotEcommerce.csproj"]
    assert "opt.UseMySql" in files_mysql["Program.cs"]
    assert '"MySQL"' in files_mysql["appsettings.json"]


def test_java_target_multi_entity_and_mysql():
    req_pg = _make_multi_entity_request(is_mysql=False, language="java")
    files_pg = generate_enterprise_java_files(req_pg)

    pkg_path = req_pg.namespace.replace(".", "/")
    assert f"src/main/java/{pkg_path}/model/OrderEntity.java" in files_pg
    assert f"src/main/java/{pkg_path}/model/OrderItemEntity.java" in files_pg

    order_java = files_pg[f"src/main/java/{pkg_path}/model/OrderEntity.java"]
    item_java = files_pg[f"src/main/java/{pkg_path}/model/OrderItemEntity.java"]

    assert "@OneToMany(mappedBy = \"order\"" in order_java
    assert "@ManyToOne(fetch = FetchType.LAZY)" in item_java
    assert "postgresql" in files_pg["pom.xml"]

    # MySQL request
    req_mysql = _make_multi_entity_request(is_mysql=True, language="java")
    files_mysql = generate_enterprise_java_files(req_mysql)
    assert "mysql-connector-j" in files_mysql["pom.xml"]
    assert "com.mysql.cj.jdbc.Driver" in files_mysql["src/main/resources/application.yml"]
    assert "jdbc:mysql:" in files_mysql["src/main/resources/application.yml"]


def test_rust_target_multi_entity():
    req_pg = _make_multi_entity_request(is_mysql=False, language="rust")
    files_pg = generate_enterprise_rust_files(req_pg)

    models_rs = files_pg["src/models.rs"]
    assert "pub struct Order" in models_rs
    assert "pub struct OrderItem" in models_rs
    assert "pub order_id: String" in models_rs
    assert '"postgres"' in files_pg["Cargo.toml"]


def test_php_target_multi_entity():
    req = _make_multi_entity_request(is_mysql=False, language="php")
    files = generate_enterprise_php_files(req)

    assert "app/Models/Order.php" in files
    assert "app/Models/OrderItem.php" in files

    order_php = files["app/Models/Order.php"]
    item_php = files["app/Models/OrderItem.php"]

    assert "public function order_items()" in order_php
    assert "hasMany(OrderItem::class" in order_php
    assert "public function order()" in item_php
    assert "belongsTo(Order::class" in item_php


def test_kotlin_target_multi_entity():
    req_pg = _make_multi_entity_request(is_mysql=False, language="kotlin")
    files_pg = generate_enterprise_kotlin_files(req_pg)

    pkg_path = req_pg.namespace.replace(".", "/")
    assert "org.postgresql:postgresql" in files_pg["build.gradle.kts"]
    assert f"src/main/java/{pkg_path}/model/OrderEntity.java" in files_pg
    assert f"src/main/java/{pkg_path}/model/OrderItemEntity.java" in files_pg
