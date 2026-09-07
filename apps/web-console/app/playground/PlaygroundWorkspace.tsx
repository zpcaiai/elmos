"use client";

import React, { useMemo, useState } from "react";
import { Icon, type IconName } from "../components/Icon";

type PlaygroundTab = "code" | "ast" | "lean4" | "pr_daemon";
type ExecutionState = "NOT_RUN" | "CHECKING" | "BLOCKED";

interface ASTNode {
  id: string;
  label: string;
  type: "source" | "ir" | "formal" | "target";
  status: "not-run";
  details: string;
}

const PLAYGROUND_TABS: ReadonlyArray<{
  id: PlaygroundTab;
  label: string;
  icon: IconName;
}> = [
  { id: "code", label: "双栏示例编辑器", icon: "code" },
  { id: "ast", label: "AST 拓扑要求（未执行）", icon: "workflow" },
  { id: "lean4", label: "Lean 4 / Dafny 规格示例", icon: "shield" },
  { id: "pr_daemon", label: "Git PR 演练示例", icon: "box" },
];

const DEFAULT_JAVA_SNIPPET = `public class AccountService {
    private double balance;

    public void deposit(double amount) {
        if (amount > 0) {
            this.balance += amount;
        }
    }

    public boolean withdraw(double amount) {
        if (amount > 0 && this.balance >= amount) {
            this.balance -= amount;
            return true;
        }
        return false;
    }
}`;

const SAMPLE_SNIPPETS: Record<string, string> = {
  java: DEFAULT_JAVA_SNIPPET,
  csharp: `public class OrderProcessor {
    public string OrderId { get; set; }
    public decimal TotalAmount { get; set; }

    public void Process() {
        if (TotalAmount >= 0) {
            Console.WriteLine($"Processing {OrderId}");
        }
    }
}`,
  cobol: `       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELLO-ACCT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-BALANCE PIC 9(7)V99 VALUE 1000.00.
       PROCEDURE DIVISION.
           DISPLAY 'CURRENT BALANCE: ' WS-BALANCE.
           STOP RUN.`,
};

