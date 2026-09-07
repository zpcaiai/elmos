---
name: python-ai-ml-framework-modernizer
description: Modernize TensorFlow, PyTorch, scikit-learn, traditional ML, training workflows, checkpoints, exports, serving, feature pipelines, and GPU compatibility. Use for AI/ML code migration, model artifact strategy, TensorFlow 1 conversion, PyTorch upgrades, or scikit-learn persistence risks.
---

# Python AI and ML Framework Modernizer

## Separate code, artifact, and environment

Inventory framework/version, Python, CUDA/device/precision, model class, datasets/features, training scripts, checkpoints, optimizer/scheduler, metrics, serving/export, distribution, seeds, and experiment tracking. Bind every model artifact to its exact environment snapshot.

For TensorFlow 1, capture the original baseline, use the official conversion tool only as a candidate, transition through `compat.v1`, then migrate graph/session, eager or `tf.function`, training, checkpoints, SavedModel, summaries, and metrics in stages. Do not equate automatic API rewriting with equivalence.

For PyTorch, compare module/state-dict keys, tensor shapes/dtypes/devices, optimizer/scheduler, distributed settings, AMP/compile/export, and serving. Apply approved numerical tolerances; do not require cross-version or CPU/GPU bitwise identity.

For scikit-learn, preserve estimator/pipeline/transformer order, feature/category/preprocessing/random-state details, custom functions, and training environment. Do not assume pickle/joblib compatibility or safety.

Choose among old-environment neutral export, resave, retrain, ONNX, compatibility runtime, or dual-serving shadow. Block incompatible GPU/driver/CUDA/cuDNN/wheel stacks. Accept only after feature/signature, artifact load matrix, inference, training tier, metrics, hardware, and serving behavior are independently validated.

