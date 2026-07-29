"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import type { UserActivityEvent } from "../lib/operationsContracts";
import {
  bucketDuration,
  normalizeTelemetryRoute,
  routeBusinessLine,
  telemetrySchemaVersion,
  type ConsoleTelemetryEvent,
  type TelemetryOutcome,
  type TelemetryTargetKind,
} from "../lib/telemetry/contracts";

const ENDPOINT = "/api/telemetry/events";
const STORAGE_KEY = "elmos:user-activity-queue:v1";
const SESSION_KEY = "elmos:user-activity-session:v1";
const PREFERENCE_KEY = "elmos:telemetry-enabled:v1";
const MAX_QUEUE = 200;
const BATCH_SIZE = 20;
const FLUSH_INTERVAL_MS = 2_000;

let collectorInstalled = false;

function businessLine(pathname: string): string {
  if (pathname.startsWith("/spring")) return "SPRING_MODERNIZATION";
  if (pathname.startsWith("/translation")) return "LANGUAGE_TRANSLATION";
  if (pathname.startsWith("/generation")) return "PROJECT_SYNTHESIS";
  if (pathname.startsWith("/repositories")) return "REPOSITORY_WORKSPACE";
  if (pathname.startsWith("/migration")) return "MIGRATION_GOVERNANCE";
  if (pathname.startsWith("/commercialization")) return "COMMERCIALIZATION";
  if (pathname.startsWith("/pricing")) return "PRICING_USAGE";
  if (pathname.startsWith("/skills")) return "SKILLS_QUALIFICATION";
  if (pathname.startsWith("/admin")) return "ADMIN_OPERATIONS";
  return "PRODUCT_OVERVIEW";
}

function safePath(value: string): string {
  try {
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin ? url.pathname : "EXTERNAL";
  } catch {
    return "/";
  }
}

function stableTarget(element: Element | null): string {
  if (!element) return "unknown";
  const explicit = element.getAttribute("data-operation-id");
  if (explicit && /^[A-Za-z0-9._:-]{1,120}$/.test(explicit)) return explicit;
  if (element instanceof HTMLAnchorElement) return `link:${safePath(element.href)}`;
  const tag = element.tagName.toLocaleLowerCase("en-US");
  const role = element.getAttribute("role");
  const type = element instanceof HTMLButtonElement || element instanceof HTMLInputElement
    ? element.type
    : null;
  const classToken = Array.from(element.classList)
    .find((item) => /^[A-Za-z][A-Za-z0-9_-]{0,48}$/.test(item));
  return [tag, role ? `role-${role}` : "", type ? `type-${type}` : "", classToken ?? ""]
    .filter(Boolean)
    .join(":")
    .slice(0, 160);
}

function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function sessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const created = uuid();
    sessionStorage.setItem(SESSION_KEY, created);
    return created;
  } catch {
    return uuid();
  }
}

function loadQueue(): UserActivityEvent[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is UserActivityEvent => {
      if (typeof item !== "object" || item === null || Array.isArray(item)) return false;
      const event = item as Partial<UserActivityEvent>;
      return typeof event.eventId === "string"
        && typeof event.sessionId === "string"
        && typeof event.eventKind === "string"
        && typeof event.action === "string"
        && typeof event.businessLine === "string"
        && typeof event.route === "string"
        && typeof event.target === "string"
        && typeof event.occurredAt === "string"
        && ["SUCCESS", "FAILURE", "CANCELLED"].includes(event.result ?? "");
    }).slice(-MAX_QUEUE);
  } catch {
    return [];
  }
}

function saveQueue(queue: UserActivityEvent[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(queue.slice(-MAX_QUEUE)));
  } catch {
    // Storage may be disabled; the in-memory queue still works for this page.
  }
}

function roundedDuration(value: number): number {
  return Math.max(0, Math.min(3_600_000, Math.round(value)));
}

function telemetryOutcome(result: UserActivityEvent["result"]): TelemetryOutcome {
  if (result === "FAILURE") return "failed";
  if (result === "CANCELLED") return "cancelled";
  return "succeeded";
}

function telemetryEventName(event: UserActivityEvent): ConsoleTelemetryEvent["eventName"] {
  if (event.eventKind === "NAVIGATION") return "page_view";
  if (event.eventKind === "API_REQUEST") return "api_request";
  if (event.eventKind === "CLIENT_ERROR") return "js_error";
  if (event.eventKind === "PERFORMANCE") return "performance";
  if (event.action === "FORM_SUBMIT") return "form_submit";
  return "interaction";
}

function telemetryTargetKind(event: UserActivityEvent): TelemetryTargetKind {
  if (event.eventKind === "NAVIGATION" || event.eventKind === "PERFORMANCE") return "page";
  if (event.eventKind === "API_REQUEST") return "api";
  if (event.eventKind === "CLIENT_ERROR") return "window";
  const prefix = event.target.split(":", 1)[0];
  return ["button", "link", "form", "input", "select", "textarea"].includes(prefix)
    ? prefix as TelemetryTargetKind
    : "unknown";
}

