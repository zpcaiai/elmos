from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional

class Language(Enum):
    JAVA = "JAVA"
    PYTHON = "PYTHON"
    TYPESCRIPT = "TYPESCRIPT"
    CSHARP = "CSHARP"
    GO = "GO"
    RUST = "RUST"
    KOTLIN = "KOTLIN"
    SWIFT = "SWIFT"
    RUBY = "RUBY"
    PHP = "PHP"
    DART = "DART"

class Framework(Enum):
    SPRING_BOOT = "SPRING_BOOT"
    DJANGO = "DJANGO"
    FASTAPI = "FASTAPI"
    FLASK = "FLASK"
    EXPRESS = "EXPRESS"
    NESTJS = "NESTJS"
    ASPNET = "ASPNET"
    GIN = "GIN"
    ACTIX = "ACTIX"
    RAILS = "RAILS"
    LARAVEL = "LARAVEL"
    FLUTTER = "FLUTTER"

class ProjectType(Enum):
    REST_API = "REST_API"
    GRAPHQL_API = "GRAPHQL_API"
    GRPC_SERVICE = "GRPC_SERVICE"
    WEB_APP = "WEB_APP"
    CLI_TOOL = "CLI_TOOL"
    LIBRARY = "LIBRARY"
    MICROSERVICE = "MICROSERVICE"
    MONOLITH = "MONOLITH"

class DatabaseType(Enum):
    POSTGRESQL = "POSTGRESQL"
    MYSQL = "MYSQL"
    SQLITE = "SQLITE"
    MONGODB = "MONGODB"
    REDIS = "REDIS"
    NONE = "NONE"

class FieldType(Enum):
    STRING = "STRING"
    INT = "INT"
    FLOAT = "FLOAT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    UUID = "UUID"
    DECIMAL = "DECIMAL"
    TEXT = "TEXT"
    BLOB = "BLOB"

class RelationshipType(Enum):
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"
    ONE_TO_ONE = "ONE_TO_ONE"

@dataclass
class FieldSpec:
    name: str
    type: FieldType
    required: bool = True
    unique: bool = False
    default_value: Optional[str] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None

@dataclass
class RelationshipSpec:
    name: str
    target_entity: str
    type: RelationshipType

@dataclass
class EntitySpec:
    name: str
    fields: List[FieldSpec] = field(default_factory=list)
    relationships: List[RelationshipSpec] = field(default_factory=list)

@dataclass
class EndpointSpec:
    method: str
    path: str
    description: str = ""
    request_body: Optional[EntitySpec] = None
    response_body: Optional[EntitySpec] = None
    auth_required: bool = False
    roles: List[str] = field(default_factory=list)

@dataclass
class ServiceSpec:
    name: str
    methods: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)

@dataclass
class DatabaseSpec:
    type: DatabaseType
    entities_to_persist: List[str] = field(default_factory=list)

@dataclass
class AuthSpec:
    type: str  # JWT/OAuth2/Basic/None
    roles: List[str] = field(default_factory=list)

@dataclass
class ConfigSpec:
    env_vars: List[str] = field(default_factory=list)
    ports: List[int] = field(default_factory=list)
    features: List[str] = field(default_factory=list)

@dataclass
class PSIR:
    project_name: str
    description: str
    language: Language
    framework: Framework
    project_type: ProjectType
    entities: List[EntitySpec] = field(default_factory=list)
    endpoints: List[EndpointSpec] = field(default_factory=list)
    services: List[ServiceSpec] = field(default_factory=list)
    database: Optional[DatabaseSpec] = None
    auth: Optional[AuthSpec] = None
    config: Optional[ConfigSpec] = None

@dataclass
class GeneratedProject:
    project_root: str
    files: Dict[str, str] = field(default_factory=dict)
    build_command: str = ""
    run_command: str = ""
    test_command: str = ""
