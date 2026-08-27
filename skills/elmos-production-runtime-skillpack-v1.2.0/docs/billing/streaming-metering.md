# Streaming Token / Credit Metering

Long-running calls should not make the UI wait until final settlement.

## Meter model

`usage_meter_events` are monotonic cumulative snapshots.

Unique key:
`(model_call_id, sequence_no)`

Also enforce monotonic cumulative token counts per call.

UI may project:
- input tokens
- cached tokens
- output tokens
- reasoning tokens
- metered provider cost
- metered credits
- reserved credits
- final settled credits

## Finalization

Final provider usage is authoritative for settlement.

The finalizer:
1. validates final usage is not less than the last cumulative meter without an explicit provider correction;
2. writes final usage once;
3. settles reservation;
4. emits a final meter/settlement event;
5. records any meter-to-final delta for observability.
