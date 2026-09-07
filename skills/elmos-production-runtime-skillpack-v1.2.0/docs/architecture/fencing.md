# Atomic Fencing

Do not allocate fencing tokens with `MAX(fencing_token)+1` under production contention.

Use a per-work-item allocator row:

```text
work_item_fence_counters(work_item_id PK, next_token)
```

Atomic allocation:

```sql
INSERT ... VALUES(work_item_id, 1)
ON CONFLICT(work_item_id)
DO UPDATE SET next_token = work_item_fence_counters.next_token + 1
RETURNING next_token;
```

Every terminal or checkpoint ownership-sensitive commit must validate the current lease token.
