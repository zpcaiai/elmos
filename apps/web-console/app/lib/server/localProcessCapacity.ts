import type { ChildProcess } from "node:child_process";

export class LocalProcessCapacityError extends Error {}

/** A process-local bulkhead, not a distributed queue or effect/idempotency authority. */
export class LocalProcessCapacity {
  #total = 0;
  #tenants = new Map<string, number>();

  acquire(tenant: string, globalLimit: number, tenantLimit: number): {
    release(): void;
    track(child: ChildProcess): void;
  } {
    if (!tenant || !Number.isSafeInteger(globalLimit) || globalLimit < 1 || globalLimit > 128
      || !Number.isSafeInteger(tenantLimit) || tenantLimit < 1 || tenantLimit > globalLimit) {
      throw new LocalProcessCapacityError("LOCAL_PROCESS_CAPACITY_CONFIGURATION_INVALID");
    }
    const count = this.#tenants.get(tenant) ?? 0;
    if (this.#total >= globalLimit || count >= tenantLimit) {
      throw new LocalProcessCapacityError("LOCAL_PROCESS_CAPACITY_REACHED");
    }
    this.#total += 1;
    this.#tenants.set(tenant, count + 1);
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      this.#total -= 1;
      const remaining = (this.#tenants.get(tenant) ?? 1) - 1;
      if (remaining === 0) this.#tenants.delete(tenant);
      else this.#tenants.set(tenant, remaining);
    };
    return {
      release,
      // Only close establishes both process exit and closed stdio. HTTP timeout,
      // stream errors, or an error event alone do not release a live process slot.
      track: (child) => { child.once("close", release); },
    };
  }
}

const processState = globalThis as typeof globalThis & {
  __elmosMultimodalProcessCapacity?: LocalProcessCapacity;
};
export const multimodalProcessCapacity = processState.__elmosMultimodalProcessCapacity
  ??= new LocalProcessCapacity();