function actionKey(event: UserActivityEvent): string {
  const normalizedTarget = normalizeTelemetryRoute(event.target);
  const source = event.eventKind === "API_REQUEST"
    ? `${event.action.toLocaleLowerCase("en-US")}.${normalizedTarget.replace(/^\/api\/?/, "").replaceAll("/", ".")}`
    : event.action.toLocaleLowerCase("en-US");
  const normalized = source.replace(/[^a-z0-9._-]+/g, "-").replace(/^[^a-z0-9]+/, "").slice(0, 81);
  return normalized.length >= 3 ? normalized : `ui.${normalized || "unknown"}`;
}

function viewportClass(): ConsoleTelemetryEvent["viewportClass"] {
  if (window.innerWidth < 680) return "mobile";
  if (window.innerWidth < 1024) return "tablet";
  return "desktop";
}

function toTelemetry(event: UserActivityEvent): ConsoleTelemetryEvent {
  const route = normalizeTelemetryRoute(event.route);
  return {
    schemaVersion: telemetrySchemaVersion,
    eventName: telemetryEventName(event),
    businessLine: routeBusinessLine(route),
    route,
    actionKey: actionKey(event),
    targetKind: telemetryTargetKind(event),
    outcome: telemetryOutcome(event.result),
    durationBucket: bucketDuration(event.durationMs),
    viewportClass: viewportClass(),
    sessionId: event.sessionId,
    occurredAt: event.occurredAt,
    durationMs: event.durationMs ?? null,
    errorCode: event.errorCode ?? null,
  };
}

