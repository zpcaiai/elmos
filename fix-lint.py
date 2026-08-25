#!/usr/bin/env python3
"""Fix the two ruff findings the merge surfaced.

Both are pre-existing on the perf side, not merge artefacts: the php target
tests and the reserved-name tests were added there and the lint gate had not
run over them yet. `[tool.ruff]` is byte-identical on both sides, so nothing
about the rules changed in the merge.

Run from the elmos-merge worktree:

    python3 ../elmos/fix-lint.py
"""
from pathlib import Path

# --- E501: one assertion message over the line limit -------------------------
p = Path("engines/polyglot-route-engine/tests/test_emitted_names_are_reserved.py")
text = p.read_text(encoding="utf-8")
old = '''        assert _reserved(language, call), f"{language} {operator} emits {call}, which the policy allows as a source name"
'''
new = '''        assert _reserved(language, call), (
            f"{language} {operator} emits {call}, which the policy allows as a source name"
        )
'''
assert text.count(old) == 1, f"E501 匹配 {text.count(old)} 次"
p.write_text(text.replace(old, new), encoding="utf-8")
print(f"  {p.name}: 断言信息换行")

# --- I001: function-local imports out of order -------------------------------
p = Path("engines/polyglot-route-engine/tests/test_php_target.py")
text = p.read_text(encoding="utf-8")
old = '''    import pytest

    from elmos_polyglot_route.models import RouteError
    from elmos_polyglot_route.native import _validated_module_inventory
    from pathlib import Path
    import tempfile
'''
new = '''    import tempfile
    from pathlib import Path

    import pytest

    from elmos_polyglot_route.models import RouteError
    from elmos_polyglot_route.native import _validated_module_inventory
'''
assert text.count(old) == 1, f"I001 匹配 {text.count(old)} 次"
p.write_text(text.replace(old, new), encoding="utf-8")
print(f"  {p.name}: 导入按 stdlib / 三方 / 本地 分组排序")

import ast
for f in ("engines/polyglot-route-engine/tests/test_emitted_names_are_reserved.py",
          "engines/polyglot-route-engine/tests/test_php_target.py"):
    ast.parse(Path(f).read_text(encoding="utf-8"))
print("  两个文件语法 OK")
