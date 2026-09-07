---
name: wcf-to-corewcf-grpc-rest-migrator
description: Inventory WCF contracts, bindings, behaviors and clients, then choose CoreWCF, gRPC, REST, messaging, coexistence, or redesign with contract gates.
---

# WCF to CoreWCF, gRPC, REST, or Messaging Migrator

Inventory services, ServiceContract/OperationContract/DataContract, endpoints, addresses, bindings, behaviors, security, transactions, reliable sessions, duplex callbacks, streaming, message inspectors, custom encoders, metadata/WSDL, hosting and client populations.

## Decision matrix

- Prefer evaluating CoreWCF for compatible SOAP contracts, NetTcp, and existing clients that must remain.
- Consider gRPC for controlled strongly typed service-to-service callers.
- Consider REST only when HTTP resource semantics and client migration are explicitly designed; never translate SOAP to REST mechanically.
- Consider messaging for asynchronous workflows with a defined delivery/idempotency model.
- Mark complex custom bindings/behaviors `PARTIAL` or `REQUIRES_REDESIGN` and require architecture approval.

CoreWCF is a candidate, not a universal answer. Security modes, certificates, identity, transaction flow, interoperability, WSDL and legacy-client behavior require independent evidence.

## Required output

Produce service/contract/endpoint/binding/behavior/operation inventories, client impact, target alternatives, selected decision with rationale, coexistence/cutover steps, WSDL/SOAP/client/security/transaction gates, and rollback obligations.
