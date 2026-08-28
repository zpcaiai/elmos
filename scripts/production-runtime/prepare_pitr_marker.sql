\set ON_ERROR_STOP on
begin;
select set_config('app.tenant_id', :'tenant_id', true);
insert into observability.pitr_markers
  (id, tenant_id, payload_sha256, change_id)
values
  (:'marker_id'::uuid, :'tenant_id'::uuid, :'marker_sha256', :'change_id')
on conflict (id) do update
set payload_sha256 = excluded.payload_sha256
where observability.pitr_markers.tenant_id = excluded.tenant_id
  and observability.pitr_markers.payload_sha256 = excluded.payload_sha256
  and observability.pitr_markers.change_id = excluded.change_id
returning id as committed_marker_id
\gset
\if :{?committed_marker_id}
\else
  \echo 'PITR_SOURCE_MARKER_CONFLICT'
  \quit 3
\endif
select to_char(clock_timestamp() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"');
commit;
