import { createInflateRaw, type InflateRaw } from "node:zlib";
import type { UnzipDecoder, UnzipDecoderConstructor, AsyncFlateStreamHandler } from "fflate";

/** Feed one bounded archive chunk then await drain before feeding another.
 * Native zlib does the CPU work off the event loop. Entry decoders are serviced
 * serially, so an archive containing many small files cannot create a worker or
 * inflate context for every entry at once.
 */
export class AsynchronousZipInflate {
  #pending: Array<() => Promise<void>> = [];
  #streams = new Set<InflateRaw>();
  #closed = false;
  readonly decoder: UnzipDecoderConstructor;

  constructor() {
    const owner = this;
    this.decoder = class implements UnzipDecoder {
      static compression = 8;
      ondata: AsyncFlateStreamHandler = () => undefined;
      #stream: InflateRaw | undefined;
      #terminated = false;
      #failure: Error | undefined;
      #rejectWrite: ((error: Error) => void) | undefined;

      push(chunk: Uint8Array, final: boolean): void {
        if (owner.#closed || this.#terminated) return;
        if (owner.#pending.length >= 4096) throw new Error("ZIP_INFLATE_QUEUE_LIMIT");
        const bytes = Buffer.from(chunk);
        owner.#pending.push(async () => {
          if (this.#failure) throw this.#failure;
          if (owner.#closed || this.#terminated) throw new Error("ZIP_ENTRY_TERMINATED");
          const stream = this.#stream ??= createInflateRaw();
          if (!owner.#streams.has(stream)) {
            owner.#streams.add(stream);
            // This listener outlives individual writes. A zlib error can arrive
            // between drain() calls or when a completed write is terminated.
            stream.on("error", (error: Error) => {
              this.#failure ??= error;
              this.#rejectWrite?.(error);
            });
            stream.once("close", () => owner.#streams.delete(stream));
            stream.on("data", (data: Buffer) => {
              try { this.ondata(null, new Uint8Array(data), false); }
              catch (error) { stream.destroy(error instanceof Error ? error : new Error("ZIP_CALLBACK_FAILED")); }
            });
          }
          await new Promise<void>((resolve, reject) => {
            let settled = false;
            const cleanup = () => {
              stream.removeListener("end", ended);
              this.#rejectWrite = undefined;
            };
            const failed = (error: Error) => {
              if (settled) return;
              settled = true;
              this.#failure ??= error;
              cleanup(); reject(error);
            };
            const ended = () => {
              if (settled) return;
              try {
                this.ondata(null, new Uint8Array(), true);
                settled = true;
                cleanup();
                owner.#streams.delete(stream);
                resolve();
              } catch (error) {
                failed(error instanceof Error ? error : new Error("ZIP_CALLBACK_FAILED"));
              }
            };
            this.#rejectWrite = failed;
            if (final) {
              stream.once("end", ended);
              stream.end(bytes);
            } else {
              stream.write(bytes, (error) => {
                if (error) { failed(error); return; }
                if (settled) return;
                settled = true;
                cleanup();
                resolve();
              });
            }
          });
        });
      }

      terminate(): void {
        this.#terminated = true;
        this.#failure ??= new Error("ZIP_ENTRY_TERMINATED");
        this.#rejectWrite?.(this.#failure);
        this.#stream?.destroy(this.#failure);
      }
    };
  }

  async drain(): Promise<void> {
    if (this.#closed) throw new Error("ZIP_INFLATE_CLOSED");
    while (this.#pending.length) {
      await this.#pending.shift()!();
      if (this.#closed) throw new Error("ZIP_INFLATE_CLOSED");
    }
  }

  close(): void {
    this.#closed = true;
    this.#pending.length = 0;
    for (const stream of this.#streams) stream.destroy(new Error("ZIP_INFLATE_CLOSED"));
    this.#streams.clear();
  }
}
