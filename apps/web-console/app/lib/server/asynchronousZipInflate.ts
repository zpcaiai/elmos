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

      push(chunk: Uint8Array, final: boolean): void {
        if (owner.#closed || this.#terminated) return;
        if (owner.#pending.length >= 4096) throw new Error("ZIP_INFLATE_QUEUE_LIMIT");
        const bytes = Buffer.from(chunk);
        owner.#pending.push(async () => {
          if (this.#terminated) return;
          const stream = this.#stream ??= createInflateRaw();
          if (!owner.#streams.has(stream)) {
            owner.#streams.add(stream);
            stream.on("data", (data: Buffer) => {
              try { this.ondata(null, data, false); }
              catch (error) { stream.destroy(error instanceof Error ? error : new Error("ZIP_CALLBACK_FAILED")); }
            });
          }
          await new Promise<void>((resolve, reject) => {
            const cleanup = () => {
              stream.removeListener("error", failed);
              stream.removeListener("end", ended);
            };
            const failed = (error: Error) => { cleanup(); reject(error); };
            const ended = () => {
              cleanup();
              owner.#streams.delete(stream);
              this.ondata(null, new Uint8Array(), true);
              resolve();
            };
            stream.once("error", failed);
            if (final) {
              stream.once("end", ended);
              stream.end(bytes);
            } else {
              stream.write(bytes, (error) => {
                if (error) { failed(error); return; }
                cleanup();
                resolve();
              });
            }
          });
        });
      }

      terminate(): void {
        this.#terminated = true;
        this.#stream?.destroy(new Error("ZIP_ENTRY_TERMINATED"));
      }
    };
  }

  async drain(): Promise<void> {
    while (this.#pending.length) await this.#pending.shift()!();
  }

  close(): void {
    this.#closed = true;
    this.#pending.length = 0;
    for (const stream of this.#streams) stream.destroy();
    this.#streams.clear();
  }
}
