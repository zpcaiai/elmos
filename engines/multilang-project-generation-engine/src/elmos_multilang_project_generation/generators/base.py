from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any

from ..models import PSIR, GeneratedProject, EntitySpec, EndpointSpec, ServiceSpec

class ProjectGenerator(ABC):
    @abstractmethod
    def generate(self, psir: PSIR) -> GeneratedProject:
        pass

    @abstractmethod
    def generate_entity(self, entity_spec: EntitySpec) -> str:
        pass

    @abstractmethod
    def generate_endpoint(self, endpoint_spec: EndpointSpec) -> str:
        pass

    @abstractmethod
    def generate_service(self, service_spec: ServiceSpec) -> str:
        pass

    @abstractmethod
    def generate_build_config(self) -> str:
        pass

    @abstractmethod
    def generate_config(self) -> str:
        pass

    @abstractmethod
    def generate_tests(self) -> Dict[str, str]:
        pass
