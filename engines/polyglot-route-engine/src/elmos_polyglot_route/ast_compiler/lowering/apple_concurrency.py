"""Apple Concurrency Lowering: Bridges Swift async/await, ObjC GCD blocks, and reactive Task."""

from __future__ import annotations

from ..ir import UniversalAnnotation, UniversalModule


class AppleConcurrencyLowering:
    """Aligns Swift modern Concurrency and Objective-C GCD block callbacks with standard async models."""

    @classmethod
    def lower_module(cls, module: UniversalModule, source_lang: str, target_lang: str) -> UniversalModule:
        t_lang = target_lang.lower().strip()

        for u_class in module.classes:
            for m in u_class.methods:
                # If target is Swift and method is async, ensure proper async/await
                if t_lang == "swift" and m.is_async:
                    m.is_async = True
                # If target is Objective-C and method was async, adapt to completion handler pattern
                elif t_lang in ("objc", "objective-c") and m.is_async:
                    m.is_async = False
                    # Retain the adaptation in the typed annotation surface.
                    if not any(annotation.name == "ObjCAsyncBlock" for annotation in m.annotations):
                        m.annotations.append(UniversalAnnotation(name="ObjCAsyncBlock"))

        return module
