\set ON_ERROR_STOP on
begin read only;
select set_config('app.tenant_id', :'tenant_id', true);
select count(*) as marker_count
  from observability.pitr_markers
 where tenant_id = :'tenant_id'::uuid
   and id = :'marker_id'::uuid
   and payload_sha256 = :'marker_sha256'
   and change_id = :'change_id'
\gset
\if :marker_count
\else
  \echo 'PITR_MARKER_NOT_FOUND_OR_MISMATCHED'
  \quit 3
\endif
select count(*) as negative_wallets
  from billing.wallet_balances
 where tenant_id = :'tenant_id'::uuid
   and (available_balance < 0 or reserved_balance < 0)
\gset
\if :negative_wallets
  \echo 'PITR_NEGATIVE_WALLET_INVARIANT_FAILED'
  \quit 4
\endif
select count(*) as unbalanced_journals
  from (
    select journal_id, currency
      from billing.billing_journal_lines
     where tenant_id = :'tenant_id'::uuid
     group by journal_id, currency
    having sum(debit) <> sum(credit)
  ) violations
\gset
\if :unbalanced_journals
  \echo 'PITR_JOURNAL_BALANCE_INVARIANT_FAILED'
  \quit 5
\endif
select json_build_object(
  'marker_id', :'marker_id',
  'marker_sha256', :'marker_sha256',
  'negative_wallets', :negative_wallets,
  'unbalanced_journals', :unbalanced_journals,
  'server_version_num', current_setting('server_version_num')
)::text;
rollback;
