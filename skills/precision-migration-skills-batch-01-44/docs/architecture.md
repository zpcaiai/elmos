# Architecture

```text
Assessment → Semantic Recovery → Typed/Effect/State IR → Candidate Generation
→ Static/Formal Validation → Target Generation → Differential Runtime
→ Counterexample Repair → Evidence Gate → Shadow/Canary/Cutover
```

控制面保存语义图、规则、任务、模型路由和证据；执行面提供隔离的编译器、Runtime、数据库、浏览器、设备和证明Worker。
