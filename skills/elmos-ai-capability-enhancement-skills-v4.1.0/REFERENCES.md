# References and Version-Pinning Rules

The package design is informed by public specifications and official project documentation, including MCP, A2A, ACP, OpenAI Plugins/Apps SDK, OpenAPI, AsyncAPI, CloudEvents, OpenTelemetry, OpenLineage, Apache Iceberg, Delta Lake, KServe, NVIDIA Triton, Ray Serve, SLSA, Sigstore, SPIFFE/SPIRE, OWASP agentic security resources, NIST and ISO management/security guidance.

## Release rule

URLs and conceptual references are not production pins. Every production certificate must bind exact upstream version, artifact/container digest, adapter digest, conformance corpus, policy bundle and environment profile. Upstream changes invalidate only the dependent evidence subgraph, but critical invalidated evidence blocks release until rerun.

## Official reference starting points

- https://modelcontextprotocol.io/specification/2026-07-28
- https://a2a-protocol.org/latest/specification/
- https://agentclientprotocol.com/
- https://developers.openai.com/plugins
- https://www.asyncapi.com/docs/reference/specification/latest
- https://cloudevents.io/
- https://opentelemetry.io/docs/specs/semconv/gen-ai/
- https://openlineage.io/docs/
- https://iceberg.apache.org/spec/
- https://docs.delta.io/
- https://kserve.github.io/website/
- https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/
- https://docs.ray.io/en/latest/serve/
- https://slsa.dev/spec/
- https://www.sigstore.dev/
- https://spiffe.io/


## Certification maximum authoritative source families

The adapters store identifiers and mapping contracts only; exact editions and official licensed texts must be resolved at implementation/release time.

- ISO/CASCO conformity assessment family: ISO/IEC 17000, 17011, 17020, 17021-1, 17024, 17025, 17029, 17030, ISO 17034, ISO/IEC 17040, 17043, 17050, 17060, 17065 and 17067.
- BIPM/JCGM metrology publications: GUM/VIM and conformity decision guidance.
- Current AI standards and guidance: ISO/IEC 42005, 42006, developing 42007 profile, 23894, 24027, 24028, 24029, 25058/25059, 4213, 5259, 5338, 5469, 6254, 8200, 12791 and 12792.
- NIST AI RMF, Generative AI Profile, adversarial ML taxonomy, TEVV-Athlon and SP 800-218A.
- Common Criteria/ISO/IEC 15408 and ISO/IEC 18045; CCRA recognition.
- FIPS 140-3/ACVP and FIPS 203/204/205 post-quantum cryptography standards.
- IETF RATS, EAT, CoRIM and RFC 3161; W3C Verifiable Credentials.
- Applicable sector standards must be obtained from their authoritative publishers and interpreted by competent domain experts/regulators.


## Split package note

Source package: `elmos-ai-native-project-factory-total-skills-v4.0.0`. Package role: `capability`.
