package elmos.fde.production_write
default allow := false
# This capability package intentionally cannot authorize production writes.
deny_reason := "production writes require external customer authority and certification workflow"
