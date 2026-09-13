/**
 * Directive Decision Tree & Conditional Lowering Engine.
 * 
 * Analyzes arbitrary nested boolean conditions (ternaries, logical &&/|| cascades,
 * Vue v-if/v-else-if/v-else chains, Angular *ngIf and ngSwitch, Svelte {#if} blocks)
 * and normalizes them into non-overlapping, deterministic AST decision trees.
 */

import { FullSyntaxNode } from "../types";

export interface DecisionBranch {
  conditionExpr: string;
  node: FullSyntaxNode;
  isNegated?: boolean;
}

export interface DecisionTree {
  id: string;
  branches: DecisionBranch[];
  fallbackNode?: FullSyntaxNode;
}

export class DirectiveDecisionTreeEngine {
  /**
   * Transforms arbitrary nested conditional expressions into a normalized DecisionTree.
   */
  public static normalizeCondition(node: FullSyntaxNode): DecisionTree {
    const branches: DecisionBranch[] = [];
    let fallbackNode: FullSyntaxNode | undefined = undefined;

    if (node.condition) {
      // Primary branch
      branches.push({
        conditionExpr: this.cleanExpression(node.condition.test),
        node: node.condition.thenNode,
      });

      // Elif branches if present
      if (node.condition.elifBranches) {
        for (const b of node.condition.elifBranches) {
          branches.push({
            conditionExpr: this.cleanExpression(b.test),
            node: b.node,
          });
        }
      }

      // Else branch: may itself be another conditional node (nested ternary unrolling)
      if (node.condition.elseNode) {
        if (node.condition.elseNode.kind === "conditional" || node.condition.elseNode.condition) {
          const nested = this.normalizeCondition(node.condition.elseNode);
          branches.push(...nested.branches);
          fallbackNode = nested.fallbackNode;
        } else {
          fallbackNode = node.condition.elseNode;
        }
      }
    }

    return {
      id: `dt_${Math.random().toString(36).substring(2, 9)}`,
      branches,
      fallbackNode,
    };
  }

  /**
   * Lowers a JSX nested ternary expression AST into FullSyntaxNode conditional branches.
   * e.g., `isLoading ? <Spinner /> : isError ? <ErrorView /> : <Content />`
   */
  public static parseTernaryExpressionToNode(
    testExpr: string,
    consequentNode: FullSyntaxNode,
    alternateNode: FullSyntaxNode
  ): FullSyntaxNode {
    // If alternate is itself a conditional, unroll recursively
    if (alternateNode.kind === "conditional" && alternateNode.condition) {
      const nested = this.normalizeCondition(alternateNode);
      return {
        id: `cond_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
        kind: "conditional",
        condition: {
          test: this.cleanExpression(testExpr),
          thenNode: consequentNode,
          elifBranches: nested.branches.map(b => ({ test: b.conditionExpr, node: b.node })),
          elseNode: nested.fallbackNode,
        },
      };
    }

    return {
      id: `cond_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      kind: "conditional",
      condition: {
        test: this.cleanExpression(testExpr),
        thenNode: consequentNode,
        elseNode: alternateNode,
      },
    };
  }

  /**
   * Lowers logical AND cascade (e.g. `isValid && isAuthorized && <AdminPanel />`)
   * into an atomic condition test.
   */
  public static parseLogicalAndToNode(
    conditions: string[],
    consequentNode: FullSyntaxNode
  ): FullSyntaxNode {
    const combinedTest = conditions
      .map(c => this.cleanExpression(c))
      .filter(c => c.length > 0)
      .join(" && ");

    return {
      id: `cond_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
      kind: "conditional",
      condition: {
        test: combinedTest,
        thenNode: consequentNode,
      },
    };
  }

  /**
   * Converts a normalized DecisionTree to WeChat MiniApp WXML `<block wx:if>` sequence.
   */
  public static emitToWxmlDecisionBlocks(
    tree: DecisionTree,
    nodeRenderer: (node: FullSyntaxNode) => string
  ): string {
    const lines: string[] = [];

    tree.branches.forEach((branch, idx) => {
      const directive = idx === 0 ? "wx:if" : "wx:elif";
      const sanitizedCond = this.sanitizeForWxmlBinding(branch.conditionExpr);
      lines.push(`<block ${directive}="{{${sanitizedCond}}}">`);
      lines.push(`  ${nodeRenderer(branch.node).trim()}`);
      lines.push(`</block>`);
    });

    if (tree.fallbackNode) {
      lines.push(`<block wx:else>`);
      lines.push(`  ${nodeRenderer(tree.fallbackNode).trim()}`);
      lines.push(`</block>`);
    }

    return lines.join("\n");
  }

  /**
   * Converts a normalized DecisionTree to Vue 3 `<template v-if/v-else-if/v-else>` sequence.
   */
  public static emitToVueTemplateBlocks(
    tree: DecisionTree,
    nodeRenderer: (node: FullSyntaxNode) => string
  ): string {
    const lines: string[] = [];

    tree.branches.forEach((branch, idx) => {
      const directive = idx === 0 ? "v-if" : "v-else-if";
      lines.push(`<template ${directive}="${branch.conditionExpr}">`);
      lines.push(`  ${nodeRenderer(branch.node).trim()}`);
      lines.push(`</template>`);
    });

    if (tree.fallbackNode) {
      lines.push(`<template v-else>`);
      lines.push(`  ${nodeRenderer(tree.fallbackNode).trim()}`);
      lines.push(`</template>`);
    }

    return lines.join("\n");
  }

  /**
   * Sanitizes expression syntax for WXML double curly mustache interpolation.
   * Prevents XML attribute breaking quotes and unescaped entities.
   */
  private static sanitizeForWxmlBinding(expr: string): string {
    let res = expr.trim();
    // In WXML attributes: attr="{{ ... }}", inner double quotes MUST become single quotes
    res = res.replace(/"/g, "'");
    return res;
  }

  private static cleanExpression(expr: string): string {
    let res = expr.trim();
    if (res.startsWith("(") && res.endsWith(")")) {
      // Check balanced outermost parentheses
      let depth = 0;
      let isBalancedOutermost = true;
      for (let i = 0; i < res.length - 1; i++) {
        if (res[i] === "(") depth++;
        else if (res[i] === ")") depth--;
        if (depth === 0) {
          isBalancedOutermost = false;
          break;
        }
      }
      if (isBalancedOutermost) {
        res = res.slice(1, -1).trim();
      }
    }
    return res;
  }
}
