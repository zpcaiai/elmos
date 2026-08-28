# Target Ecosystem Catalog and Product Policy

## Tier P0: direct commercial generators

| Family | Targets | Product role |
|---|---|---|
| Visual prototype/operations | Dify | Business-editable prototype, workflow and plugin target |
| Portable RAG | Universal RAG | Full production RAG architecture independent of one framework |
| Python/TS agents | LangChain, LangGraph | Integrations and durable graph runtime |
| Java enterprise | Spring AI | Spring-native enterprise AI service |
| Coding harness | Pi, DeepSeek Harness, OpenHarness, Symphony | Repository agent packages and coding orchestration |
| Personal/channel assistant | OpenClaw | Isolated gateway, channels, skills and plugins |
| Vendor agent SDK | OpenAI Agents SDK, Google ADK, Microsoft Agent Framework | Provider/ecosystem-native agent projects |
| Data/RAG frameworks | LlamaIndex, Haystack, PydanticAI | Document/data agents, pipelines and typed Python |
| AI web | Vercel AI SDK | Streaming/generative UI front end and server integration |
| Protocol | MCP, A2A, OpenAPI tools | Interoperable tool and agent gateway |
| Infrastructure | OpenTelemetry, pgvector | Production observability and default relational vector integration |

P0 does not mean every upstream version is pre-certified. It means the adapter is a first-class implementation objective with a native conformance contract.

## Tier P1: important generators and compatibility targets

Mastra, LangChain4j, CrewAI, RAGFlow, Langflow, Coze Studio, FastGPT, n8n AI, OpenHands, OpenCode, Codex, Claude Code, Gemini CLI, Cline/Roo, Continue, Aider, Strands Agents, Agno, smolagents, DSPy, Qwen-Agent, GraphRAG, Neo4j GraphRAG, LiteLLM, OpenRouter, vLLM, SGLang, Ollama, Qdrant, Milvus and Weaviate.

P1 adapters can become P0 after:

- demand and paid-route evidence;
- upstream stability and license fit;
- native conformance maturity;
- upgrade burden;
- security and operations envelope;
- at least one repeatable Golden Route.

## Compatibility/migration-only sources

AutoGen, Semantic Kernel, Flowise and OpenAI Swarm are represented as import/migration sources in this package. This is a product-policy decision, not a statement that they cannot run. Greenfield defaults should use a currently supported target portfolio selected from exact capability evidence.

## Do not expose the raw catalog as the primary UX

The user first chooses an outcome:

- enterprise knowledge assistant;
- agentic or graph RAG;
- document intelligence;
- multi-agent business process;
- coding agent or coding orchestrator;
- personal assistant;
- data/SQL agent;
- realtime/voice agent;
- AI-native web app;
- workflow automation;
- protocol gateway;
- enterprise agent control plane.

Elmos then proposes a portfolio and explains why each target has a role.

## Portfolio patterns

### Prototype-to-production

```text
Dify prototype
   ↓ import AI-SIR
LangGraph production runtime
   +
Spring AI enterprise facade
   +
OpenClaw or web channel
```

### Java enterprise

```text
Spring Boot estate
   ↓
Spring AI service
   + MCP client/server
   + pgvector or approved vector store
   + Elmos durable runtime for long side-effecting workflows
```

### Coding repository

```text
Repository evidence and build/test contracts
   ↓
Pi package + DeepSeek/OpenHarness plugin
   + Codex/Claude/OpenCode repository skills
   + Symphony/OpenHands orchestration
   + independent build/test/review gate
```

### AI-native web

```text
Vercel AI SDK / AG-UI front end
   ↓
LangGraph / OpenAI Agents / ADK backend
   ↓
MCP/A2A tools
   ↓
Elmos authority, trace, FinOps and certification
```

## Selection anti-patterns

- selecting a framework solely because a model generated familiar code;
- using visual-platform export as the only source of truth;
- hiding durable execution behind an in-memory loop;
- calling a framework's tracing product the independent verifier;
- equating a plugin/skill load with repository task success;
- embedding provider secrets or broad network rights in generated projects;
- generating ten targets when one production target plus one prototype is sufficient;
- claiming universal cross-framework equivalence without feature-level gaps.
