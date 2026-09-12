import uuid
import datetime
from typing import Dict, List, Optional
from .types import (
    EventSchemaVersion,
    EvolutionSchemaChange as SchemaChange,
    EventSchemaChangeType as SchemaChangeType,
    SchemaCompatResult
)

class EventSchemaCompatibilityEngine:
    def __init__(self):
        self._schemas: Dict[str, EventSchemaVersion] = {}
        # index by event_type
        self._event_type_schemas: Dict[str, List[str]] = {}

    def register_schema(self, schema: EventSchemaVersion) -> str:
        """Registers a new schema version."""
        if schema.schema_id in self._schemas:
            raise ValueError(f"Schema {schema.schema_id} already exists")
            
        if not schema.registered_at:
            schema.registered_at = datetime.datetime.utcnow().isoformat()
            
        self._schemas[schema.schema_id] = schema
        
        if schema.event_type not in self._event_type_schemas:
            self._event_type_schemas[schema.event_type] = []
        self._event_type_schemas[schema.event_type].append(schema.schema_id)
        
        return schema.schema_id

    def deprecate_schema(self, schema_id: str) -> EventSchemaVersion:
        """Marks a schema as deprecated."""
        if schema_id not in self._schemas:
            raise ValueError(f"Schema {schema_id} not found")
        schema = self._schemas[schema_id]
        schema.deprecated = True
        return schema

    def diff_schemas(self, schema_id_a: str, schema_id_b: str) -> List[SchemaChange]:
        """Computes differences between two schemas (a -> b)."""
        if schema_id_a not in self._schemas or schema_id_b not in self._schemas:
            raise ValueError("Schema not found")
            
        schema_a = self._schemas[schema_id_a]
        schema_b = self._schemas[schema_id_b]
        
        changes = []
        
        # Fields added/removed/type changed
        for field, t_type in schema_b.fields.items():
            if field not in schema_a.fields:
                changes.append(SchemaChange(
                    change_id=str(uuid.uuid4()),
                    schema_id=schema_b.schema_id,
                    change_type=SchemaChangeType.FIELD_ADDED,
                    field_name=field,
                    new_value=t_type,
                    breaking=False
                ))
            elif schema_a.fields[field] != t_type:
                changes.append(SchemaChange(
                    change_id=str(uuid.uuid4()),
                    schema_id=schema_b.schema_id,
                    change_type=SchemaChangeType.TYPE_CHANGED,
                    field_name=field,
                    old_value=schema_a.fields[field],
                    new_value=t_type,
                    breaking=True
                ))
                
        for field, t_type in schema_a.fields.items():
            if field not in schema_b.fields:
                changes.append(SchemaChange(
                    change_id=str(uuid.uuid4()),
                    schema_id=schema_b.schema_id,
                    change_type=SchemaChangeType.FIELD_REMOVED,
                    field_name=field,
                    old_value=t_type,
                    breaking=True if field in schema_a.required_fields else False
                ))
                
        # Required added/removed
        for field in schema_b.required_fields:
            if field not in schema_a.required_fields and field in schema_a.fields:
                # Required added for existing field
                changes.append(SchemaChange(
                    change_id=str(uuid.uuid4()),
                    schema_id=schema_b.schema_id,
                    change_type=SchemaChangeType.REQUIRED_ADDED,
                    field_name=field,
                    breaking=True
                ))
            elif field not in schema_a.required_fields and field not in schema_a.fields:
                # Required added for a newly added field
                changes.append(SchemaChange(
                    change_id=str(uuid.uuid4()),
                    schema_id=schema_b.schema_id,
                    change_type=SchemaChangeType.REQUIRED_ADDED,
                    field_name=field,
                    breaking=True
                ))
                
        for field in schema_a.required_fields:
            if field not in schema_b.required_fields and field in schema_b.fields:
                changes.append(SchemaChange(
                    change_id=str(uuid.uuid4()),
                    schema_id=schema_b.schema_id,
                    change_type=SchemaChangeType.REQUIRED_REMOVED,
                    field_name=field,
                    breaking=False
                ))
                
        # Enum added/removed
        for field, b_values in schema_b.enum_fields.items():
            a_values = schema_a.enum_fields.get(field, [])
            for val in b_values:
                if val not in a_values:
                    changes.append(SchemaChange(
                        change_id=str(uuid.uuid4()),
                        schema_id=schema_b.schema_id,
                        change_type=SchemaChangeType.ENUM_VALUE_ADDED,
                        field_name=field,
                        new_value=val,
                        breaking=False
                    ))
                    
        for field, a_values in schema_a.enum_fields.items():
            b_values = schema_b.enum_fields.get(field, [])
            if field in schema_b.fields:
                for val in a_values:
                    if val not in b_values:
                        changes.append(SchemaChange(
                            change_id=str(uuid.uuid4()),
                            schema_id=schema_b.schema_id,
                            change_type=SchemaChangeType.ENUM_VALUE_REMOVED,
                            field_name=field,
                            old_value=val,
                            breaking=True
                        ))
                        
        return changes

    def check_compatibility(self, schema_id_a: str, schema_id_b: str) -> SchemaCompatResult:
        """Determines compatibility result from a -> b."""
        if schema_id_a not in self._schemas or schema_id_b not in self._schemas:
            return SchemaCompatResult.UNKNOWN
            
        if schema_id_a == schema_id_b:
            return SchemaCompatResult.FULLY_COMPATIBLE

        changes = self.diff_schemas(schema_id_a, schema_id_b)
        
        if not changes:
            return SchemaCompatResult.FULLY_COMPATIBLE
            
        has_breaking = any(c.breaking for c in changes)
        if has_breaking:
            return SchemaCompatResult.BREAKING
            
        # No breaking changes. Check if we added fields (backward compatible)
        # or removed optional fields (forward compatible)
        added = any(c.change_type in (SchemaChangeType.FIELD_ADDED, SchemaChangeType.ENUM_VALUE_ADDED) for c in changes)
        removed_optional = any(c.change_type == SchemaChangeType.FIELD_REMOVED and not c.breaking for c in changes)
        
        if added and not removed_optional:
            return SchemaCompatResult.BACKWARD_COMPATIBLE
        if removed_optional and not added:
            return SchemaCompatResult.FORWARD_COMPATIBLE
            
        # Mixed non-breaking changes
        return SchemaCompatResult.BACKWARD_COMPATIBLE

    def get_schema_history(self, event_type: str) -> List[EventSchemaVersion]:
        """All versions for event type"""
        if event_type not in self._event_type_schemas:
            return []
        
        ids = self._event_type_schemas[event_type]
        schemas = [self._schemas[i] for i in ids]
        return sorted(schemas, key=lambda s: s.registered_at)

    def get_latest_schema(self, event_type: str) -> EventSchemaVersion:
        """Latest version"""
        history = self.get_schema_history(event_type)
        if not history:
            raise ValueError("No schemas found for event type")
        return history[-1]

    def validate_evolution(self, event_type: str) -> Dict:
        """Check entire history: any breaking changes?"""
        history = self.get_schema_history(event_type)
        if len(history) < 2:
            return {"valid": True, "breaking_changes": []}
            
        all_breaking = []
        for i in range(len(history) - 1):
            s_a = history[i].schema_id
            s_b = history[i+1].schema_id
            changes = self.diff_schemas(s_a, s_b)
            breaking = [c for c in changes if c.breaking]
            all_breaking.extend(breaking)
            
        return {
            "valid": len(all_breaking) == 0,
            "breaking_changes": all_breaking
        }

    def get_breaking_changes(self, event_type: str) -> List[SchemaChange]:
        """All breaking changes in history"""
        res = self.validate_evolution(event_type)
        return res["breaking_changes"]

    def get_consumers(self, event_type: str, version: str) -> int:
        """Simulated consumer count"""
        import hashlib
        key = f"{event_type}:{version}".encode("utf-8")
        h = int(hashlib.md5(key).hexdigest()[:8], 16)
        return (h % 100) + 1

    def get_compatibility_report(self) -> Dict:
        """Event types, total schemas, breaking changes, deprecated"""
        event_types = list(self._event_type_schemas.keys())
        total = len(self._schemas)
        breaking = 0
        deprecated = sum(1 for s in self._schemas.values() if s.deprecated)
        
        for et in event_types:
            breaking += len(self.get_breaking_changes(et))
            
        return {
            "event_types": len(event_types),
            "total_schemas": total,
            "breaking_changes": breaking,
            "deprecated": deprecated
        }
