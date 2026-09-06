# Sources and provenance

Reviewed for this design on 2026-09-06. Primary technical references:

- **S01 Agent Skills specification** — https://agentskills.io/specification
  SKILL.md metadata and progressive disclosure
- **S02 OpenAI Skills documentation** — https://learn.chatgpt.com/docs/build-skills
  skill usage and distribution; no API integration is required by this package
- **S03 DAP overview** — https://microsoft.github.io/debug-adapter-protocol/overview
  capability flags, lifecycle, breakpoint verification, stopped-state handles
- **S04 LSP 3.17 specification** — https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/
  position encodings and language capabilities; versioned protocol not a claim of latest release
- **S05 debugpy** — https://github.com/microsoft/debugpy
  actual Python DAP candidate; local trusted fixture tested
- **S06 vscode-js-debug** — https://github.com/microsoft/vscode-js-debug
  JS DAP candidate; not tested in deployment here
- **S07 java-debug** — https://github.com/microsoft/java-debug
  JVM JDI/DAP and JDT integration candidate
- **S08 netcoredbg** — https://github.com/Samsung/netcoredbg
  CoreCLR DAP candidate, qualified versions and licenses required
- **S09 Delve DAP** — https://github.com/go-delve/delve/tree/master/service/dap
  Go debug candidate
- **S10 LLDB DAP** — https://lldb.llvm.org/use/lldbdap.html
  native debug candidate
- **S11 OpenTelemetry context propagation** — https://opentelemetry.io/docs/concepts/context-propagation/
  propagated context for trace correlations, not universal line replay
- **S12 gVisor security model** — https://gvisor.dev/docs/architecture_guide/security/
  isolation boundary candidate; deployment validation still required
- **S13 Firecracker** — https://firecracker-microvm.github.io/
  microVM candidate; host implementation and qualification required
- **S14 Vercel Sandbox** — https://vercel.com/docs/sandbox
  optional provider integration, not automatically provisioned
- **S15 WebContainers introduction** — https://webcontainers.io/guides/introduction
  optional JS/Node browser route, not universal native replacement
- **S16 WebContainers browser support** — https://webcontainers.io/guides/browser-support
  feature detection required; page may retain old dated browser notes, no current per-browser guarantee used
- **S17 Flutter Web** — https://docs.flutter.dev/platform-integration/web
  web/native distinction
- **S18 Flutter iOS setup** — https://docs.flutter.dev/platform-integration/ios/setup
  native SDK/platform requirements
- **S19 Node debugging** — https://nodejs.org/learn/getting-started/debugging
  inspector exposure and process debugging risk

## Existing Elmos source material

The three baseline documents and exact file identifiers are recorded in `sources.json`.
They were read as design inputs; the package does not bundle their entire contents or claim a live repo audit.
The 600-second rule, local model and workflow composition are original proposed design choices.
Local lab scripts run only original cart programs written for this package.
No API keys, credentials, private project source or third-party binaries are distributed.
