/** At most one write plus one dirty bit; callers never append Promise tails. */
export class CoalescingFlush {
  #write: () => Promise<void>;
  #delayMs: number;
  #dirty = false;
  #running: Promise<void> | undefined;
  #timer: ReturnType<typeof setTimeout> | undefined;
  #failure: unknown;

  constructor(write: () => Promise<void>, delayMs = 100) {
    this.#write = write;
    this.#delayMs = delayMs;
  }

  request(): void {
    this.#dirty = true;
    if (this.#timer || this.#running || this.#failure) return;
    this.#timer = setTimeout(() => {
      this.#timer = undefined;
      void this.flush().catch(() => undefined);
    }, this.#delayMs);
  }

  async flush(): Promise<void> {
    if (this.#timer) clearTimeout(this.#timer);
    this.#timer = undefined;
    if (this.#running) await this.#running;
    if (this.#failure) throw this.#failure;
    if (!this.#dirty) return;
    this.#running = (async () => {
      try {
        while (this.#dirty) {
          this.#dirty = false;
          await this.#write();
        }
      } catch (error) {
        this.#failure = error;
        throw error;
      } finally {
        this.#running = undefined;
      }
    })();
    await this.#running;
  }
}
