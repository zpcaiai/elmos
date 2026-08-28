# Engineering Assurance Standards Mapping

This package uses public standards and community verification projects as engineering control sources. It does not assert legal compliance, audit opinion or accredited certification. Exact versions and applicability must be frozen for each release.

| Profile ID | Engineering use | Controls | Source reference |
|---|---|---:|---|
| `owasp-asvs` | OWASP ASVS web and API verification controls | 14 | `https://owasp.org/www-project-application-security-verification-standard/` |
| `owasp-genai-llm-2026` | OWASP GenAI LLM Top 10 2026 risk coverage | 10 | `https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/` |
| `owasp-agentic-2026` | OWASP Top 10 for Agentic Applications 2026 coverage | 10 | `https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/` |
| `owasp-aisvs` | OWASP AI Security Verification Standard controls | 10 | `https://owasp.org/www-project-artificial-intelligence-security-verification-standard-aisvs-docs/` |
| `nist-ssdf` | NIST SSDF secure development practices | 4 | `https://csrc.nist.gov/pubs/sp/800/218/final` |
| `nist-ssdf-ai` | NIST SP 800-218A AI secure development profile | 5 | `https://csrc.nist.gov/pubs/sp/800/218/a/final` |
| `slsa-1.2` | SLSA 1.2 source and build integrity | 7 | `https://slsa.dev/spec/v1.2/` |
| `wcag-2.2-aa` | WCAG 2.2 AA accessibility coverage | 10 | `https://www.w3.org/TR/WCAG22/` |
| `pci-dss-4.0.1` | PCI DSS 4.0.1 payment boundary controls | 12 | `https://www.pcisecuritystandards.org/standards/pci-dss/` |
| `owasp-masvs` | OWASP MASVS mobile and mini-app adjacent controls | 8 | `https://mas.owasp.org/MASVS/` |
| `opentelemetry-semconv` | OpenTelemetry semantic convention conformance | 10 | `https://opentelemetry.io/docs/specs/semconv/` |

Each control is materialized into three evidence surfaces: automated negative tests, configuration/build evidence and runtime observation. Non-applicability requires an explicit signed rationale.
