# Target scaffold boundary

The target project must be generated from a repository-specific FCM after source
fingerprinting. This experimental pack deliberately does not ship a universal
Boot application class that would silently discard root/child context, filter,
view, security, persistence or transaction behavior. Scaffold generation and
target compilation remain `NOT_RUN`.