export function PlaygroundWorkspace() {
  const [sourceLang, setSourceLang] = useState<string>("java");
  const [targetLang, setTargetLang] = useState<string>("csharp");
  const [sourceCode, setSourceCode] = useState<string>(DEFAULT_JAVA_SNIPPET);
  const [executionState, setExecutionState] = useState<ExecutionState>("NOT_RUN");
  const [executionMessage, setExecutionMessage] = useState(
    "当前页面仅展示静态输入、目标与规格示例；尚未连接真实转换、SMT、Lean、SCM 或签名 Runner。",
  );
  const [activeTab, setActiveTab] = useState<PlaygroundTab>("code");
  const isProcessing = executionState === "CHECKING";

  // This is deliberately a static example. It is never presented as output
  // derived from sourceCode and never contributes execution evidence.
  const targetCode = useMemo(() => {
    if (targetLang === "csharp") {
      return `// STATIC EXAMPLE ONLY — NOT GENERATED FROM THE SOURCE INPUT
// Execution: NOT_RUN · Certification: NOT_CERTIFIED
public class AccountService
{
    public double Balance { get; private set; }

    public void Deposit(double amount)
    {
        if (amount > 0)
        {
            Balance += amount;
        }
    }

    public bool Withdraw(double amount)
    {
        if (amount > 0 && Balance >= amount)
        {
            Balance -= amount;
            return true;
        }
        return false;
    }
}`;
    } else if (targetLang === "rust") {
      return `// STATIC EXAMPLE ONLY — NOT GENERATED FROM THE SOURCE INPUT
// Execution: NOT_RUN · Certification: NOT_CERTIFIED
pub struct AccountService {
    balance: f64,
}

impl AccountService {
    pub fn new() -> Self {
        Self { balance: 0.0 }
    }

    pub fn deposit(&mut self, amount: f64) {
        if amount > 0.0 {
            self.balance += amount;
        }
    }

    pub fn withdraw(&mut self, amount: f64) -> bool {
        if amount > 0.0 && self.balance >= amount {
            self.balance -= amount;
            true
        } else {
            false
        }
    }
}`;
    } else {
      return `// STATIC EXAMPLE ONLY — NOT GENERATED FROM THE SOURCE INPUT
// Execution: NOT_RUN · Certification: NOT_CERTIFIED
package account

type AccountService struct {
    balance float64
}

func (s *AccountService) Deposit(amount float64) {
    if amount > 0 {
        s.balance += amount
    }
}

func (s *AccountService) Withdraw(amount float64) bool {
    if amount > 0 && s.balance >= amount {
        s.balance -= amount
        return true
    }
    return false
}`;
    }
  }, [targetLang]);

  // Planned stages are an explanatory graph, not a replay or proof receipt.
  const astNodes: ASTNode[] = [
    { id: "node-src-ast", label: `Source AST (${sourceLang.toUpperCase()})`, type: "source", status: "not-run", details: "Parser invocation and AST counts are NOT_RUN." },
    { id: "node-type-algebra", label: "Canonical Type Algebra", type: "ir", status: "not-run", details: "Type normalization is a planned obligation; no IR artifact exists." },
    { id: "node-cfg-flow", label: "Control Flow & Effect Graph", type: "ir", status: "not-run", details: "CFG and effect analysis have not executed." },
    { id: "node-smt-solver", label: "SMT Invariant Solver (Z3/CVC5)", type: "formal", status: "not-run", details: "No solver was invoked and no SAT/UNSAT verdict exists." },
    { id: "node-lean4-kernel", label: "Lean 4 Theorem Checker", type: "formal", status: "not-run", details: "No theorem artifact was checked by a Lean kernel." },
    { id: "node-tgt-ast", label: `Target AST (${targetLang.toUpperCase()})`, type: "target", status: "not-run", details: "No target AST, build, provenance, or certification was produced." },
  ];

  const handleModernize = () => {
    setExecutionState("CHECKING");
    setExecutionMessage("正在检查真实 Runner 是否已绑定；不会生成模拟证明或认证状态。");
    setTimeout(() => {
      setExecutionState("BLOCKED");
      setExecutionMessage(
        "BLOCKED：此示例页未绑定真实转换、形式化验证、独立签名或 SCM Runner；执行保持 NOT_RUN，认证保持 NOT_CERTIFIED。",
      );
    }, 450);
  };

  const resetExecution = () => {
    setExecutionState("NOT_RUN");
    setExecutionMessage("输入或目标已变化；尚未执行转换、证明、构建、签名或发布。");
  };

  const handleSnippetChange = (lang: string) => {
    setSourceLang(lang);
    resetExecution();
    if (SAMPLE_SNIPPETS[lang]) {
      setSourceCode(SAMPLE_SNIPPETS[lang]);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              <Icon name="spark" className="h-3.5 w-3.5" />
              Static workbench preview · NOT_RUN
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-foreground">
              跨语言转换与形式化验证准备工作台
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              编辑输入、查看目标与证明规格示例；真实执行和证据只由受控 Runner 与独立门禁产生。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleModernize}
              disabled={isProcessing}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-50"
            >
              <Icon name="spark" className={`h-4 w-4 ${isProcessing ? "animate-spin" : ""}`} />
              {isProcessing ? "检查 Runner 绑定中..." : "检查真实执行条件"}
            </button>
          </div>
        </div>

        {/* View Tabs */}
        <div className="mt-6 flex flex-wrap gap-2 border-b border-border pb-3">
          {PLAYGROUND_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              aria-pressed={activeTab === tab.id}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
                activeTab === tab.id
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon name={tab.icon} className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div
        role="status"
        aria-live="polite"
        className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"
      >
        <strong>{executionState}</strong> · {executionMessage}
      </div>

      {/* Main Tab Content */}
      {activeTab === "code" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Source Code Panel */}
          <div className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-2.5 w-2.5 rounded-full bg-amber-500" />
                <label htmlFor="playground-source-code" className="font-semibold text-foreground">源语言输入 (Source Code)</label>
              </div>
              <select
                id="playground-source-language"
                aria-label="源语言"
                value={sourceLang}
                onChange={(e) => handleSnippetChange(e.target.value)}
                className="rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground focus:outline-hidden"
              >
                <option value="java">Java (Spring / Enterprise)</option>
                <option value="csharp">C# (.NET Core)</option>
                <option value="cobol">COBOL (Mainframe / IBM)</option>
              </select>
            </div>
            <textarea
              id="playground-source-code"
              aria-label="源代码输入"
              value={sourceCode}
              onChange={(e) => {
                setSourceCode(e.target.value);
                resetExecution();
              }}
              rows={16}
              className="w-full resize-y rounded-xl border border-border bg-muted/20 p-4 font-mono text-xs text-foreground focus:border-primary focus:outline-hidden"
              spellCheck={false}
            />
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>Lines: {sourceCode.split("\n").length}</span>
              <span>Parser: NOT_RUN</span>
            </div>
          </div>

          {/* Target Code Panel */}
          <div className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                <label htmlFor="playground-target-code" className="font-semibold text-foreground">静态目标示例（非转换结果）</label>
                <span className="rounded-md bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                  NOT_RUN
                </span>
              </div>
              <select
                id="playground-target-language"
                aria-label="目标语言"
                value={targetLang}
                onChange={(e) => {
                  setTargetLang(e.target.value);
                  resetExecution();
                }}
                className="rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground focus:outline-hidden"
              >
                <option value="csharp">C# (.NET 9 / Modern)</option>
                <option value="rust">Rust (2024 / Memory-Safe)</option>
                <option value="go">Go (1.23 / Cloud-Native)</option>
              </select>
            </div>
            <textarea
              id="playground-target-code"
              aria-label="静态目标代码示例"
              readOnly
              value={targetCode}
              rows={16}
              className="w-full resize-y rounded-xl border border-border bg-muted/40 p-4 font-mono text-xs text-foreground focus:outline-hidden"
              spellCheck={false}
            />
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>Execution: NOT_RUN</span>
              <span>Certification: NOT_CERTIFIED</span>
            </div>
          </div>
        </div>
      )}

      {/* AST Topology Graph */}
      {activeTab === "ast" && (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-xs">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-base font-semibold text-foreground">
              多阶段语法语义拓扑与不变式传递链
            </h3>
            <span className="text-xs text-muted-foreground">Graph: Acyclic Transformation DAG</span>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {astNodes.map((node, idx) => (
              <div
                key={node.id}
                className="relative flex flex-col rounded-xl border border-border/80 bg-muted/20 p-4 transition hover:border-primary/50"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-muted-foreground">Step 0{idx + 1}</span>
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                    <Icon name="test" className="h-3 w-3" />
                    NOT_RUN
                  </span>
                </div>
                <h4 className="mt-2 text-sm font-semibold text-foreground">{node.label}</h4>
                <p className="mt-1 text-xs text-muted-foreground">{node.details}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Lean 4 & Dafny Spec Tab */}
      {activeTab === "lean4" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Lean 4 Specification */}
          <div className="rounded-2xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-semibold text-foreground">Lean 4 形式化定理规格 (.lean)</span>
              <span className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-mono text-primary">
                Lean 4.8.0 Kernel
              </span>
            </div>
            <pre className="rounded-xl border border-border bg-muted/30 p-4 font-mono text-xs text-foreground overflow-x-auto">
{`-- SPECIFICATION EXAMPLE ONLY — NOT GENERATED OR CHECKED
import Mathlib.Data.Real.Basic

theorem PreserveNonNegativeBalance 
  (balance : Real) (amount : Real)
  (h_pos : amount > 0)
  (h_sufficient : balance >= amount) :
  balance - amount >= 0 := by
  intro h1 h2
  omega`}
            </pre>
          </div>

          {/* Dafny Specification */}
          <div className="rounded-2xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-semibold text-foreground">Dafny 严密方法契约 (.dfy)</span>
              <span className="rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-mono text-emerald-600 dark:text-emerald-400">
                Dafny 4.4.0
              </span>
            </div>
            <pre className="rounded-xl border border-border bg-muted/30 p-4 font-mono text-xs text-foreground overflow-x-auto">
{`// SPECIFICATION EXAMPLE ONLY — NOT GENERATED OR VERIFIED
method {:verify true} Withdraw(balance: int, amount: int) returns (newBal: int, ok: bool)
  requires balance >= 0
  requires amount > 0
  ensures ok ==> newBal == balance - amount && newBal >= 0
  ensures !ok ==> newBal == balance
{
  if balance >= amount {
    newBal := balance - amount;
    ok := true;
  } else {
    newBal := balance;
    ok := false;
  }
}`}
            </pre>
          </div>
        </div>
      )}

      {/* PR Daemon Simulation Tab */}
      {activeTab === "pr_daemon" && (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-foreground">
                Git PR 自愈流程静态示例
              </h3>
              <p className="text-xs text-muted-foreground">
                仅展示预期补丁形状；未接收 Webhook、未创建分支、未推送或审批 Pull Request。
              </p>
            </div>
            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              SCM EFFECTS: NOT_RUN
            </span>
          </div>

          <div className="rounded-xl border border-border bg-muted/20 p-4">
            <h4 className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
              Illustrative Git Diff (not generated)
            </h4>
            <pre className="mt-2 text-xs font-mono text-foreground overflow-x-auto">
{`--- a/src/main/java/LegacyAccount.java
+++ b/src/main/java/LegacyAccount.java
@@ -1,3 +1,3 @@
 public class LegacyAccount {
-  public Vector<String> history = new Vector<>();
+  public List<String> history = new ArrayList<>();
 }`}
            </pre>
          </div>

          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4">
            <h4 className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
              SAMPLE_ONLY · Review NOT_RUN
            </h4>
            <p className="mt-1 text-xs text-muted-foreground">
              此示例没有执行规则检查，也没有创建或推送 `elmos-fix/pr-142` 分支；需要 SCM 授权、Runner 回执和独立复核后才能产生真实结论。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
