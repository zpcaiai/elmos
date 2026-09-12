"""Industrial local Host Broker for the 1,244 HOST_ROUTE_BOUND Foundry skills.

Pack dispatch uses exact compiled native-program handlers.  Family kernels
remain available for domain-input unit tests.  No LLM API key is required
for local industrial execution.
"""

from .families import KernelFamily, classify_skill
from .host_broker import (
    INDUSTRIAL_BROKER_ID,
    INDUSTRIAL_BROKER_VERSION,
    IndustrialLocalHostBroker,
    execute_industrial_skill,
)
from .kernels import KernelResult, execute_kernel

__all__ = [
    "INDUSTRIAL_BROKER_ID",
    "INDUSTRIAL_BROKER_VERSION",
    "IndustrialLocalHostBroker",
    "KernelFamily",
    "KernelResult",
    "classify_skill",
    "execute_industrial_skill",
    "execute_kernel",
]
