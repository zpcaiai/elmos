"""Foundation regressions.

These pin defects that only appear when an error travels the way a real one
does — out of a context manager, through a re-raise, with a traceback attached.
A ``pytest.raises`` around a direct call never exercises that path, which is
exactly why the defect below survived 1,376 passing tests and only fell out of
the first live PostgreSQL transaction.
"""

from __future__ import annotations

import contextlib

import pytest

from elmos_autonomy_kernel.errors import Category, KernelError, register_codes

register_codes(Category.INPUT, "TEST_ONLY_FOUNDATION_CODE")


def _boom() -> None:
    raise KernelError(code="TEST_ONLY_FOUNDATION_CODE", message="boom")


def test_a_kernel_error_can_carry_a_traceback():
    """Python assigns ``__traceback__`` to an exception as it propagates.

    A frozen, slotted dataclass refuses that assignment and — because of how the
    generated ``__setattr__`` closes over the class — fails with an unrelated
    ``TypeError``, replacing the real error with a confusing one at whatever
    frame re-raised it.
    """

    with pytest.raises(KernelError) as excinfo:
        _boom()
    assert excinfo.value.__traceback__ is not None
    assert excinfo.value.code == "TEST_ONLY_FOUNDATION_CODE"


def test_a_kernel_error_survives_a_context_manager_re_raise():
    """The exact shape that broke: a generator-based context manager unwinding.

    ``contextlib`` re-throws the exception into the generator and sets
    ``__traceback__`` on the way through.  Every database transaction, file
    handle and lock guard in the kernel is one of these.
    """

    @contextlib.contextmanager
    def guard():
        yield

    with pytest.raises(KernelError) as excinfo:
        with guard():
            _boom()
    assert excinfo.value.code == "TEST_ONLY_FOUNDATION_CODE"


def test_a_kernel_error_preserves_its_cause():
    """``raise ... from exc`` assigns ``__cause__``; the same write path."""

    try:
        try:
            raise ValueError("underlying")
        except ValueError as exc:
            raise KernelError(code="TEST_ONLY_FOUNDATION_CODE",
                              message="wrapped") from exc
    except KernelError as error:
        assert isinstance(error.__cause__, ValueError)
        assert error.to_payload()["code"] == "TEST_ONLY_FOUNDATION_CODE"
