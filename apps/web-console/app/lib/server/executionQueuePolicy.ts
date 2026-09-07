export type ExecutionQueueMode = "HOSTED" | "LOCAL_DEVELOPMENT";

type QueueEnvironment = Readonly<Record<string, string | undefined>>;

/**
 * Production is always hosted.  The opt-in flag is intentionally unable to
 * downgrade a production process to the filesystem queue.
 */
export function executionQueueMode(
  environment: QueueEnvironment = process.env,
): ExecutionQueueMode {
  if (environment.NODE_ENV === "production") return "HOSTED";
  return environment.ELMOS_HOSTED_EXECUTION_ENABLED === "true"
    ? "HOSTED"
    : "LOCAL_DEVELOPMENT";
}

export function hostedExecutionRequired(
  environment: QueueEnvironment = process.env,
): boolean {
  return executionQueueMode(environment) === "HOSTED";
}

export function localFilesystemExecutionAllowed(
  environment: QueueEnvironment = process.env,
): boolean {
  return executionQueueMode(environment) === "LOCAL_DEVELOPMENT";
}
