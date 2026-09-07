# Model Serving Lifecycle

Model generation and serving are separated. The serving profile freezes model artifact, tokenizer, runtime, quantization, hardware, batching, cache, safety, routing, observability and rollback. Shadow and canary gates compare quality, schema/tool behavior, safety, latency tails, throughput and full cost.

A provider alias is not a version; behavior fingerprints and drift triggers govern recertification.
