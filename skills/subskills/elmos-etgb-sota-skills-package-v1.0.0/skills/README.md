# ETGB Skills

入口 Skill 为 `etgb-orchestrator`。业务线 Skill 只负责领域验证；隐藏测试、Oracle 和发布判定分离，以防生成/转换 Agent 修改自己的验收标准。

`manifest.yaml` 声明依赖关系，可导入 Elmos Skill Registry。部署时应把读取 hidden tests、批准语料、签发 release 的权限分配给不同 execution environment/role。
