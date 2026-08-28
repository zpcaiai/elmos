# Security Model Delta

- Caller metadata is untrusted.
- Verified security context is Host-minted and invocation-bound.
- Execution authority is the intersection of verified context, Environment/Attachment owner profile, parent authority and global policy.
- Host capabilities are borrowed through non-transferable, revocable leases.
- Skill content is not authorization; verified provenance and explicit authorization semantics are.
- Remote Executor and Workspace commits require current generation fencing.
- Lossy permission projections and unknown required durable events fail closed.
