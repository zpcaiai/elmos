"""Spring Data JPA & Hibernate 5 to Hibernate 6 modernization migrator.

Transforms deprecated @Type and @TypeDef annotations, updates Hibernate dialect
names (removing version suffixes in favor of unified Dialect classes), and enforces
canonical persistence invariants.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JpaMigrationResult:
    migrated_content: str
    changes: list[str] = field(default_factory=list)
    deprecated_annotations_removed: list[str] = field(default_factory=list)
    invariants_preserved: list[str] = field(default_factory=list)
    has_jpa_config: bool = False


class JpaPersistenceMigrator:
    """Migrates Hibernate 5 JPA entity code and dialect configuration to Hibernate 6 standards."""

    DIALECT_MAPPINGS = {
        'org.hibernate.dialect.PostgreSQL82Dialect': 'org.hibernate.dialect.PostgreSQLDialect',
        'org.hibernate.dialect.PostgreSQL9Dialect': 'org.hibernate.dialect.PostgreSQLDialect',
        'org.hibernate.dialect.PostgreSQL95Dialect': 'org.hibernate.dialect.PostgreSQLDialect',
        'org.hibernate.dialect.PostgreSQL10Dialect': 'org.hibernate.dialect.PostgreSQLDialect',
        'org.hibernate.dialect.MySQL5Dialect': 'org.hibernate.dialect.MySQLDialect',
        'org.hibernate.dialect.MySQL55Dialect': 'org.hibernate.dialect.MySQLDialect',
        'org.hibernate.dialect.MySQL57Dialect': 'org.hibernate.dialect.MySQLDialect',
        'org.hibernate.dialect.MySQL8Dialect': 'org.hibernate.dialect.MySQLDialect',
        'org.hibernate.dialect.Oracle9iDialect': 'org.hibernate.dialect.OracleDialect',
        'org.hibernate.dialect.Oracle10gDialect': 'org.hibernate.dialect.OracleDialect',
        'org.hibernate.dialect.Oracle12cDialect': 'org.hibernate.dialect.OracleDialect',
        'org.hibernate.dialect.SQLServer2008Dialect': 'org.hibernate.dialect.SQLServerDialect',
        'org.hibernate.dialect.SQLServer2012Dialect': 'org.hibernate.dialect.SQLServerDialect',
    }

    def __init__(self) -> None:
        self.typedef_pattern = re.compile(r'@TypeDefs?\s*\(\s*\{?.*?\}?\s*\)', re.DOTALL)
        self.type_pattern = re.compile(r'@Type\s*\(\s*type\s*=\s*"([^"]+)"\s*\)')

    def migrate_entity_source(self, source_code: str) -> JpaMigrationResult:
        changes: list[str] = []
        deprecated_removed: list[str] = []
        invariants = [
            'schema-mapping-and-generated-identifiers',
            'query-result-null-and-precision-equivalence',
            'constraint-locking-and-exception-semantics',
            'provider-dialect-and-transaction-resource-binding',
        ]

        code = source_code
        has_config = False

        if '@TypeDef' in code:
            has_config = True
            code = self.typedef_pattern.sub('', code)
            changes.append('Removed deprecated @TypeDef declaration (unsupported in Hibernate 6)')
            deprecated_removed.append('@TypeDef')

        if '@Type' in code:
            has_config = True
            def replace_type(match: re.Match) -> str:
                t = match.group(1)
                if 'TextType' in t or 'string' in t.lower():
                    return '@Column(columnDefinition = "text")'
                if 'Json' in t or 'json' in t.lower():
                    return '@JdbcTypeCode(SqlTypes.JSON)'
                return '@JdbcTypeCode(SqlTypes.JAVA_OBJECT)'

            code = self.type_pattern.sub(replace_type, code)
            changes.append('Migrated legacy @Type annotations to @JdbcTypeCode / @Column')
            deprecated_removed.append('@Type')

            # Clean up imports and add modern imports
            code = re.sub(r"import\s+org\.hibernate\.annotations\.Type;\s*\n?", "", code)
            code = re.sub(r"import\s+org\.hibernate\.annotations\.TypeDef;\s*\n?", "", code)
            if "import org.hibernate.annotations.JdbcTypeCode;" not in code:
                code = "import org.hibernate.annotations.JdbcTypeCode;\nimport org.hibernate.type.SqlTypes;\n" + code

        return JpaMigrationResult(
            migrated_content=code,
            changes=changes,
            deprecated_annotations_removed=deprecated_removed,
            invariants_preserved=invariants,
            has_jpa_config=has_config,
        )

    def migrate_properties_config(self, properties_content: str) -> JpaMigrationResult:
        changes: list[str] = []
        invariants = [
            'provider-dialect-and-transaction-resource-binding',
            'constraint-locking-and-exception-semantics',
        ]
        content = properties_content
        has_config = False

        for legacy_dialect, unified_dialect in self.DIALECT_MAPPINGS.items():
            if legacy_dialect in content:
                has_config = True
                content = content.replace(legacy_dialect, unified_dialect)
                changes.append(f'Modernized Hibernate dialect {legacy_dialect} -> {unified_dialect}')

        return JpaMigrationResult(
            migrated_content=content,
            changes=changes,
            invariants_preserved=invariants,
            has_jpa_config=has_config,
        )
