/**
 * Reactive Dependency Directed Acyclic Graph (DAG) Engine.
 * 
 * Computes topological ordering, reactive update cascades, and cycle detection
 * across Props, State, Computed, Effects/Watchers, and Methods for modern frontend components.
 */

import { FullSyntaxProp, FullSyntaxState, FullSyntaxComputed, FullSyntaxEffect, FullSyntaxMethod } from "../types";

export interface ReactiveNode {
  id: string;
  name: string;
  kind: "prop" | "state" | "computed" | "effect" | "method" | "ref";
  dependencies: Set<string>;
  dependents: Set<string>;
  evaluationOrder?: number;
  isCycleParticipant?: boolean;
}

export interface DependencyGraphAnalysis {
  nodes: Map<string, ReactiveNode>;
  topologicalOrder: string[];
  cycles: string[][];
  rootSources: string[];      // Props and States that have no dependencies
  terminalSinks: string[];    // Effects and Render outputs that have no dependents
  maxDepth: number;
}

export class ReactiveDependencyDAG {
  private nodes: Map<string, ReactiveNode> = new Map();

  constructor() {}

  /**
   * Add a reactive node with explicit dependencies.
   */
  public addNode(name: string, kind: ReactiveNode["kind"], deps: string[] = []): void {
    if (!this.nodes.has(name)) {
      this.nodes.set(name, {
        id: `rn_${this.nodes.size + 1}`,
        name,
        kind,
        dependencies: new Set(),
        dependents: new Set(),
      });
    }

    const node = this.nodes.get(name)!;
    for (const dep of deps) {
      if (dep === name) continue; // Ignore self-references for immediate registration
      node.dependencies.add(dep);

      // Ensure dependency node exists in graph
      if (!this.nodes.has(dep)) {
        this.nodes.set(dep, {
          id: `rn_${this.nodes.size + 1}`,
          name: dep,
          kind: "state", // default inferred kind until registered
          dependencies: new Set(),
          dependents: new Set(),
        });
      }
      this.nodes.get(dep)!.dependents.add(name);
    }
  }

  /**
   * Ingest a full set of component members into the reactive graph.
   */
  public ingestComponentMembers(
    props: FullSyntaxProp[],
    states: FullSyntaxState[],
    computed: FullSyntaxComputed[],
    effects: FullSyntaxEffect[],
    methods: FullSyntaxMethod[]
  ): void {
    // 1. Props are pure inputs
    for (const p of props) {
      this.addNode(p.name, "prop");
    }

    // 2. States may have initial value dependencies
    for (const s of states) {
      const initialDeps = this.extractIdentifiersFromExpr(s.initialValueExpr);
      this.addNode(s.name, "state", initialDeps);
    }

    // 3. Computed properties depend on states, props, or other computed
    for (const c of computed) {
      const explicitDeps = c.dependencies.length > 0 ? c.dependencies : this.extractIdentifiersFromExpr(c.expressionOrBody);
      this.addNode(c.name, "computed", explicitDeps);
    }

    // 4. Effects / Watchers depend on declared dependencies or accessed state
    for (const e of effects) {
      const effectName = e.id || `effect_${e.hookKind}_${this.nodes.size}`;
      const explicitDeps = e.dependencies.length > 0 ? e.dependencies : this.extractIdentifiersFromExpr(e.bodyCode);
      this.addNode(effectName, "effect", explicitDeps);
    }

    // 5. Methods may read state/props and invoke other methods
    for (const m of methods) {
      const accessed = this.extractIdentifiersFromExpr(m.bodyCode);
      this.addNode(m.name, "method", accessed);
    }
  }

