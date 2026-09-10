"""Framework & Web API routing lowering across 8 languages."""

from __future__ import annotations

from ..ir import UniversalAnnotation, UniversalClass, UniversalMethod, UniversalModule


class FrameworkLowering:
    """Maps REST controllers, routing annotations, and parameters across web frameworks."""

    @classmethod
    def lower_module(cls, module: UniversalModule, target_language: str) -> UniversalModule:
        target = target_language.lower().strip()
        for c in module.classes:
            cls.lower_class(c, target)
        return module

    @classmethod
    def lower_class(cls, c: UniversalClass, target_language: str) -> None:
        if not c.is_controller and not any('controller' in a.name.lower() or 'router' in a.name.lower() for a in c.annotations):
            return

        c.is_controller = True
        base = c.base_route or ('/api/v1/' + c.name.lower().replace('controller', '').replace('service', ''))
        c.base_route = base

        # Generate framework-specific controller annotations
        c.annotations.clear()
        if target_language == 'java':
            c.annotations.append(UniversalAnnotation(name='RestController'))
            c.annotations.append(UniversalAnnotation(name='RequestMapping', args=[base]))
        elif target_language == 'csharp':
            c.annotations.append(UniversalAnnotation(name='ApiController'))
            c.annotations.append(UniversalAnnotation(name='Route', args=[base.lstrip('/')]))
        elif target_language == 'typescript':
            c.annotations.append(UniversalAnnotation(name='Controller', args=[base.lstrip('/')]))
        elif target_language == 'python':
            c.annotations.append(UniversalAnnotation(name='APIRouter', args=[base]))
        elif target_language == 'kotlin':
            c.annotations.append(UniversalAnnotation(name='RestController'))
            c.annotations.append(UniversalAnnotation(name='RequestMapping', args=[base]))

        # Method annotations
        for m in c.methods:
            if not m.http_method:
                # Infer from name
                if 'get' in m.name.lower():
                    m.http_method = 'GET'
                    m.http_path = '/{serial}' if m.params else ''
                elif 'create' in m.name.lower() or 'post' in m.name.lower():
                    m.http_method = 'POST'
                    m.http_path = ''
                elif 'update' in m.name.lower() or 'put' in m.name.lower():
                    m.http_method = 'PUT'
                    m.http_path = '/{serial}' if m.params else ''
                elif 'delete' in m.name.lower():
                    m.http_method = 'DELETE'
                    m.http_path = '/{serial}' if m.params else ''
