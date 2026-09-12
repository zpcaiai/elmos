# SQL / SQL routine 转换 Domain Pack

## 保证目标
Typed result bag + ordered result when specified + transaction/effect trace

## 首个商业纵向切片
冻结源/目标真实DB版本的一对SQL SELECT子集；存储过程/事务另立route范围

## 核心语义
AST不是完整语义。需要catalog、精确DB版本、SQL modes、timezone、collation、schema约束、UDF与transaction设置。
Comparator明确ordered/bag/set；默认bag，只有规范要求set时才去重。日期/小数/二进制保持类型；NaN/signed-zero按声明处理。
无序LIMIT、随机/时间函数、浮点聚合使用受控时钟/seed或性质与允许结果集合；无法界定则INCONCLUSIVE。
SQLancer用于启发DB oracle/发现引擎bug，不是跨dialect转换认证器。SQLGlot unsupported必须raise或报告，不默默best effort签PASS。
DDL/data migration另检查row count、约束、索引、默认值、权限、触发器/identity与回滚策略；query等价不涵盖迁移正确性。

## 必需验收场景
- **SQL-001** — 空表/重复行/全NULL/混合NULL：比较bag multiplicity和typed NULL，不转空字符串。
- **SQL-002** — 外层x=NULL、内层非NULL非空的NOT IN改写：检测与NOT EXISTS不等价。
- **SQL-003** — DECIMAL边界/舍入/负数/overflow：精确比较或contract批准的舍入，不用通用epsilon。
- **SQL-004** — LEFT JOIN谓词移位：捕获WHERE与ON选择语义差异。
- **SQL-005** — ORDER BY含并列值与分页：要求批准的tie-breaker或声明非确定性，不随意排序掩盖。
- **SQL-006** — routine失败、savepoint、sequence副作用：按真实引擎语义观察；不假设sequence回滚。

## 形式化义务候选
三值逻辑/关系bag受限DSL规则；rewrite充分前提；decimal/类型转换边界。

## 不支持/阻塞
未建模vendor extension/UDF；未验证的procedure异常语义；来源许可/环境缺失的真实DB。

## 成熟度
本包仅SPECIFIED，原生适配与客户认证NOT_RUN。每种确切source/target/feature/environment组合独立晋级；不能用一个语言/DB测试结果覆盖整个矩阵。
