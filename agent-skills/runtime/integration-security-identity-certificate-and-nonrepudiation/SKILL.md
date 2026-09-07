---
name: integration-security-identity-certificate-and-nonrepudiation
description: Govern identities, authorization, certificates, payload protection, signatures, and non-repudiation for APIs, brokers, partners, and file transfer. Use when replacing shared credentials, designing least privilege, rotating partner certificates, or packaging AS2 evidence.
---

# Integration Security

## Establish identity and scope

Distinguish user, application, workload, partner, broker client, gateway client, MFT agent, and administrator identities. Bind authorization to the precise API route, queue, topic, consumer group, exchange, partner, file route, and operation.

Replace shared broker, partner, and gateway credentials with owner-assigned, scoped, rotatable identities. Keep broker passwords, API keys, tokens, and private keys out of exports, evidence, logs, prompts, and registries.

## Protect messages

Select transport TLS, message encryption, message signature, field encryption, tokenization, or an explicitly accepted lack of protection based on classification. Preserve AS2 message ID, MIC, signature, encryption, MDN, certificate, timestamp, partner, and payload hash as non-repudiation evidence.

Do not interpret transport-security evidence as proof that a business transaction succeeded.