export function UserActivityCollector() {
  const pathname = usePathname();

  useEffect(() => {
    if (collectorInstalled) return;
    collectorInstalled = true;

    const session = sessionId();
    let queue = loadQueue();
    let inFlight = false;
    let stopped = false;
    let enabled = true;
    try {
      enabled = localStorage.getItem(PREFERENCE_KEY) !== "off";
    } catch {
      // Storage can be unavailable in hardened browser modes.
    }
    const nativeFetch = window.fetch.bind(window);
    let lastRoute = safePath(window.location.pathname);
    if (!enabled) {
      queue = [];
      saveQueue(queue);
    }

    function enqueue(input: Omit<UserActivityEvent, "eventId" | "sessionId" | "occurredAt" | "businessLine" | "route"> & {
      route?: string;
      businessLine?: string;
    }) {
      if (!enabled) return;
      const route = input.route ?? window.location.pathname;
      queue.push({
        ...input,
        eventId: uuid(),
        sessionId: session,
        occurredAt: new Date().toISOString(),
        businessLine: input.businessLine ?? businessLine(route),
        route: safePath(route),
      });
      if (queue.length > MAX_QUEUE) queue = queue.slice(-MAX_QUEUE);
      saveQueue(queue);
      if (queue.length >= BATCH_SIZE) void flush();
    }

    async function flush() {
      if (stopped || inFlight || queue.length === 0) return;
      inFlight = true;
      const batch = queue.slice(0, BATCH_SIZE);
      try {
        const response = await nativeFetch(ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ events: batch.map(toTelemetry) }),
          cache: "no-store",
          keepalive: true,
        });
        if (response.ok) {
          const sent = new Set(batch.map((event) => event.eventId));
          queue = queue.filter((event) => !sent.has(event.eventId));
          saveQueue(queue);
        }
      } catch {
        // Keep the bounded queue for a later retry. Never log the telemetry failure through itself.
      } finally {
        inFlight = false;
      }
    }

    function handleClick(event: MouseEvent) {
      const target = event.target instanceof Element
        ? event.target.closest("button, a, [role='button'], summary, [data-operation-id]")
        : null;
      if (!target || target.closest("[data-telemetry-ignore='true']")) return;
      enqueue({
        eventKind: "USER_ACTION",
        action: "CLICK",
        target: stableTarget(target),
        result: "SUCCESS",
      });
    }

    function handleSubmit(event: SubmitEvent) {
      const target = event.target instanceof Element
        ? event.target.closest("form, [data-operation-id]")
        : null;
      if (!target || target.closest("[data-telemetry-ignore='true']")) return;
      enqueue({
        eventKind: "USER_ACTION",
        action: "FORM_SUBMIT",
        target: stableTarget(target),
        result: "SUCCESS",
      });
    }

    function handleError() {
      enqueue({
        eventKind: "CLIENT_ERROR",
        action: "RUNTIME_ERROR",
        target: "window",
        result: "FAILURE",
        errorCode: "JS_RUNTIME_ERROR",
      });
    }

    function handleRejection() {
      enqueue({
        eventKind: "CLIENT_ERROR",
        action: "UNHANDLED_REJECTION",
        target: "window",
        result: "FAILURE",
        errorCode: "UNHANDLED_PROMISE_REJECTION",
      });
    }

    function handleRouteChange(event: Event) {
      const detail = (event as CustomEvent<{ pathname?: string }>).detail;
      const route = safePath(detail?.pathname ?? window.location.pathname);
      if (route === lastRoute) return;
      lastRoute = route;
      enqueue({
        eventKind: "NAVIGATION",
        action: "PAGE_VIEW",
        target: route,
        route,
        result: "SUCCESS",
      });
    }

    function handlePreference(event: Event) {
      const requested = (event as CustomEvent<{ enabled?: boolean }>).detail?.enabled;
      enabled = requested === true;
      try {
        localStorage.setItem(PREFERENCE_KEY, enabled ? "on" : "off");
      } catch {
        // The in-memory preference still applies for the current page.
      }
      if (!enabled) {
        queue = [];
        saveQueue(queue);
      } else {
        enqueue({
          eventKind: "USER_ACTION",
          action: "TELEMETRY_ENABLED",
          target: "button:telemetry-preference",
          result: "SUCCESS",
        });
      }
    }

    const wrappedFetch: typeof window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const rawUrl = input instanceof Request ? input.url : String(input);
      const path = safePath(rawUrl);
      if (!path.startsWith("/api/") || path === ENDPOINT || path.startsWith("/api/admin/")) {
        return nativeFetch(input, init);
      }
      const started = performance.now();
      const method = (init?.method ?? (input instanceof Request ? input.method : "GET")).toUpperCase();
      try {
        const response = await nativeFetch(input, init);
        enqueue({
          eventKind: "API_REQUEST",
          action: `API_${method}`,
          target: path,
          route: window.location.pathname,
          durationMs: roundedDuration(performance.now() - started),
          result: response.ok ? "SUCCESS" : "FAILURE",
          errorCode: response.ok ? undefined : `HTTP_${response.status}`,
          metadata: { statusClass: `${Math.floor(response.status / 100)}XX` },
        });
        return response;
      } catch (error) {
        enqueue({
          eventKind: "API_REQUEST",
          action: `API_${method}`,
          target: path,
          route: window.location.pathname,
          durationMs: roundedDuration(performance.now() - started),
          result: "FAILURE",
          errorCode: error instanceof DOMException && error.name === "AbortError"
            ? "REQUEST_ABORTED"
            : "NETWORK_ERROR",
        });
        throw error;
      }
    };
    window.fetch = wrappedFetch;

    document.addEventListener("click", handleClick, true);
    document.addEventListener("submit", handleSubmit, true);
    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);
    window.addEventListener("elmos:route-change", handleRouteChange);
    window.addEventListener("elmos:telemetry-preference", handlePreference);

    enqueue({
      eventKind: "NAVIGATION",
      action: "PAGE_VIEW",
      target: safePath(window.location.pathname),
      result: "SUCCESS",
    });

    const loadMetrics = () => {
      const navigation = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
      if (navigation) {
        enqueue({
          eventKind: "PERFORMANCE",
          action: "PERFORMANCE_MEASURE",
          target: "navigation",
          durationMs: roundedDuration(navigation.duration),
          result: "SUCCESS",
          metricName: "PAGE_LOAD_MS",
          metricValue: roundedDuration(navigation.duration),
        });
      }
      for (const entry of performance.getEntriesByType("paint")) {
        if (entry.name !== "first-contentful-paint") continue;
        enqueue({
          eventKind: "PERFORMANCE",
          action: "PERFORMANCE_MEASURE",
          target: "paint",
          durationMs: roundedDuration(entry.startTime),
          result: "SUCCESS",
          metricName: "FCP_MS",
          metricValue: roundedDuration(entry.startTime),
        });
      }
    };
    if (document.readyState === "complete") queueMicrotask(loadMetrics);
    else window.addEventListener("load", loadMetrics, { once: true });

    const timer = window.setInterval(() => void flush(), FLUSH_INTERVAL_MS);
    const onVisibility = () => {
      if (document.visibilityState === "hidden") void flush();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("click", handleClick, true);
      document.removeEventListener("submit", handleSubmit, true);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
      window.removeEventListener("elmos:route-change", handleRouteChange);
      window.removeEventListener("elmos:telemetry-preference", handlePreference);
      if (window.fetch === wrappedFetch) window.fetch = nativeFetch;
      collectorInstalled = false;
    };
  }, []);

  useEffect(() => {
    if (!collectorInstalled) return;
    // The global collector records initial navigation; this marker makes client-side
    // route changes observable without collecting query strings.
    window.dispatchEvent(new CustomEvent("elmos:route-change", { detail: { pathname } }));
  }, [pathname]);

  return null;
}
