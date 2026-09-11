"""Industrial-grade polyglot translation: IR, lowering, emit, interpret, campaign."""

from .campaign import prove_route_corpus, run_industrial_campaign
from .corpora import all_corpora
from .emitter import emit_industrial_module
from .interpreter import IndustrialInterpreter
from .languages import INDUSTRIAL_LANGUAGES, INDUSTRIAL_ROUTE_KEYS
from .metric import industrial_quality_percent
from .profile import INDUSTRIAL_DOMAINS, INDUSTRIAL_PROFILE

__all__ = [
    "INDUSTRIAL_DOMAINS",
    "INDUSTRIAL_LANGUAGES",
    "INDUSTRIAL_PROFILE",
    "INDUSTRIAL_ROUTE_KEYS",
    "IndustrialInterpreter",
    "all_corpora",
    "emit_industrial_module",
    "industrial_quality_percent",
    "prove_route_corpus",
    "run_industrial_campaign",
]
