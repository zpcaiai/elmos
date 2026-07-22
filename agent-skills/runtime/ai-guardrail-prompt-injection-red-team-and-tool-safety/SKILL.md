---
name: ai-guardrail-prompt-injection-red-team-and-tool-safety
description: 建立输入、检索、模型输出、工具调用、数据泄漏和Agent行为的多层Guardrail与红队评测。
---

# AI Safety and Guardrails

## Guardrail层

USER_INPUT
PROMPT_ASSEMBLY
RETRIEVED_CONTEXT
MODEL_INPUT
MODEL_OUTPUT
TOOL_INPUT
TOOL_OUTPUT
MEMORY_WRITE
FINAL_RESPONSE
SIDE_EFFECT

## 风险

Prompt Injection
Indirect Injection
Jailbreak
Sensitive Disclosure
Insecure Output
Tool Abuse
Excessive Agency
Data Poisoning
Model Denial of Service
Supply Chain
Misinformation
Overreliance

OWASP的2025 LLM应用Top 10提供了生成式AI应用风险基线，涵盖Prompt Injection、敏感信息泄漏、供应链、数据与模型Poisoning、不当输出处理、过度代理和无限资源消耗等问题；具体版本必须进入ELMOS Risk Profile。

## Guardrail类型

DETERMINISTIC
CLASSIFIER
LLM_BASED
POLICY
ALLOWLIST
DENYLIST
SCHEMA
SANDBOX
HUMAN
RATE_LIMIT
BUDGET

## Prompt Injection

检查：

- 用户输入；
- 网页；
- 文档；
- 邮件；
- Tool Result；
- Memory；
- Agent Message。

Retrieved Document必须视为：
