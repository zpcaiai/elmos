---
name: esb-soa-flow-mapping-and-adapter-modernizer
description: Decompose legacy ESB and SOA flows into protocol adapters, versioned mappings, routing, domain logic, data ownership, and workflow responsibilities. Use for IIB, App Connect, TIBCO, Mule, OSB, webMethods, BizTalk, SAP PI/PO, or custom flow modernization.
---

# ESB and SOA Modernization

## Classify responsibility

Classify every flow segment as PROTOCOL_ADAPTER, DATA_TRANSFORMATION, CONTENT_ROUTING, SERVICE_FACADE, PROCESS_ORCHESTRATION, BUSINESS_RULE, DATA_ACCESS, SECURITY_GATEWAY, or FILE_TRANSFER.

Move protocol conversion to adapters, format mapping to versioned boundary transformations, simple routing to gateway or broker, domain decisions to owned services, long stateful processes to workflow, and shared data access to an owner API.

## Preserve contracts

Inventory WSDL, operations, policies, endpoints, registries, shared services, compositions, scripts, and mappings. Record each mapping field, rule, default, lookup, loss, error, owner, and version.

Detect pricing, eligibility, approval, hidden security, database access, external calls, date/currency logic, and shared libraries inside mappings or scripts. Do not copy a God ESB or an unbounded enterprise canonical model into the target.