  /**
   * Perform comprehensive dependency graph analysis, cycle detection, and topological sorting.
   */
  public analyze(): DependencyGraphAnalysis {
    const cycles: string[][] = [];
    const visited = new Set<string>();
    const recursionStack = new Set<string>();
    const currentPath: string[] = [];

    // Cycle detection using Tarjan's / DFS path tracking
    const detectCyclesDFS = (nodeName: string) => {
      visited.add(nodeName);
      recursionStack.add(nodeName);
      currentPath.push(nodeName);

      const node = this.nodes.get(nodeName);
      if (node) {
        for (const dep of node.dependencies) {
          if (!this.nodes.has(dep)) continue;

          if (!visited.has(dep)) {
            detectCyclesDFS(dep);
          } else if (recursionStack.has(dep)) {
            // Cycle detected: extract subpath from dep to current
            const cycleStartIndex = currentPath.indexOf(dep);
            if (cycleStartIndex !== -1) {
              const cycle = currentPath.slice(cycleStartIndex).concat(dep);
              cycles.push(cycle);
              for (const cNode of cycle) {
                const cn = this.nodes.get(cNode);
                if (cn) cn.isCycleParticipant = true;
              }
            }
          }
        }
      }

      currentPath.pop();
      recursionStack.delete(nodeName);
    };

    for (const [name] of this.nodes) {
      if (!visited.has(name)) {
        detectCyclesDFS(name);
      }
    }

    // Topological Sort via Kahn's Algorithm
    const inDegree = new Map<string, number>();
    for (const [name, node] of this.nodes) {
      // Calculate in-degree based on dependencies that are in the graph and not in a broken cycle
      let deg = 0;
      for (const dep of node.dependencies) {
        if (this.nodes.has(dep)) deg++;
      }
      inDegree.set(name, deg);
    }

    const queue: string[] = [];
    const topologicalOrder: string[] = [];

    // Enqueue nodes with in-degree 0 (Sources)
    for (const [name, deg] of inDegree) {
      if (deg === 0) {
        queue.push(name);
      }
    }

    let orderIndex = 0;
    while (queue.length > 0) {
      const current = queue.shift()!;
      topologicalOrder.push(current);
      const node = this.nodes.get(current);
      if (node) {
        node.evaluationOrder = orderIndex++;
        for (const dependent of node.dependents) {
          const currentDeg = inDegree.get(dependent) || 0;
          const nextDeg = currentDeg - 1;
          inDegree.set(dependent, nextDeg);
          if (nextDeg === 0) {
            queue.push(dependent);
          }
        }
      }
    }

    // Identify roots and sinks
    const rootSources: string[] = [];
    const terminalSinks: string[] = [];
    for (const [name, node] of this.nodes) {
      if (node.dependencies.size === 0) {
        rootSources.push(name);
      }
      if (node.dependents.size === 0) {
        terminalSinks.push(name);
      }
    }

    // Compute maximum dependency chain depth
    let maxDepth = 0;
    const depthCache = new Map<string, number>();
    const computeDepth = (name: string, seen: Set<string>): number => {
      if (seen.has(name)) return 0;
      if (depthCache.has(name)) return depthCache.get(name)!;

      const node = this.nodes.get(name);
      if (!node || node.dependencies.size === 0) {
        depthCache.set(name, 1);
        return 1;
      }

      seen.add(name);
      let d = 0;
      for (const dep of node.dependencies) {
        d = Math.max(d, computeDepth(dep, seen));
      }
      seen.delete(name);

      const res = d + 1;
      depthCache.set(name, res);
      return res;
    };

    for (const [name] of this.nodes) {
      maxDepth = Math.max(maxDepth, computeDepth(name, new Set()));
    }

    return {
      nodes: this.nodes,
      topologicalOrder,
      cycles,
      rootSources,
      terminalSinks,
      maxDepth,
    };
  }

  /**
   * Extracts top-level variable identifiers from arbitrary JavaScript/TypeScript expressions.
   */
  private extractIdentifiersFromExpr(code: string): string[] {
    if (!code || !code.trim()) return [];

    const ids: Set<string> = new Set();
    // Match potential identifiers (avoiding JS keywords)
    const matches = code.matchAll(/\b([a-zA-Z_$][a-zA-Z0-9_$]*)\b/g);
    const keywords = new Set([
      "const", "let", "var", "function", "return", "if", "else", "for", "while",
      "do", "switch", "case", "default", "break", "continue", "import", "export",
      "from", "class", "this", "new", "typeof", "instanceof", "in", "of", "void",
      "delete", "true", "false", "null", "undefined", "NaN", "Infinity", "try",
      "catch", "finally", "throw", "async", "await", "yield", "Math", "JSON",
      "console", "Array", "Object", "String", "Number", "Boolean", "Date", "Set",
      "Map", "Promise"
    ]);

    for (const m of matches) {
      const id = m[1];
      if (id && !keywords.has(id) && isNaN(Number(id))) {
        ids.add(id);
      }
    }

    return Array.from(ids);
  }
}
