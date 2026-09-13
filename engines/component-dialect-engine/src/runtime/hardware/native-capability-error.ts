export class NativeCapabilityUnavailableError extends Error {
  readonly code = "NATIVE_CAPABILITY_UNAVAILABLE";
  readonly evidenceState = "NOT_RUN";

  constructor(readonly capability: string, readonly platform: string) {
    super(`Native capability ${capability} is unavailable on ${platform}; explicit mock mode is required for local tests.`);
    this.name = "NativeCapabilityUnavailableError";
  }
}
