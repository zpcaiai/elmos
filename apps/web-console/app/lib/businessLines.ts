import type {
  DirectedLanguageRoute,
  SpringModernizationStage,
  TranslationLanguage,
  TranslationLanguageId,
} from "./contracts";

export const springModernizationStages: SpringModernizationStage[] = [
  { id: "discover", title: "识别旧工程", detail: "读取依赖、XML、注解、web.xml 与有效版本", status: "READY", requiredEvidence: "源快照、有效 POM/Gradle 模型、框架指纹" },
  { id: "baseline", title: "建立源基线", detail: "真实构建、启动、端点、安全与数据行为", status: "NOT_RUN", requiredEvidence: "源版本构建日志、启动探针、契约测试" },
  { id: "contract", title: "提取 FCM", detail: "固化 Web、DI、配置、安全、事务与生命周期", status: "REVIEW", requiredEvidence: "FCM 实体、来源映射、未决义务" },
  { id: "upgrade", title: "依赖序升级", detail: "Java、Jakarta、Security、JPA 与配置配方", status: "REVIEW", requiredEvidence: "精确配方摘要、受保护区域、升级差异" },
  { id: "verify", title: "目标验证", detail: "构建、启动、端点、持久化与关闭探针", status: "NOT_RUN", requiredEvidence: "Java 21 / Boot 3.5.3 真实运行证据" },
  { id: "release", title: "回滚与交付", detail: "独立 holdout、回滚说明与保守门禁", status: "BLOCKED", requiredEvidence: "独立验证者、holdout、Batch 30 Gate" },
];

export const translationLanguages: TranslationLanguage[] = [
  { id: "java", label: "Java", compiler: "Java 21.0.11 / JDK Tree API", runtime: "JVM 21.0.11", enginePath: "engines/polyglot-route-engine/native/java/Analyzer.java" },
  { id: "csharp", label: "C#", compiler: ".NET SDK 10.0.301 / Roslyn 5.6.0", runtime: ".NET 10", enginePath: "engines/dotnet-engine/src/Elmos.Dotnet.SemanticCli" },
  { id: "go", label: "Go", compiler: "Go 1.25.0 / go/parser AST", runtime: "Go 1.25.0", enginePath: "engines/polyglot-route-engine/native/go/analyzer.go" },
  { id: "rust", label: "Rust", compiler: "rustc 1.89.0 / syn AST 2.0.119", runtime: "Rust 1.89.0", enginePath: "engines/polyglot-route-engine/native/rust/src/main.rs" },
  { id: "python", label: "Python", compiler: "CPython AST 3.12.12", runtime: "CPython 3.12.12", enginePath: "engines/polyglot-route-engine/src/elmos_polyglot_route/python_analyzer.py" },
  { id: "typescript", label: "TypeScript", compiler: "TypeScript 5.9.2 Compiler API", runtime: "Node.js 26.0.0", enginePath: "engines/frontend-client-engine/src/polyglot.ts" },
];

const sourceHazards: Record<TranslationLanguageId, string[]> = {
  java: ["泛型擦除、checked exception 与反射", "同步、线程与内存模型", "注解、序列化与类加载"],
  csharp: ["值类型、nullable 与 decimal", "LINQ、委托、事件与 async/await", "attribute、reflection 与 disposal"],
  go: ["接口方法集、nil 与零值", "goroutine、channel 与内存模型", "defer、panic/recover 与构建标签"],
  rust: ["所有权、借用与生命周期", "trait、泛型与模式匹配", "unsafe、并发与 panic 语义"],
  python: ["动态属性、MRO 与 duck typing", "truthiness、任意精度整数与生成器", "装饰器、元类、运行时导入与原生扩展"],
  typescript: ["结构类型、联合/交叉类型", "undefined/null 与 number 精度", "Promise 事件循环、原型与运行时类型守卫"],
};

const targetHazards: Record<TranslationLanguageId, string[]> = {
  java: ["目标必须使用名义类型且不退化为 Object", "对象图、异常、框架与并发不属于当前纯函数 profile"],
  csharp: ["目标必须显式表达 nullable/Task/decimal", "Task、事件、资源释放与框架不属于当前纯函数 profile"],
  go: ["目标必须显式处理 nil、错误值与整数宽度", "goroutine、channel、defer 与 I/O 不属于当前纯函数 profile"],
  rust: ["目标必须显式表达所有权、借用与溢出策略", "trait、unsafe、async 与 I/O 不属于当前纯函数 profile"],
  python: ["目标类型证据与运行时约束必须分开", "动态对象、装饰器、导入副作用不属于当前纯函数 profile"],
  typescript: ["目标必须区分 null、undefined 与缺失属性", "Promise、原型、I/O 与框架不属于当前纯函数 profile"],
};

export function translationHazards(
  source: TranslationLanguageId,
  target: TranslationLanguageId,
): string[] {
  return [...sourceHazards[source], ...targetHazards[target]].slice(0, 4);
}

/**
 * Editorial shape only. Route readiness is owned by `routes/inventory.json` and
 * is served by `/api/capabilities/translation`; until that contract has been
 * read, every status here stays NOT_RUN so an offline console can never render
 * a local pass it has not observed.
 */
export const directedLanguageRoutes: DirectedLanguageRoute[] = translationLanguages.flatMap((source) =>
  translationLanguages
    .filter((target) => target.id !== source.id)
    .map((target) => ({
      id: `${source.id}-to-${target.id}`,
      source: source.id,
      target: target.id,
      skill: `b29-certify-${source.id}-to-${target.id}`,
      status: "BLOCKED" as const,
      readiness: "NOT_RUN" as const,
      localExecution: "NOT_RUN" as const,
      independentVerification: "NOT_RUN" as const,
      externalVerification: "NOT_RUN" as const,
      sourceVersion: "UNKNOWN",
      targetVersion: "UNKNOWN",
      hazards: translationHazards(source.id, target.id),
      blockers: [
        "路线能力契约尚未读取；本地执行状态在读取 routes/inventory.json 之前保持 NOT_RUN",
        "仅支持 typed-pure-function-v1：显式基本类型、if、return 与受限二元运算",
        "对象图、异常、async、I/O、反射、框架、数据库与并发必须拆到精确 Pack",
      ],
    })),
);
