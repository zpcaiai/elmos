# Kubernetes deployment contract

These manifests are hardened deployment inputs, not evidence that Kubernetes
was run. Before applying them, replace the deliberately invalid image digest,
provide a host-owned trusted service factory, create the referenced ConfigMap
and Secrets, enforce mTLS at the selected ingress/mesh, and label only the exact
database, telemetry, and ingress namespaces/pods that may communicate.

The current evidence state is `NOT_RUN`; certification is `NOT_CERTIFIED`.
Static manifest review cannot promote either field.
