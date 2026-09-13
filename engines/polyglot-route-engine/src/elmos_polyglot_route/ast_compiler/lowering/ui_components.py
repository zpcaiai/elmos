"""UI Component Lowering: Bridges React, Flutter, VB6 Form, and Headless Backend Services."""

from __future__ import annotations

from typing import Any
from ..ir import (
    UniversalModule, UniversalClass, UniversalField, UniversalMethod, UniversalParam,
    UniversalType, UniversalStmt, ReturnStmt, RawSnippetStmt, LiteralExpr,
    UIComponentDecl, UIStateVar, UIViewNode, UIEventBinding
)


class UIComponentLowering:
    """Translates UI components between declarative frameworks, desktop forms, and backend services."""

    UI_LANGUAGES = {"react", "flutter", "dart", "swift", "vb6"}

    @classmethod
    def lower_module(cls, module: UniversalModule, source_lang: str, target_lang: str) -> UniversalModule:
        s_lang = source_lang.lower().strip()
        t_lang = target_lang.lower().strip()

        # Case 1: Source has UI components, Target is a headless backend language (Java, C#, Go, Python, Rust, etc.)
        if module.ui_components and t_lang not in cls.UI_LANGUAGES:
            for ui_comp in module.ui_components:
                # Convert UI component into a headless Service/ViewModel class
                cls_name = f"{ui_comp.name}ViewModel" if not ui_comp.name.endswith("ViewModel") else ui_comp.name
                backend_cls = UniversalClass(name=cls_name)

                # Convert Props & StateVars into Fields
                for prop in ui_comp.props:
                    backend_cls.fields.append(UniversalField(
                        name=prop.name,
                        type_info=prop.type_info,
                        is_readonly=True
                    ))
                for state in ui_comp.state_vars:
                    backend_cls.fields.append(UniversalField(
                        name=state.name,
                        type_info=state.type_info,
                        default_value=state.initial_value
                    ))

                # Convert methods and event handlers into business methods
                for m in ui_comp.methods:
                    backend_cls.methods.append(m)

                if ui_comp.root_view:
                    for evt in ui_comp.root_view.events:
                        if not any(m.name == evt.handler_method_name for m in backend_cls.methods):
                            handler = UniversalMethod(
                                name=evt.handler_method_name,
                                return_type=UniversalType.void(),
                                body=evt.inline_statements if evt.inline_statements else [RawSnippetStmt(code="// Handle event")]
                            )
                            backend_cls.methods.append(handler)

                module.classes.append(backend_cls)

        # Case 2: Source is Backend, Target is UI (React/Flutter/VB6)
        elif not module.ui_components and t_lang in cls.UI_LANGUAGES and module.classes:
            for u_cls in module.classes:
                comp_name = u_cls.name.replace("Service", "View").replace("Controller", "Card")
                ui_comp = UIComponentDecl(name=comp_name, is_stateful=True)
                for f in u_cls.fields:
                    ui_comp.state_vars.append(UIStateVar(
                        name=f.name,
                        type_info=f.type_info,
                        initial_value=f.default_value
                    ))
                ui_comp.root_view = UIViewNode(
                    tag="Container",
                    text_content=f"{comp_name} Component"
                )
                module.ui_components.append(ui_comp)

        return module
