"""Lightweight standard-library compatibility shim for pytest.

Enables pytest-authored test suites to execute natively under standard library unittest
without installing third-party pytest packages.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
import unittest


class raises:
    def __init__(self, expected_exception: type[BaseException], match: str | None = None) -> None:
        self.expected = expected_exception
        self.match = match
        self.value: Any = None

    def __enter__(self) -> raises:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> bool:
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected}")
        if issubclass(exc_type, self.expected):
            self.value = exc_val
            if self.match:
                if not re.search(self.match, str(exc_val)):
                    raise AssertionError(f"Pattern '{self.match}' does not match '{exc_val}'")
            return True
        return False


class MonkeyPatch:
    def __init__(self) -> None:
        self._undo: list[Any] = []

    def setattr(self, target: Any, name: str, value: Any, raising: bool = True) -> None:
        if isinstance(target, str):
            import importlib
            mod_name, attr = target.rsplit(".", 1)
            target = importlib.import_module(mod_name)
            name = attr
        has_old = hasattr(target, name)
        old_val = getattr(target, name, None)
        setattr(target, name, value)
        self._undo.append(("setattr", target, name, old_val, has_old))

    def chdir(self, path: Any) -> None:
        import os
        old_cwd = os.getcwd()
        os.chdir(path)
        self._undo.append(("chdir", old_cwd))

    def undo(self) -> None:
        import os
        for item in reversed(self._undo):
            if item[0] == "chdir":
                os.chdir(item[1])
            elif item[0] == "setattr":
                _, target, name, old_val, has_old = item
                if has_old:
                    setattr(target, name, old_val)
                else:
                    delattr(target, name)
        self._undo.clear()


FIXTURES: dict[str, Callable[..., Any]] = {}


def fixture(func: Callable[..., Any] | None = None, scope: str = "function") -> Any:
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        FIXTURES[fn.__name__] = fn
        setattr(fn, "_is_fixture", True)
        return fn

    if func is not None:
        return decorator(func)
    return decorator


class _Mark:
    @staticmethod
    def parametrize(argnames: str | Sequence[str], argvalues: Sequence[Any], *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        if isinstance(argnames, str):
            names = [a.strip() for a in argnames.split(",")]
        else:
            names = list(argnames)

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            setattr(func, "_pytest_parametrize", (names, argvalues))
            return func

        return decorator


mark = _Mark()


def resolve_fixture(fixture_name: str, fixtures_dict: dict[str, Callable[..., Any]], cleanups: list[Callable[[], None]], cache: dict[str, Any]) -> Any:
    if fixture_name in cache:
        return cache[fixture_name]
    if fixture_name == "tmp_path":
        td = tempfile.TemporaryDirectory()
        cleanups.append(td.cleanup)
        val = Path(td.name).resolve()
        cache["tmp_path"] = val
        return val
    if fixture_name == "monkeypatch":
        mp = MonkeyPatch()
        cleanups.append(mp.undo)
        cache["monkeypatch"] = mp
        return mp
    if fixture_name in fixtures_dict:
        fn = fixtures_dict[fixture_name]
        sig = inspect.signature(fn)
        kwargs = {}
        for param in sig.parameters.values():
            kwargs[param.name] = resolve_fixture(param.name, fixtures_dict, cleanups, cache)
        res = fn(**kwargs)
        if inspect.isgenerator(res):
            val = next(res)

            def _gen_cleanup() -> None:
                try:
                    next(res)
                except StopIteration:
                    pass

            cleanups.append(_gen_cleanup)
        else:
            val = res
        cache[fixture_name] = val
        return val
    raise ValueError(f"Unknown fixture: {fixture_name}")


def build_test_suite(module: Any) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    fixtures = dict(FIXTURES)
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and getattr(obj, "_is_fixture", False):
            fixtures[name] = obj

    for name in dir(module):
        if not name.startswith("test_"):
            continue
        func = getattr(module, name)
        if not callable(func):
            continue

        if hasattr(func, "_pytest_parametrize"):
            argnames, argvalues = getattr(func, "_pytest_parametrize")
            for idx, case_vals in enumerate(argvalues):
                if not isinstance(case_vals, (list, tuple)):
                    case_vals = [case_vals]
                param_dict = dict(zip(argnames, case_vals))

                class ParamTestCase(unittest.TestCase):
                    def __init__(self, fn: Callable[..., Any] = func, p_dict: dict[str, Any] = param_dict, test_name: str = f"{name}_{idx}") -> None:
                        super().__init__("run_test")
                        self.fn = fn
                        self.p_dict = p_dict
                        self._test_name = test_name

                    def __str__(self) -> str:
                        return f"{self._test_name} ({self.fn.__module__})"

                    def id(self) -> str:
                        return f"{self.fn.__module__}.{self._test_name}"

                    def run_test(self) -> None:
                        cleanups: list[Callable[[], None]] = []
                        cache: dict[str, Any] = {}
                        try:
                            sig = inspect.signature(self.fn)
                            kwargs = {}
                            for p in sig.parameters.values():
                                if p.name in self.p_dict:
                                    kwargs[p.name] = self.p_dict[p.name]
                                else:
                                    kwargs[p.name] = resolve_fixture(p.name, fixtures, cleanups, cache)
                            self.fn(**kwargs)
                        finally:
                            for cu in reversed(cleanups):
                                cu()

                suite.addTest(ParamTestCase())
        else:
            class FuncTestCase(unittest.TestCase):
                def __init__(self, fn: Callable[..., Any] = func, test_name: str = name) -> None:
                    super().__init__("run_test")
                    self.fn = fn
                    self._test_name = test_name

                def __str__(self) -> str:
                    return f"{self._test_name} ({self.fn.__module__})"

                def id(self) -> str:
                    return f"{self.fn.__module__}.{self._test_name}"

                def run_test(self) -> None:
                    cleanups: list[Callable[[], None]] = []
                    cache: dict[str, Any] = {}
                    try:
                        sig = inspect.signature(self.fn)
                        kwargs = {}
                        for p in sig.parameters.values():
                            kwargs[p.name] = resolve_fixture(p.name, fixtures, cleanups, cache)
                        self.fn(**kwargs)
                    finally:
                        for cu in reversed(cleanups):
                            cu()

            suite.addTest(FuncTestCase())
    return suite
