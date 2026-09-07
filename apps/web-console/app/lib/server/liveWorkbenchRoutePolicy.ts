const identifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/;

export function liveWorkbenchRouteAllowed(path: readonly string[], method: string): boolean {
  if (method === "POST" && path.length === 1 && path[0] === "sessions") return true;
  if (method === "POST" && path.length === 1 && path[0] === "explanations") return true;
  if (
    method === "GET" &&
    path.length === 2 &&
    ["deliveries", "missions", "correspondences"].includes(path[0]) &&
    identifier.test(path[1])
  )
    return true;
  if (
    method === "GET" &&
    path.length === 3 &&
    path[0] === "anchors" &&
    identifier.test(path[1]) &&
    path[2] === "source"
  )
    return true;
  if (
    method === "POST" &&
    path.length === 3 &&
    path[0] === "missions" &&
    identifier.test(path[1]) &&
    path[2] === "attempts"
  )
    return true;
  if (path.length < 2 || path[0] !== "sessions" || !identifier.test(path[1])) return false;
  const suffix = path.slice(2).join("/");
  if (method === "GET")
    return suffix === "" || suffix === "events" || suffix === "events/stream" || suffix === "preview-access";
  // Readiness commits and runtime-event ingestion are service-to-service only;
  // the browser BFF intentionally has no route to those authority surfaces.
  return method === "POST" && ["debug-commands", "terminate"].includes(suffix);
}

export function liveWorkbenchIdentifier(value: string): boolean {
  return identifier.test(value);
}
