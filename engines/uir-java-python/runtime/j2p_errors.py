"""The Java throwable hierarchy, shared by the runtime and by java.time.

It lives in its own module for one reason: ``j2p_time`` needs these classes at
class-definition time, and ``j2p_runtime`` imports ``j2p_time``.  Reaching for
``__bases__`` reassignment to paper over that cycle does not work -- Python
refuses it when the layouts differ -- and would have hidden the real problem,
which is that two modules wanted to own the same hierarchy.
"""

from __future__ import annotations


class JavaThrowable(Exception):
    """Base of every exception the generated code can raise.

    ``java_name`` is what Java prints in a stack trace, and is what the
    differential harness compares on, so an exception raised by the translation
    must be the *same* exception Java raises, not merely "some error".
    """

    java_name = "java.lang.Throwable"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message if message is not None else "")
        self.message = message


class JavaException(JavaThrowable):
    java_name = "java.lang.Exception"


class RuntimeExceptionJ(JavaException):
    java_name = "java.lang.RuntimeException"


class ArithmeticExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.ArithmeticException"


class NullPointerExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.NullPointerException"


class ClassCastExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.ClassCastException"


class NumberFormatExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.NumberFormatException"


class IndexOutOfBoundsExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.IndexOutOfBoundsException"


class ArrayIndexOutOfBoundsExceptionJ(IndexOutOfBoundsExceptionJ):
    java_name = "java.lang.ArrayIndexOutOfBoundsException"


class StringIndexOutOfBoundsExceptionJ(IndexOutOfBoundsExceptionJ):
    java_name = "java.lang.StringIndexOutOfBoundsException"


class IllegalArgumentExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.IllegalArgumentException"


class IllegalStateExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.IllegalStateException"


class IOExceptionJ(JavaException):
    java_name = "java.io.IOException"


class UncheckedIOExceptionJ(RuntimeExceptionJ):
    java_name = "java.io.UncheckedIOException"


class FileNotFoundExceptionJ(IOExceptionJ):
    java_name = "java.io.FileNotFoundException"


class NoSuchFileExceptionJ(IOExceptionJ):
    java_name = "java.nio.file.NoSuchFileException"


class NoSuchAlgorithmExceptionJ(JavaException):
    java_name = "java.security.NoSuchAlgorithmException"


class TimeoutExceptionJ(JavaException):
    java_name = "java.util.concurrent.TimeoutException"


class SecurityExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.SecurityException"


class ConcurrentModificationExceptionJ(RuntimeExceptionJ):
    java_name = "java.util.ConcurrentModificationException"


class ArrayStoreExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.ArrayStoreException"


class CloneNotSupportedExceptionJ(JavaException):
    java_name = "java.lang.CloneNotSupportedException"


class InterruptedExceptionJ(JavaException):
    java_name = "java.lang.InterruptedException"


class NoSuchElementExceptionJ(RuntimeExceptionJ):
    java_name = "java.util.NoSuchElementException"


class UnsupportedOperationExceptionJ(RuntimeExceptionJ):
    java_name = "java.lang.UnsupportedOperationException"


