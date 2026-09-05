export type RouteParams = Record<string, string | string[] | undefined>;

export type RouteMatch<T> = {
  readonly value: T;
  readonly params: RouteParams;
};

type Segment =
  | { readonly kind: "static"; readonly value: string }
  | { readonly kind: "dynamic"; readonly name: string }
  | { readonly kind: "catch-all"; readonly name: string; readonly optional: boolean };

export type CompiledRoute<T> = {
  readonly template: string;
  readonly value: T;
  readonly segments: readonly Segment[];
  readonly score: readonly number[];
};

function compileSegment(segment: string): Segment {
  const optionalCatchAll = /^\[\[\.\.\.([A-Za-z][A-Za-z0-9_]*)\]\]$/.exec(segment);
  if (optionalCatchAll) {
    return { kind: "catch-all", name: optionalCatchAll[1], optional: true };
  }
  const catchAll = /^\[\.\.\.([A-Za-z][A-Za-z0-9_]*)\]$/.exec(segment);
  if (catchAll) {
    return { kind: "catch-all", name: catchAll[1], optional: false };
  }
  const dynamic = /^\[([A-Za-z][A-Za-z0-9_]*)\]$/.exec(segment);
  if (dynamic) {
    return { kind: "dynamic", name: dynamic[1] };
  }
  if (!segment || segment.includes("[") || segment.includes("]")) {
    throw new Error(`INVALID_API_ROUTE_SEGMENT:${segment}`);
  }
  return { kind: "static", value: segment };
}

export function compileRoutes<T>(entries: readonly { template: string; value: T }[]): readonly CompiledRoute<T>[] {
  const seen = new Set<string>();
  const routes = entries.map((entry) => {
    if (!entry.template || seen.has(entry.template)) {
      throw new Error(`DUPLICATE_OR_EMPTY_API_ROUTE:${entry.template}`);
    }
    seen.add(entry.template);
    const segments = entry.template.split("/").map(compileSegment);
    const catchAllIndex = segments.findIndex((segment) => segment.kind === "catch-all");
    if (catchAllIndex >= 0 && catchAllIndex !== segments.length - 1) {
      throw new Error(`NON_TERMINAL_API_CATCH_ALL:${entry.template}`);
    }
    return {
      ...entry,
      segments,
      score: segments.map((segment) => segment.kind === "static" ? 3 : segment.kind === "dynamic" ? 2 : 1),
    };
  });
  return routes.sort((left, right) => {
    const length = Math.max(left.score.length, right.score.length);
    for (let index = 0; index < length; index += 1) {
      const difference = (right.score[index] ?? 0) - (left.score[index] ?? 0);
      if (difference !== 0) return difference;
    }
    return right.segments.length - left.segments.length;
  });
}

export function matchRoute<T>(path: readonly string[], routes: readonly CompiledRoute<T>[]): RouteMatch<T> | null {
  for (const route of routes) {
    const params: RouteParams = {};
    let pathIndex = 0;
    let matched = true;
    for (const segment of route.segments) {
      if (segment.kind === "catch-all") {
        const rest = path.slice(pathIndex);
        if (!segment.optional && rest.length === 0) {
          matched = false;
        } else {
          params[segment.name] = rest.length === 0 ? undefined : [...rest];
          pathIndex = path.length;
        }
        break;
      }
      const current = path[pathIndex];
      if (current === undefined || (segment.kind === "static" && current !== segment.value)) {
        matched = false;
        break;
      }
      if (segment.kind === "dynamic") params[segment.name] = current;
      pathIndex += 1;
    }
    if (matched && pathIndex === path.length) return { value: route.value, params };
  }
  return null;
}
