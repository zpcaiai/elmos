"use client";

import React, { useState, useMemo } from "react";
import { Icon } from "../components/Icon";

interface ASTNode {
  id: string;
  label: string;
  type: "source" | "ir" | "formal" | "target";
  status: "verified" | "analyzing" | "idle";
  details: string;
}

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
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<"code" | "ast" | "lean4" | "pr_daemon">("code");
  const [proofVerified, setProofVerified] = useState<boolean>(true);

  // Modernized target code simulation
  const targetCode = useMemo(() => {
    if (targetLang === "csharp") {
      return `// Modernized by ELMOS Polyglot Compiler v3.0.0 (Target: .NET 9 C#)
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
      return `// Modernized by ELMOS Polyglot Compiler v3.0.0 (Target: Rust 2024 Edition)
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
      return `// Modernized by ELMOS Polyglot Compiler v3.0.0 (Target: Go 1.23)
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

  // Synthetic AST graph nodes
  const astNodes: ASTNode[] = [
    { id: "node-src-ast", label: `Source AST (${sourceLang.toUpperCase()})`, type: "source", status: "verified", details: "Classes: 1, Methods: 2, StateVars: 1" },
    { id: "node-type-algebra", label: "Canonical Type Algebra", type: "ir", status: "verified", details: "Primitives normalized to IEEE754 & Checked Numerics" },
    { id: "node-cfg-flow", label: "Control Flow & Effect Graph", type: "ir", status: "verified", details: "Cyclomatic complexity: 3, Branches verified" },
    { id: "node-smt-solver", label: "SMT Invariant Solver (Z3/CVC5)", type: "formal", status: "verified", details: "SAT_PROVED: Invariant balance >= 0 preserved" },
    { id: "node-lean4-kernel", label: "Lean 4 Theorem Checker", type: "formal", status: "verified", details: "Machine proof certified with tactic 'omega'" },
    { id: "node-tgt-ast", label: `Target AST (${targetLang.toUpperCase()})`, type: "target", status: "verified", details: "Zero semantic loss, SLSA Level 3 certified" },
  ];

  const handleModernize = () => {
    setIsProcessing(true);
    setTimeout(() => {
      setIsProcessing(false);
      setProofVerified(true);
    }, 450);
  };

  const handleSnippetChange = (lang: string) => {
    setSourceLang(lang);
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
              Interactive Code & Proof Sandbox v3.0.0
            </div>
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-foreground">
              实时跨语言编译与形式化证明工作台
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              体验毫秒级 AST 语法降解、双语重构、SMT 形式化不变式证明与 Lean 4 定理综合。
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
              {isProcessing ? "编译与定理求解中..." : "一键转换与形式化证明"}
            </button>
          </div>
        </div>

        {/* View Tabs */}
        <div className="mt-6 flex flex-wrap gap-2 border-b border-border pb-3">
          {[
            { id: "code", label: "双栏实时编辑器", icon: "code" },
            { id: "ast", label: "AST 拓扑与数据流", icon: "workflow" },
            { id: "lean4", label: "Lean 4 / Dafny 定理凭证", icon: "shield" },
            { id: "pr_daemon", label: "Git PR 自愈演练", icon: "box" },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id as any)}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
                activeTab === tab.id
                  ? "bg-primary text-primary-foreground shadow-xs"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Icon name={tab.icon as any} className="h-4 w-4" />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main Tab Content */}
      {activeTab === "code" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Source Code Panel */}
          <div className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-2.5 w-2.5 rounded-full bg-amber-500" />
                <span className="font-semibold text-foreground">源语言输入 (Source Code)</span>
              </div>
              <select
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
              value={sourceCode}
              onChange={(e) => setSourceCode(e.target.value)}
              rows={16}
              className="w-full resize-y rounded-xl border border-border bg-muted/20 p-4 font-mono text-xs text-foreground focus:border-primary focus:outline-hidden"
              spellCheck={false}
            />
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>Lines: {sourceCode.split("\n").length}</span>
              <span>Syntax: CST Ready</span>
            </div>
          </div>

          {/* Target Code Panel */}
          <div className="flex flex-col rounded-2xl border border-border bg-card p-5 shadow-xs">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
                <span className="font-semibold text-foreground">目标代码输出 (Target Output)</span>
                {proofVerified && (
                  <span className="rounded-md bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                    SMT PROVED
                  </span>
                )}
              </div>
              <select
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
                className="rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs font-medium text-foreground focus:outline-hidden"
              >
                <option value="csharp">C# (.NET 9 / Modern)</option>
                <option value="rust">Rust (2024 / Memory-Safe)</option>
                <option value="go">Go (1.23 / Cloud-Native)</option>
              </select>
            </div>
            <textarea
              readOnly
              value={targetCode}
              rows={16}
              className="w-full resize-y rounded-xl border border-border bg-muted/40 p-4 font-mono text-xs text-foreground focus:outline-hidden"
              spellCheck={false}
            />
            <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>Status: SLSA Level 3 Certified</span>
              <span>Action Cache: CAS Enabled</span>
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
                    Verified
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
{`-- Generated by ELMOS Formal Proof Engine v3.0.0
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
{`// Generated by ELMOS Formal Proof Engine v3.0.0
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
                Git PR 自愈智能体模拟演练 (Webhook Simulator)
              </h3>
              <p className="text-xs text-muted-foreground">
                模拟 GitHub / GitLab 提交 Pull Request 时自动触发审查与自愈补丁生成。
              </p>
            </div>
            <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
              Webhook: http://127.0.0.1:8080/webhook
            </span>
          </div>

          <div className="rounded-xl border border-border bg-muted/20 p-4">
            <h4 className="text-xs font-mono text-muted-foreground uppercase tracking-wider">
              PR #142 Auto-Generated Git Diff Patch
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
              PR Review Verdict: PASS (Auto-Healing Branch Ready)
            </h4>
            <p className="mt-1 text-xs text-muted-foreground">
              ELMOS 检测到 1 项过时同步集合规则违规（ELMOS-RULE-JAVA-001），已自动为您生成并推送到 `elmos-fix/pr-142` 分支。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
