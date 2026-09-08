# 候选适配

reference/elmos_opt/adapters.py只构造ES/pgvector查询和Dify结果，不连接后端。
ES两分支过滤一致，_source=false，hydration复核；生产字段分析、维度、alias、许可与真实版本另测。
PG使用参数绑定和tuple集合，逻辑view名待B0映射；真实查询计划/ANN/过滤召回/OLTP影响另测，不自动DDL。
Dify service身份须映射principal/knowledge scope；归一化score profile事先定义；不得直接映射raw RRF为概率。
LangChain不旁路原网关；LangGraph原生依赖与持久恢复另资格；自制状态机不代替框架原生测试。
需要实际版本/镜像、配置、数据/宿主revision、日志、授权scope、回滚和独立审批后，才可改变candidate状态。
