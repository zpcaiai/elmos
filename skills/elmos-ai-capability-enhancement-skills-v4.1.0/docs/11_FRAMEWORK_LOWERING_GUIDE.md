# Framework Lowering Guide

This guide defines semantic mappings. Exact APIs are resolved by versioned adapters at release time.

## Dify

| AI-SIR | Dify lowering |
|---|---|
| Solution/chat interaction | App metadata and Chatflow/Workflow |
| Workflow nodes/edges | DSL graph nodes, variables and transitions |
| Model contract | Model/provider configuration references |
| Tool contract | built-in/custom tool plugin references |
| RAG | knowledge retrieval and knowledge-pipeline configuration |
| Human approval | native construct where available, otherwise external-policy gap |
| Durable execution | platform behavior plus external runtime obligation where required |
| Evidence | exported DSL hash, dependency manifest, native import and scenario execution |

The adapter generates deterministic node IDs and layout where possible. Visual coordinates are non-semantic only when runtime/acceptance is unaffected. Custom nodes/plugins are imported through plugin manifests or recorded as opaque.

## LangChain

Use LangChain for provider/tool/retriever composition and short-horizon agents. Lower durable state-machine requirements to LangGraph or attach an external durable runtime. Imported chains/agents become AI-SIR model/tool/retrieval/workflow nodes rather than remaining framework objects.

Required generated assets:

- typed settings and dependency lock;
- structured output schemas;
- tool effect/authority wrappers;
- retriever/RAG contracts;
- middleware;
- API/streaming;
- trace/eval hooks;
- migration profile to LangGraph.

## LangGraph

| AI-SIR | LangGraph lowering |
|---|---|
| State schema | typed state and reducers |
| Workflow node | graph node function/agent |
| Guard/branch | conditional edges |
| Loop | graph cycle plus explicit termination/bound |
| Parallel/join | parallel branches with conflict-safe reducers |
| Checkpoint | checkpointer profile |
| Long-term memory | Store/profile |
| Human approval | interrupt/resume |
| Subworkflow | subgraph |
| Runtime evidence | checkpointer state + normalized OTel/trace bridge |

Static generation checks terminal reachability, state writes and retry safety. Dynamic verification tests crash/resume, interrupt expiry and duplicate side effects.

## Spring AI

Recommended module layout:

```text
src/main/java/.../
├── api/
├── application/
├── domain/
└── infrastructure/
    ├── model/
    ├── tools/
    ├── rag/
    ├── vectorstore/
    ├── mcp/
    ├── memory/
    └── observability/
```

Lowering:

- model contract → ChatModel/EmbeddingModel clients and ChatClient;
- middleware/context → Advisors;
- structured output → typed entity/schema conversion;
- RAG → document readers/transformers, VectorStore, retrieval advisors or modular pipeline;
- tools → typed tool callbacks with authority wrapper;
- MCP → client/server starters/config;
- memory → ChatMemory plus external durable/session store where required;
- interaction → REST/SSE/WebSocket;
- security → Spring Security/OIDC and tenant context;
- operations → Actuator/Micrometer/OpenTelemetry;
- tests → JUnit, Testcontainers, contract and security tests;
- deployment → Docker/Helm/migrations/runbook.

Long side-effecting workflows may combine Spring AI with the Elmos durable runtime rather than relying on request-thread state.

## Pi

Generated Pi package:

```text
package.json
extensions/
skills/<skill>/SKILL.md
prompts/
themes/
tests/
.pi/settings.json
```

The package includes repository bootstrap, build/test commands, architecture navigation, Domain Pack skills, safety/authority policy, review workflow and RPC/SDK embedding when required. Host-native load and tool-deny tests are mandatory.

## DeepSeek Harness

Lower to:

- Cordis plugins/services/events;
- typed configuration;
- lifecycle effects and cleanup;
- bundle manifests;
- profile/patch composition;
- session/tool/subagent integrations;
- load/unload/HMR tests.

Elmos authority and certification remain outside the plugin runtime.

## OpenHarness

Lower provider/tool/skill/plugin/hook/memory/session/permission interfaces. The adapter records which features are native and which use Elmos runtime integrations. Resume and permission tests are required.

## Symphony

Generate:

- repository `WORKFLOW.md`;
- work-item adapter;
- workspace isolation;
- concurrency/retry/backoff;
- workpad/proof-of-work;
- Git/PR handoff;
- acceptance and evidence gates.

Symphony orchestrates work; it does not replace Repository Semantic IR or K8.

## OpenClaw

Generated layout:

```text
openclaw.json
workspace/
  AGENTS.md
  SOUL.md
  skills/
plugins/
  <plugin>/openclaw.plugin.json
channels/
policies/
sandbox/
service/
tests/
```

Use isolated gateway/worker placement by tenant or authority domain. Plugins/skills are signed/allowlisted and treated as trusted executable supply-chain components. The generated gateway delegates durable business workflows to a production backend when appropriate.

## OpenAI Agents SDK

Lower agents, tools, handoffs, guardrails, sessions, tracing, MCP and realtime contracts into Python or TypeScript SDK projects. Guardrails are part of runtime protection but do not replace external tool authority.

## Google ADK

Lower agent topology, workflow agents, sessions/artifacts, A2A and eval/deploy assets into the selected language adapter. Cross-language parity is feature-profiled, not assumed.

## Microsoft Agent Framework

Lower agents, sessions, graph workflows, human gates and telemetry to .NET/Python targets. AutoGen/Semantic Kernel importers recover source semantics, then migration uses AI-SIR and differential tests rather than text replacement.

## LlamaIndex / Haystack / PydanticAI

- LlamaIndex: document/data connectors, indexes, workflows and agentic RAG.
- Haystack: components, pipelines, document stores, agents and serialization.
- PydanticAI: typed dependencies/tools/output and graph state machines.

All three retain Elmos RAG, authority, durability and assurance contracts where native features are incomplete.

## Vercel AI SDK and AG-UI

Lower interaction/streaming/tool event contracts to the UI/server protocol. Business state, authority, side effects and certification remain in the backend runtime.

## Visual platform family

Langflow, Coze Studio, FastGPT and n8n use adapter-specific import/export. The product stores the visual source as an artifact and AI-SIR as semantic truth. Every custom component receives an opaque or native adapter record.

## Coding agent family

OpenHands, OpenCode, Codex, Claude Code, Gemini CLI, Cline/Roo, Continue and Aider receive host-specific skills/rules/plugins but share:

- repository capability contract;
- allowed paths/tools/network;
- Git/worktree policy;
- build/test/evidence commands;
- bounded patch/review;
- task benchmark;
- independent completion gate.
