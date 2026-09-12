"""Offline assurance reference model. Not a production certification authority."""
from .core import evaluate, TrustedContext, TrustedKey
__all__ = ["evaluate", "TrustedContext", "TrustedKey"]
