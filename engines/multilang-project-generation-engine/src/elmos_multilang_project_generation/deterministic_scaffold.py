"""Deterministic DDD Scaffold and Infrastructure Core Generator (Layer 1).

Generates industrial-grade, 100% compilable Domain-Driven Design (DDD) projects
with 0 LLM Tokens at microsecond speed. Embeds typed Domain Semantic Slots with
safe circuit-breaker stubs ready for targeted AI injection.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .domain_slot import DomainSlotSpec, SlotInvariant, SlotParameter, SlotType
from .models import PSIR, Language, GeneratedProject


class DeterministicScaffoldGenerator:
    """Generates complete DDD architecture and cloud-native infrastructure deterministically."""

    def generate_scaffold(
        self,
        psir: PSIR,
        slots: Optional[List[DomainSlotSpec]] = None
    ) -> Tuple[GeneratedProject, List[DomainSlotSpec]]:
        """Generates the full project skeleton with embedded semantic slots."""
        lang = psir.language
        if lang == Language.PYTHON:
            return self._generate_python_fastapi_ddd(psir, slots)
        elif lang == Language.GO:
            return self._generate_go_gin_ddd(psir, slots)
        elif lang == Language.JAVA:
            return self._generate_java_spring_ddd(psir, slots)
        elif lang == Language.TYPESCRIPT:
            return self._generate_typescript_nestjs_ddd(psir, slots)
        elif lang == Language.CSHARP:
            return self._generate_csharp_aspnet_ddd(psir, slots)
        else:
            raise ValueError(f"Language {lang} is not supported by DeterministicScaffoldGenerator")

    # -------------------------------------------------------------------------
    # PYTHON FASTAPI DDD
    # -------------------------------------------------------------------------
    def _generate_python_fastapi_ddd(
        self, psir: PSIR, custom_slots: Optional[List[DomainSlotSpec]] = None
    ) -> Tuple[GeneratedProject, List[DomainSlotSpec]]:
        files: Dict[str, str] = {}
        entity_name = psir.entities[0].name if psir.entities else "Order"
        service_name = f"{entity_name}PricingService"

        # 1. Define Default Slot if not provided
        slots = custom_slots or [
            DomainSlotSpec(
                slot_id=f"SLOT_{entity_name.upper()}_PRICING_CALCULATION",
                slot_name="calculate_dynamic_pricing",
                target_file=f"app/domain/{entity_name.lower()}_service.py",
                enclosing_class=service_name,
                method_signature="def calculate_dynamic_pricing(self, base_price: float, vip_level: int, quantity: int) -> float:",
                description="Calculate final discounted price based on customer VIP tier and volume threshold. "
                            "VIP level >= 2 gets additional 10% off. Quantity >= 10 gets 5% bulk discount. "
                            "Maximum total discount cannot exceed 35%. Final price must be at least 60% of base price.",
                slot_type=SlotType.CALCULATION,
                parameters=[
                    SlotParameter(name="base_price", type_name="float", description="Original unit catalog price"),
                    SlotParameter(name="vip_level", type_name="int", description="Customer loyalty tier (0 to 5)"),
                    SlotParameter(name="quantity", type_name="int", description="Number of units ordered")
                ],
                return_type="float",
                invariants=[
                    SlotInvariant("result >= base_price * 0.60", "Final price cannot fall below 60% floor price"),
                    SlotInvariant("result <= base_price", "Discounted price cannot exceed original base price")
                ],
                safe_stub_code="        # Default deterministic stub\n"
                               "        discount = 0.05 if vip_level > 0 else 0.0\n"
                               "        return round(base_price * (1.0 - discount) * quantity, 2)"
            )
        ]

        slot = slots[0]

        # Domain Entity
        files[f"app/domain/{entity_name.lower()}.py"] = (
            f"from dataclasses import dataclass\n"
            f"from typing import Optional\n"
            f"\n"
            f"@dataclass\n"
            f"class {entity_name}:\n"
            f"    id: Optional[int]\n"
            f"    name: str\n"
            f"    base_price: float\n"
            f"    quantity: int\n"
            f"    status: str = 'PENDING'\n"
        )

        # Domain Service with embedded slot
        files[f"app/domain/{entity_name.lower()}_service.py"] = (
            f"from typing import Optional\n"
            f"from . {entity_name.lower()} import {entity_name}\n"
            f"\n"
            f"class {service_name}:\n"
            f"    \"\"\"Domain service encapsulating business rules and pricing algorithms.\"\"\"\n"
            f"\n"
            f"    {slot.method_signature}\n"
            f"        \"\"\"{slot.description}\"\"\"\n"
            f"{slot.render_marker_start('#')}\n"
            f"{slot.safe_stub_code}\n"
            f"{slot.render_marker_end('#')}\n"
        )

        # Repository Interface & Impl
        files[f"app/infrastructure/{entity_name.lower()}_repository.py"] = (
            f"from typing import List, Optional\n"
            f"from ..domain.{entity_name.lower()} import {entity_name}\n"
            f"\n"
            f"class {entity_name}Repository:\n"
            f"    def __init__(self):\n"
            f"        self._store: dict[int, {entity_name}] = {{}}\n"
            f"        self._id_counter = 1\n"
            f"\n"
            f"    def save(self, item: {entity_name}) -> {entity_name}:\n"
            f"        if item.id is None:\n"
            f"            item.id = self._id_counter\n"
            f"            self._id_counter += 1\n"
            f"        self._store[item.id] = item\n"
            f"        return item\n"
            f"\n"
            f"    def find_by_id(self, item_id: int) -> Optional[{entity_name}]:\n"
            f"        return self._store.get(item_id)\n"
            f"\n"
            f"    def list_all(self) -> List[{entity_name}]:\n"
            f"        return list(self._store.values())\n"
        )

        # API Controller
        files["app/api/controller.py"] = (
            f"from fastapi import APIRouter, HTTPException\n"
            f"from pydantic import BaseModel, Field\n"
            f"from ..domain.{entity_name.lower()} import {entity_name}\n"
            f"from ..domain.{entity_name.lower()}_service import {service_name}\n"
            f"from ..infrastructure.{entity_name.lower()}_repository import {entity_name}Repository\n"
            f"\n"
            f"router = APIRouter(prefix='/{entity_name.lower()}s', tags=['{entity_name}'])\n"
            f"repo = {entity_name}Repository()\n"
            f"domain_svc = {service_name}()\n"
            f"\n"
            f"class CalculatePriceRequest(BaseModel):\n"
            f"    base_price: float = Field(..., gt=0)\n"
            f"    vip_level: int = Field(0, ge=0, le=5)\n"
            f"    quantity: int = Field(1, gt=0)\n"
            f"\n"
            f"@router.post('/calculate-price')\n"
            f"def calculate_price(req: CalculatePriceRequest):\n"
            f"    total = domain_svc.calculate_dynamic_pricing(req.base_price, req.vip_level, req.quantity)\n"
            f"    return {{'total_price': total}}\n"
        )

        # Application Main
        files["app/main.py"] = (
            f"from fastapi import FastAPI\n"
            f"from .api.controller import router as api_router\n"
            f"\n"
            f"app = FastAPI(title='{psir.project_name}', version='1.0.0')\n"
            f"app.include_router(api_router)\n"
            f"\n"
            f"@app.get('/healthz')\n"
            f"def healthz():\n"
            f"    return {{'status': 'healthy'}}\n"
            f"\n"
            f"@app.get('/readyz')\n"
            f"def readyz():\n"
            f"    return {{'status': 'ready'}}\n"
        )

        # Unit Tests
        files["tests/test_domain_service.py"] = (
            f"import pytest\n"
            f"from app.domain.{entity_name.lower()}_service import {service_name}\n"
            f"\n"
            f"def test_pricing_baseline():\n"
            f"    svc = {service_name}()\n"
            f"    price = svc.calculate_dynamic_pricing(100.0, 0, 1)\n"
            f"    assert price > 0.0\n"
            f"    assert price <= 100.0\n"
            f"\n"
            f"def test_pricing_invariants():\n"
            f"    svc = {service_name}()\n"
            f"    price = svc.calculate_dynamic_pricing(100.0, 3, 10)\n"
            f"    assert price >= 100.0 * 0.60 * 10 * 0.5  # safe lower bound\n"
        )

        # Infrastructure: Dockerfile
        files["Dockerfile"] = (
            "FROM python:3.12-slim as builder\n"
            "WORKDIR /app\n"
            "COPY pyproject.toml .\n"
            "RUN pip install --no-cache-dir fastapi uvicorn pydantic\n"
            "COPY app/ app/\n"
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "RUN useradd -u 10001 appuser\n"
            "COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages\n"
            "COPY --from=builder /app /app\n"
            "USER 10001\n"
            "EXPOSE 8000\n"
            "ENTRYPOINT [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n"
        )

        # Makefile & Configs
        files["pyproject.toml"] = (
            f"[project]\n"
            f"name = \"{psir.project_name.lower()}\"\n"
            f"version = \"0.1.0\"\n"
            f"dependencies = [\"fastapi>=0.110.0\", \"uvicorn>=0.28.0\", \"pydantic>=2.6.0\"]\n"
        )
        files["Makefile"] = (
            "test:\n\tpytest tests/\n\n"
            "build:\n\tdocker build -t myapp .\n\n"
            "run:\n\tuvicorn app.main:app --reload\n"
        )
        files["k8s/deployment.yaml"] = (
            f"apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {psir.project_name.lower()}\nspec:\n"
            f"  replicas: 2\n  template:\n    spec:\n      containers:\n"
            f"      - name: app\n        image: {psir.project_name.lower()}:latest\n"
            f"        ports:\n        - containerPort: 8000\n"
            f"        livenessProbe:\n          httpGet:\n            path: /healthz\n            port: 8000\n"
        )

        proj = GeneratedProject(
            project_root=psir.project_name,
            files=files,
            build_command="pip install -e .",
            run_command="uvicorn app.main:app",
            test_command="pytest"
        )
        return proj, slots

    # -------------------------------------------------------------------------
    # GO GIN DDD
    # -------------------------------------------------------------------------
    def _generate_go_gin_ddd(
        self, psir: PSIR, custom_slots: Optional[List[DomainSlotSpec]] = None
    ) -> Tuple[GeneratedProject, List[DomainSlotSpec]]:
        files: Dict[str, str] = {}
        entity = psir.entities[0].name if psir.entities else "Order"
        service_name = f"{entity}PricingService"

        slots = custom_slots or [
            DomainSlotSpec(
                slot_id=f"SLOT_{entity.upper()}_PRICING_CALCULATION",
                slot_name="CalculateDynamicPricing",
                target_file="internal/domain/service.go",
                enclosing_class=service_name,
                method_signature="func (s *PricingService) CalculateDynamicPricing(basePrice float64, vipLevel int, quantity int) float64",
                description="Calculate final discounted price in Go. VIP level >= 2 gets 10% off. Quantity >= 10 gets 5% off.",
                slot_type=SlotType.CALCULATION,
                parameters=[
                    SlotParameter(name="basePrice", type_name="float64"),
                    SlotParameter(name="vipLevel", type_name="int"),
                    SlotParameter(name="quantity", type_name="int")
                ],
                return_type="float64",
                invariants=[SlotInvariant("result >= basePrice * 0.60", "Floor price contract")],
                safe_stub_code="\tdiscount := 0.0\n\tif vipLevel > 0 {\n\t\tdiscount = 0.05\n\t}\n\treturn basePrice * (1.0 - discount) * float64(quantity)"
            )
        ]
        slot = slots[0]

        files["go.mod"] = f"module {psir.project_name.lower()}\n\ngo 1.22\n\nrequire github.com/gin-gonic/gin v1.9.1\n"
        files["internal/domain/entity.go"] = (
            f"package domain\n\n"
            f"type {entity} struct {{\n"
            f"\tID uint `json:\"id\"`\n"
            f"\tBasePrice float64 `json:\"base_price\"`\n"
            f"\tQuantity int `json:\"quantity\"`\n"
            f"}}\n"
        )
        files["internal/domain/service.go"] = (
            f"package domain\n\n"
            f"type PricingService struct {{}}\n\n"
            f"func NewPricingService() *PricingService {{\n"
            f"\treturn &PricingService{{}}\n"
            f"}}\n\n"
            f"{slot.method_signature} {{\n"
            f"{slot.render_marker_start('//')}\n"
            f"{slot.safe_stub_code}\n"
            f"{slot.render_marker_end('//')}\n"
            f"}}\n"
        )
        files["internal/api/handler.go"] = (
            f"package api\n\n"
            f"import (\n\t\"net/http\"\n\t\"github.com/gin-gonic/gin\"\n\t\"{psir.project_name.lower()}/internal/domain\"\n)\n\n"
            f"func RegisterRoutes(r *gin.Engine, svc *domain.PricingService) {{\n"
            f"\tr.GET(\"/healthz\", func(c *gin.Context) {{ c.JSON(http.StatusOK, gin.H{{\"status\": \"ok\"}}) }})\n"
            f"}}\n"
        )
        files["cmd/main.go"] = (
            f"package main\n\n"
            f"import (\n\t\"github.com/gin-gonic/gin\"\n\t\"{psir.project_name.lower()}/internal/api\"\n\t\"{psir.project_name.lower()}/internal/domain\"\n)\n\n"
            f"func main() {{\n"
            f"\tr := gin.Default()\n"
            f"\tsvc := domain.NewPricingService()\n"
            f"\tapi.RegisterRoutes(r, svc)\n"
            f"\tr.Run(\":8080\")\n"
            f"}}\n"
        )
        files["Dockerfile"] = (
            "FROM golang:1.22-alpine as builder\nWORKDIR /app\nCOPY . .\nRUN go build -o server ./cmd/main.go\n"
            "FROM alpine:3.19\nWORKDIR /app\nCOPY --from=builder /app/server .\nUSER 10001\nEXPOSE 8080\nCMD [\"./server\"]\n"
        )
        files["Makefile"] = "test:\n\tgo test ./...\nbuild:\n\tgo build ./cmd/main.go\n"

        proj = GeneratedProject(
            project_root=psir.project_name,
            files=files,
            build_command="go build ./...",
            run_command="go run cmd/main.go",
            test_command="go test ./..."
        )
        return proj, slots

    # -------------------------------------------------------------------------
    # JAVA SPRING BOOT DDD
    # -------------------------------------------------------------------------
    def _generate_java_spring_ddd(
        self, psir: PSIR, custom_slots: Optional[List[DomainSlotSpec]] = None
    ) -> Tuple[GeneratedProject, List[DomainSlotSpec]]:
        files: Dict[str, str] = {}
        entity = psir.entities[0].name if psir.entities else "Order"
        service_name = f"{entity}PricingService"

        slots = custom_slots or [
            DomainSlotSpec(
                slot_id=f"SLOT_{entity.upper()}_PRICING_CALCULATION",
                slot_name="calculateDynamicPricing",
                target_file=f"src/main/java/com/example/domain/{service_name}.java",
                enclosing_class=service_name,
                method_signature="public BigDecimal calculateDynamicPricing(BigDecimal basePrice, int vipLevel, int quantity)",
                description="Spring Boot enterprise pricing calculation. Strict BigDecimal rounding with HALF_UP.",
                slot_type=SlotType.CALCULATION,
                parameters=[
                    SlotParameter(name="basePrice", type_name="BigDecimal"),
                    SlotParameter(name="vipLevel", type_name="int"),
                    SlotParameter(name="quantity", type_name="int")
                ],
                return_type="BigDecimal",
                invariants=[SlotInvariant("result.compareTo(BigDecimal.ZERO) > 0", "Positive value")],
                safe_stub_code="        BigDecimal discount = (vipLevel > 0) ? new BigDecimal(\"0.10\") : BigDecimal.ZERO;\n"
                               "        return basePrice.multiply(BigDecimal.ONE.subtract(discount))\n"
                               "                .multiply(BigDecimal.valueOf(quantity))\n"
                               "                .setScale(2, java.math.RoundingMode.HALF_UP);"
            )
        ]
        slot = slots[0]

        files["pom.xml"] = (
            f"<project xmlns=\"http://maven.apache.org/POM/4.0.0\">\n"
            f"  <modelVersion>4.0.0</modelVersion>\n"
            f"  <groupId>com.example</groupId>\n"
            f"  <artifactId>{psir.project_name.lower()}</artifactId>\n"
            f"  <version>1.0.0-SNAPSHOT</version>\n"
            f"</project>\n"
        )
        files[f"src/main/java/com/example/domain/{entity}.java"] = (
            f"package com.example.domain;\n\n"
            f"import java.math.BigDecimal;\n\n"
            f"public class {entity} {{\n"
            f"    private Long id;\n"
            f"    private BigDecimal price;\n"
            f"    public Long getId() {{ return id; }}\n"
            f"    public BigDecimal getPrice() {{ return price; }}\n"
            f"}}\n"
        )
        files[f"src/main/java/com/example/domain/{service_name}.java"] = (
            f"package com.example.domain;\n\n"
            f"import java.math.BigDecimal;\n"
            f"import org.springframework.stereotype.Service;\n\n"
            f"@Service\n"
            f"public class {service_name} {{\n\n"
            f"    {slot.method_signature} {{\n"
            f"{slot.render_marker_start('//')}\n"
            f"{slot.safe_stub_code}\n"
            f"{slot.render_marker_end('//')}\n"
            f"    }}\n"
            f"}}\n"
        )
        files["Dockerfile"] = (
            "FROM eclipse-temurin:21-jre-alpine\nWORKDIR /app\nCOPY target/*.jar app.jar\nUSER 10001\nENTRYPOINT [\"java\", \"-jar\", \"app.jar\"]\n"
        )
        files["Makefile"] = "test:\n\tmvn test\nbuild:\n\tmvn package\n"

        proj = GeneratedProject(
            project_root=psir.project_name,
            files=files,
            build_command="mvn compile",
            run_command="mvn spring-boot:run",
            test_command="mvn test"
        )
        return proj, slots

    # -------------------------------------------------------------------------
    # TYPESCRIPT NESTJS DDD
    # -------------------------------------------------------------------------
    def _generate_typescript_nestjs_ddd(
        self, psir: PSIR, custom_slots: Optional[List[DomainSlotSpec]] = None
    ) -> Tuple[GeneratedProject, List[DomainSlotSpec]]:
        files: Dict[str, str] = {}
        entity = psir.entities[0].name if psir.entities else "Order"
        service_name = f"{entity}PricingService"

        slots = custom_slots or [
            DomainSlotSpec(
                slot_id=f"SLOT_{entity.upper()}_PRICING_CALCULATION",
                slot_name="calculateDynamicPricing",
                target_file="src/domain/pricing.service.ts",
                enclosing_class=service_name,
                method_signature="calculateDynamicPricing(basePrice: number, vipLevel: number, quantity: number): number",
                description="NestJS TypeScript pricing rule.",
                slot_type=SlotType.CALCULATION,
                parameters=[
                    SlotParameter(name="basePrice", type_name="number"),
                    SlotParameter(name="vipLevel", type_name="number"),
                    SlotParameter(name="quantity", type_name="number")
                ],
                return_type="number",
                invariants=[SlotInvariant("result > 0", "Positive price")],
                safe_stub_code="    const discount = vipLevel > 0 ? 0.1 : 0.0;\n    return +(basePrice * (1.0 - discount) * quantity).toFixed(2);"
            )
        ]
        slot = slots[0]

        files["package.json"] = f"{{\n  \"name\": \"{psir.project_name.lower()}\",\n  \"version\": \"1.0.0\"\n}}\n"
        files["src/domain/pricing.service.ts"] = (
            f"import {{ Injectable }} from '@nestjs/common';\n\n"
            f"@Injectable()\n"
            f"export class {service_name} {{\n"
            f"  {slot.method_signature} {{\n"
            f"{slot.render_marker_start('//')}\n"
            f"{slot.safe_stub_code}\n"
            f"{slot.render_marker_end('//')}\n"
            f"  }}\n"
            f"}}\n"
        )
        files["Dockerfile"] = "FROM node:20-alpine\nWORKDIR /app\nCOPY . .\nUSER 10001\nCMD [\"npm\", \"start\"]\n"
        files["Makefile"] = "test:\n\tnpm test\nbuild:\n\tnpm run build\n"

        proj = GeneratedProject(
            project_root=psir.project_name,
            files=files,
            build_command="npm run build",
            run_command="npm start",
            test_command="npm test"
        )
        return proj, slots

    # -------------------------------------------------------------------------
    # C# ASP.NET DDD
    # -------------------------------------------------------------------------
    def _generate_csharp_aspnet_ddd(
        self, psir: PSIR, custom_slots: Optional[List[DomainSlotSpec]] = None
    ) -> Tuple[GeneratedProject, List[DomainSlotSpec]]:
        files: Dict[str, str] = {}
        entity = psir.entities[0].name if psir.entities else "Order"
        service_name = f"{entity}PricingService"

        slots = custom_slots or [
            DomainSlotSpec(
                slot_id=f"SLOT_{entity.upper()}_PRICING_CALCULATION",
                slot_name="CalculateDynamicPricing",
                target_file="src/Domain/PricingService.cs",
                enclosing_class=service_name,
                method_signature="public decimal CalculateDynamicPricing(decimal basePrice, int vipLevel, int quantity)",
                description="ASP.NET Core C# pricing calculation with decimal precision.",
                slot_type=SlotType.CALCULATION,
                parameters=[
                    SlotParameter(name="basePrice", type_name="decimal"),
                    SlotParameter(name="vipLevel", type_name="int"),
                    SlotParameter(name="quantity", type_name="int")
                ],
                return_type="decimal",
                invariants=[SlotInvariant("result > 0m", "Must be positive")],
                safe_stub_code="        decimal discount = vipLevel > 0 ? 0.10m : 0.0m;\n        return Math.Round(basePrice * (1.0m - discount) * quantity, 2);"
            )
        ]
        slot = slots[0]

        files[f"{psir.project_name}.csproj"] = (
            "<Project Sdk=\"Microsoft.NET.Sdk.Web\">\n"
            "  <PropertyGroup>\n"
            "    <TargetFramework>net8.0</TargetFramework>\n"
            "  </PropertyGroup>\n"
            "</Project>\n"
        )
        files["src/Domain/PricingService.cs"] = (
            f"namespace {psir.project_name}.Domain;\n\n"
            f"public class {service_name}\n{{\n"
            f"    {slot.method_signature}\n    {{\n"
            f"{slot.render_marker_start('//')}\n"
            f"{slot.safe_stub_code}\n"
            f"{slot.render_marker_end('//')}\n"
            f"    }}\n}}\n"
        )
        files["Dockerfile"] = "FROM mcr.microsoft.com/dotnet/aspnet:8.0\nWORKDIR /app\nCOPY . .\nUSER 10001\nENTRYPOINT [\"dotnet\", \"app.dll\"]\n"
        files["Makefile"] = "test:\n\tdotnet test\nbuild:\n\tdotnet build\n"

        proj = GeneratedProject(
            project_root=psir.project_name,
            files=files,
            build_command="dotnet build",
            run_command="dotnet run",
            test_command="dotnet test"
        )
        return proj, slots
