import os

with open("engines/mature-platform-engine/src/elmos_mature_platform/types.py", "a") as f:
    f.write("""

# ─── Knowledge Isolation Models ──────────────────────────────────────

class KnowledgeBoundary(str, Enum):
    TENANT = "tenant"
    PROJECT = "project"
    TEAM = "team"
    PUBLIC = "public"
    SHARED = "shared"

class KnowledgeAccessLevel(str, Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

@dataclass
class KnowledgePartition:
    partition_id: str
    name: str
    boundary: KnowledgeBoundary
    owner: str = ""  # tenant_id, project_id, team_id
    item_count: int = 0
    size_bytes: int = 0
    created_at: str = ""
    encrypted: bool = False
    retention_days: int = 365

@dataclass
class KnowledgeAccessGrant:
    grant_id: str
    partition_id: str
    principal: str  # user_id, team_id, service_account
    access_level: KnowledgeAccessLevel
    granted_by: str = ""
    granted_at: str = ""
    expires_at: str = ""
    revoked: bool = False
""")
