"""Dynamic AST test case generator for differential fuzzing."""

from __future__ import annotations

import random
from typing import Optional
from ..ir import (
    PrimitiveKind,
    UniversalClass,
    UniversalField,
    UniversalMethod,
    UniversalModule,
    UniversalParam,
    UniversalType,
)


class AstFuzzGenerator:
    """Generates synthetic, structurally valid Universal AST modules for fuzz testing."""

    PRIMITIVES = [
        PrimitiveKind.I32,
        PrimitiveKind.I64,
        PrimitiveKind.F64,
        PrimitiveKind.BOOL,
        PrimitiveKind.STRING,
    ]

    FIELD_NAMES = ["serial", "status", "value", "count", "code", "tag", "timestamp", "payload"]
    CLASS_NAMES = ["Asset", "Customer", "Order", "Device", "Account", "Metric", "Entity"]

    def __init__(self, seed: Optional[int] = 42) -> None:
        self.rng = random.Random(seed)

    def generate_type(self, depth: int = 0) -> UniversalType:
        if depth > 1 or self.rng.random() < 0.7:
            p = self.rng.choice(self.PRIMITIVES)
            return UniversalType.primitive(p)
        r = self.rng.random()
        if r < 0.5:
            elem = self.generate_type(depth + 1)
            return UniversalType.list_of(elem)
        else:
            v = self.generate_type(depth + 1)
            return UniversalType.map_of(UniversalType.string_type(), v)

    def generate_field(self, name: Optional[str] = None) -> UniversalField:
        fname = name or self.rng.choice(self.FIELD_NAMES)
        ftype = self.generate_type()
        return UniversalField(name=fname, type_info=ftype)

    def generate_method(self, name: str, is_async: bool = False, http_method: Optional[str] = None) -> UniversalMethod:
        num_params = self.rng.randint(1, 3)
        params = [
            UniversalParam(name=f"param_{i}", type_info=self.generate_type())
            for i in range(num_params)
        ]
        return_type = self.generate_type()
        return UniversalMethod(
            name=name,
            params=params,
            return_type=return_type,
            is_async=is_async,
            http_method=http_method,
            http_path=f"/{{param_0}}" if http_method == "GET" else "",
            has_exception_handling=True,
        )

    def generate_class(self, name: Optional[str] = None, is_controller: bool = False) -> UniversalClass:
        cname = name or self.rng.choice(self.CLASS_NAMES)
        num_fields = self.rng.randint(2, 4)
        chosen_names = self.rng.sample(self.FIELD_NAMES, num_fields)
        fields = [self.generate_field(fname) for fname in chosen_names]

        methods = []
        if is_controller:
            methods.append(self.generate_method("get_entity_by_id", is_async=True, http_method="GET"))
            methods.append(self.generate_method("create_entity", is_async=True, http_method="POST"))
        else:
            methods.append(self.generate_method("compute_hash", is_async=False))

        return UniversalClass(
            name=cname,
            fields=fields,
            methods=methods,
            is_controller=is_controller,
            base_route=f"/api/v1/{cname.lower()}s" if is_controller else None,
        )

    def generate_module(self, name: str = "FuzzEnterpriseModule") -> UniversalModule:
        mod = UniversalModule(name=name)
        model_cls = self.generate_class("Asset", is_controller=False)
        ctrl_cls = self.generate_class("EnterpriseAssetController", is_controller=True)
        mod.classes.append(model_cls)
        mod.classes.append(ctrl_cls)
        return mod
