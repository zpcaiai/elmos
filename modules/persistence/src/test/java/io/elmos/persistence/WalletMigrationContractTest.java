package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Guards the shape of V73 without needing a database.
 *
 * <p>This is the cheap half of the pair. It catches a constraint or a REVOKE
 * being edited out of the migration, which is the failure mode a reviewer is
 * least likely to notice, because deleting a guard leaves nothing behind that
 * looks wrong. It cannot prove any of these guards actually fire -- that is
 * {@link WalletLedgerLiveTest}, which runs the same rules against a real
 * PostgreSQL and asserts the refusals.
 */
class WalletMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V73__wallet_prepaid_balance_and_topup.sql");

    @Test void balanceIsWritableOnlyThroughTheAccountingFunctions() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("ELMOS_WALLET_BALANCE_DIRECT_MUTATION_DENIED"));
        assertTrue(sql.contains("current_setting('app.wallet_posting', true)"));
        assertTrue(sql.contains("CREATE TRIGGER wallet_accounts_balance_guard"));
        assertTrue(sql.contains("CREATE TRIGGER wallet_accounts_no_delete"));
        assertTrue(sql.contains("ELMOS_WALLET_DELETE_DENIED"));
    }

    @Test void ledgerAndPriceBookAreAppendOnly() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CREATE TRIGGER wallet_ledger_entries_append_only"));
        assertTrue(sql.contains("CREATE TRIGGER wallet_price_book_append_only"));
        assertTrue(sql.contains("FOR EACH ROW EXECUTE FUNCTION elmos_forbid_append_only_mutation()"));
    }

    @Test void idempotencyAndSingleHoldPerJobAreEnforcedByTheStorageLayer() throws Exception {
        String sql = Files.readString(MIGRATION);

        // Replay protection has to live here rather than in each caller: the
        // callers are a payment provider retry, a runner retry and a person
        // clicking twice, and none of them coordinate.
        assertTrue(sql.contains("UNIQUE (organization_id, idempotency_key)"));
        assertTrue(sql.contains("UNIQUE (organization_id, job_id)"));
        assertTrue(sql.contains("UNIQUE (provider, out_trade_no)"));
    }

    @Test void terminalStatesAreImmutable() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("ELMOS_WALLET_RESERVATION_TERMINAL_IMMUTABLE"));
        assertTrue(sql.contains("ELMOS_WALLET_RESERVATION_AMOUNT_IMMUTABLE"));
        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_TERMINAL_IMMUTABLE"));
        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_AMOUNT_IMMUTABLE"));
        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_TRADE_NO_IMMUTABLE"));
    }

    @Test void moneyCannotGoNegativeAndHoldsCannotExceedTheBalance() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CHECK (balance_minor >= 0)"));
        assertTrue(sql.contains("wallet_accounts_reserved_within_balance CHECK (reserved_minor <= balance_minor)"));
        assertTrue(sql.contains("ELMOS_WALLET_INSUFFICIENT_BALANCE"));
    }

    @Test void aJobIsNeverChargedMoreThanWasHeldForIt() throws Exception {
        String sql = Files.readString(MIGRATION);

        // The declarative half.
        assertTrue(sql.contains("AND settled_amount_minor <= amount_minor"));
        // The procedural half: settle clamps rather than raising, so a settler
        // bug under-charges instead of exceeding what the user was quoted.
        assertTrue(sql.contains("least(greatest(coalesce(p_settled_amount_minor, 0), 0), v_reservation.amount_minor)"));
    }

    @Test void adjustingABalanceByHandRequiresAReason() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("wallet_ledger_entries_adjustment_reason"));
        assertTrue(sql.contains("CHECK (entry_type <> 'ADMIN_ADJUSTMENT' OR reason IS NOT NULL)"));
        assertTrue(sql.contains("ELMOS_WALLET_ADJUSTMENT_REASON_REQUIRED"));
    }

    @Test void everyTenantScopedTableIsForcedUnderTheStandardIsolationPolicy() throws Exception {
        String sql = Files.readString(MIGRATION);

        for (String table : new String[]{
                "wallet_accounts", "wallet_ledger_entries", "wallet_reservations",
                "wallet_topup_orders", "wallet_topup_policies"}) {
            assertTrue(sql.contains("'" + table + "'"),
                    () -> table + " must be in the row level security loop");
        }
        assertTrue(sql.contains("FORCE ROW LEVEL SECURITY"));
        assertTrue(sql.contains("CREATE POLICY tenant_isolation ON %I"));
    }

    @Test void theSettlementOutboxIsExemptFromIsolationButNotFromPermissions() throws Exception {
        String sql = Files.readString(MIGRATION);

        // Cross-tenant by necessity, like execution_job_dispatch: a settler
        // cannot run under a per-transaction app.organization_id. The exemption
        // is only defensible because the table holds no customer content, so the
        // access control is a role rather than a policy.
        assertTrue(sql.contains("REVOKE ALL ON wallet_settlement_outbox FROM PUBLIC"));
        assertTrue(sql.contains("GRANT SELECT, INSERT, UPDATE ON wallet_settlement_outbox TO elmos_wallet_settler"));
        assertFalse(sql.contains("CREATE POLICY tenant_isolation ON wallet_settlement_outbox"));
    }

    @Test void everyAccountingFunctionIsRevokedFromPublic() throws Exception {
        String sql = Files.readString(MIGRATION);

        for (String function : new String[]{
                "elmos_wallet_open", "elmos_wallet_post_entry", "elmos_wallet_credit_topup",
                "elmos_wallet_reserve", "elmos_wallet_settle", "elmos_wallet_release",
                "elmos_wallet_expire_reservations", "elmos_wallet_adjust",
                "elmos_wallet_reconcile", "elmos_wallet_topup_bounds"}) {
            assertTrue(sql.contains("'" + function + "'"),
                    () -> function + " must be in the REVOKE EXECUTE ... FROM PUBLIC loop");
        }
        assertTrue(sql.contains("REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC"));
    }

    @Test void thePaymentServiceGetsFunctionsAndNoWalletTableAtAll() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("GRANT EXECUTE ON FUNCTION elmos_wallet_credit_topup("
                + "varchar, varchar, varchar, varchar) TO elmos_billing_runtime"));
        assertTrue(sql.contains("GRANT EXECUTE ON FUNCTION elmos_wallet_create_topup_order("));
        // Not one writable wallet table. Everything the payment service can do to
        // a balance is the surface of two function signatures, and both of them
        // name the single order they act on.
        assertFalse(sql.contains("ON wallet_accounts TO elmos_billing_runtime"));
        assertFalse(sql.contains("ON wallet_ledger_entries TO elmos_billing_runtime"));
        assertFalse(sql.contains("ON wallet_topup_orders TO elmos_billing_runtime"));
        assertFalse(sql.contains("ON wallet_reservations TO elmos_billing_runtime"));
        // The directory is the one table it reads, and only reads.
        assertTrue(sql.contains("GRANT SELECT ON wallet_topup_order_directory TO elmos_billing_runtime"));
    }

    @Test void aCallbackCanResolveItsTenantBeforeItHasOne() throws Exception {
        String sql = Files.readString(MIGRATION);

        // wallet_topup_orders is FORCE RLS, and a callback arrives carrying an
        // out_trade_no and no organization. Without this projection the policy
        // evaluates against a NULL context, the order is invisible, and every
        // top-up silently becomes an unmatched callback -- the exact failure V62
        // had to retrofit a fix for on payment_checkout_sessions.
        assertTrue(sql.contains("CREATE TABLE wallet_topup_order_directory"));
        assertTrue(sql.contains("CREATE TRIGGER wallet_topup_orders_directory_sync"));
        assertFalse(sql.contains("'wallet_topup_order_directory'"),
                "the directory must stay out of the row level security loop");
        // V64's lesson: the sync trigger runs while the caller holds no write
        // permission on the directory, so it must be SECURITY DEFINER with a
        // pinned path and schema-qualified targets.
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_sync_wallet_topup_directory()"));
        assertTrue(sql.contains("SET search_path = pg_catalog, public, pg_temp"));
        assertTrue(sql.contains("INSERT INTO public.wallet_topup_order_directory"));
        assertTrue(sql.contains("REVOKE ALL ON FUNCTION elmos_sync_wallet_topup_directory() FROM PUBLIC"));
    }

    @Test void accountingFunctionsBindTheirOwnTenantInsteadOfAssumingOwnerBypass() throws Exception {
        String sql = Files.readString(MIGRATION);

        // FORCE ROW LEVEL SECURITY binds the table owner too, so a SECURITY
        // DEFINER function only sees rows if a tenant is bound -- unless the
        // owner happens to be a superuser, which is a deployment property this
        // migration cannot see and must not depend on.
        assertTrue(sql.contains("CREATE OR REPLACE FUNCTION elmos_wallet_bind_tenant("));
        assertTrue(sql.contains("ELMOS_WALLET_TENANT_REQUIRED"));
        assertTrue(sql.contains("PERFORM set_config('app.organization_id', v_previous, true)"),
                "the previous tenant context must be restored, not left bound");
        for (String function : new String[]{
                "elmos_wallet_open", "elmos_wallet_post_entry", "elmos_wallet_reserve",
                "elmos_wallet_settle", "elmos_wallet_release", "elmos_wallet_credit_topup",
                "elmos_wallet_create_topup_order", "elmos_wallet_reconcile",
                "elmos_wallet_expire_reservations"}) {
            String body = bodyOf(sql, function);
            assertTrue(body.contains("elmos_wallet_bind_tenant("),
                    () -> function + " touches tenant tables without binding a tenant");
        }
    }

    @Test void theExpirySweeperIsPerTenantRatherThanACrossTenantScan() throws Exception {
        String sql = Files.readString(MIGRATION);

        // A cross-tenant scan of wallet_reservations returns nothing under FORCE
        // RLS, so the sweeper would "succeed" having swept zero rows and money
        // would stay frozen with no error anywhere.
        assertTrue(bodyOf(sql, "elmos_wallet_expire_reservations")
                        .contains("p_organization_id varchar"),
                "the sweeper must take an organization");
    }

    @Test void topUpLimitsAreEnforcedWhereNoCallerCanSkipThem() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_BELOW_MINIMUM"));
        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_ABOVE_MAXIMUM"));
        assertTrue(sql.contains("ELMOS_WALLET_TOPUP_DAILY_LIMIT_EXCEEDED"));
        // Pending orders count against the day. Counting only credited ones lets
        // a caller open unlimited orders and settle them together.
        assertTrue(sql.contains("AND status NOT IN ('FAILED', 'EXPIRED')"));
    }

    private static String bodyOf(String sql, String function) {
        int start = sql.indexOf("CREATE OR REPLACE FUNCTION " + function + "(");
        if (start < 0) {
            return "";
        }
        int end = sql.indexOf("\n$$;", start);
        return end < 0 ? sql.substring(start) : sql.substring(start, end);
    }

    @Test void everySecurityDefinerFunctionPinsItsSearchPath() throws Exception {
        String sql = Files.readString(MIGRATION);

        // Counted per function definition, not per occurrence of the phrase.
        // The first version of this test counted occurrences and reported 12
        // definers against 10 pinned search_paths, which reads exactly like two
        // unpinned functions. Both extras were the words "SECURITY DEFINER"
        // inside COMMENT prose. A test that fails on documentation teaches the
        // next person to stop trusting it.
        String[] definitions = sql.split("CREATE OR REPLACE FUNCTION");
        int definers = 0;
        for (int i = 1; i < definitions.length; i++) {
            String definition = definitions[i];
            if (!definition.contains("\nSECURITY DEFINER")) {
                continue;
            }
            definers++;
            String signature = definition.substring(0, definition.indexOf('(')).trim();
            String header = definition.substring(0, Math.max(definition.indexOf("AS $$"), 0));
            // An unpinned SECURITY DEFINER function runs with the CALLER's
            // search_path while holding the OWNER's privileges: a caller who can
            // create a schema can shadow any unqualified name it resolves and be
            // executed as the owner.
            assertTrue(header.contains("SET search_path = public"),
                    () -> signature + " is SECURITY DEFINER without a pinned search_path");
        }
        int securityDefinerCount = definers;
        assertTrue(securityDefinerCount >= 10,
                () -> "expected the ten accounting functions, found " + securityDefinerCount);
    }

    @Test void seededPricesAreDraftSoAnUnapprovedPriceCannotCharge() throws Exception {
        String sql = Files.readString(MIGRATION);

        assertTrue(sql.contains("CHECK (status IN ('DRAFT', 'PUBLISHED', 'SUPERSEDED'))"));
        assertFalse(sql.contains("'PUBLISHED');"),
                "V73 must not seed a published price");
    }
}
