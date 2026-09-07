---
name: model-artifact-inference-and-training-validator
description: Independently validate Python model artifact compatibility, input/output signatures, inference predictions and metrics, training behavior, checkpoints, performance, and serving. Use for pickle/joblib/checkpoint loading, model migration decisions, shadow inference, or training-equivalence gates.
---

# Model Artifact, Inference, and Training Validator

## Keep three verdicts separate

Judge `ARTIFACT_COMPATIBILITY`, `INFERENCE_COMPATIBILITY`, and `TRAINING_COMPATIBILITY` independently. A correct inference sample does not prove training behavior, and a loadable artifact does not prove predictions.

Bind framework/version, Python, format/hash, class reference, signatures, and environment snapshot. Load pickle, joblib, cloudpickle, PyTorch checkpoints, and other executable formats only in a source-verified, no-network, no-secret, low-privilege, resource-limited sandbox.

Run the load matrix: original artifact/original environment, original/target, converted/target, and original/compatibility runtime. Compare input/output names, shapes, dynamic dimensions, dtypes, devices, batching, probabilities/embeddings/labels, and feature preprocessing/order.

Use versioned representative, edge, rare, null, extreme, and optional adversarial inference datasets. Apply owner-approved task metrics and thresholds. For training, choose smoke, short horizon, or full retrain and compare seeds/splits, losses, metrics, gradients/NaNs, convergence, stopping, checkpoints, precision, and hardware.

Run shadow inference without business side effects. Validate startup, health, warmup, concurrency, timeout, memory/GPU, throughput, reload, and fallback. Separate migration drift, dataset drift, nondeterminism, hardware variation, and unknown causes. Fail on disappeared tests or unapproved thresholds.

