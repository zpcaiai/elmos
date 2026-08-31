package io.elmos.persistence;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Cheap, deterministic guards for the V79 platform-administrator identity
 * boundary. The real PostgreSQL behavior is exercised by
 * {@link FlywayMigrationTest}; these checks make deleting one layer of the
 * defence visible even when Docker is unavailable.
 */
class PlatformAdminIdentityMigrationContractTest {
    private static final Path MIGRATION = Path.of(
            "src/main/resources/db/migration/V79__platform_admin_verified_email_boundary.sql");
    private static final Path ACCOUNT_MIGRATION = Path.of(
            "src/main/resources/db/migration/V55__account_identity_and_organization_self_service.sql");

    private static String migration() throws Exception {
        return Files.readString(MIGRATION);
    }

    @Test void eligibilityComesFromTheAuthoritativeVerifiedAccountRow() throws Exception {
        String body = bodyOf(migration(), "elmos_platform_admin_identity_eligible");

        assertTrue(body.contains("FROM public.accounts account"));
        assertTrue(body.contains("account.status = 'ACTIVE'"));
        assertTrue(body.contains("account.email_verified_at IS NOT NULL"));
        assertTrue(body.contains("account.primary_email = btrim(account.primary_email)"));
        assertTrue(body.contains("lower(account.primary_email) = 'zpchoney@gmail.com'"));
        assertFalse(body.contains("p_email"), "a caller-supplied email must never authorize");
    }

    @Test void canonicalEmailCanBelongToOnlyOneNonPurgedAccount() throws Exception {
        String accountSql = Files.readString(ACCOUNT_MIGRATION);

        assertTrue(accountSql.contains("CREATE UNIQUE INDEX accounts_primary_email_uq"));
        assertTrue(accountSql.contains("ON accounts (lower(primary_email))"));
        assertTrue(accountSql.contains(
                "WHERE primary_email IS NOT NULL AND status <> 'PURGED'"));
        assertTrue(migration().contains(
                "account.primary_email = btrim(account.primary_email)"),
                "V79 must reject whitespace variants that the legacy lower-only index distinguishes");
    }

    @Test void authorizationAndResolutionRecheckEligibilityOnEveryUse() throws Exception {
        String sql = migration();
        String authorize = bodyOf(sql, "elmos_platform_authorize");
        String resolve = bodyOf(sql, "elmos_platform_resolve_admin_account");

        assertTrue(authorize.contains("administrator.revoked_at IS NULL"));
        assertTrue(authorize.contains(
                "elmos_platform_admin_identity_eligible(administrator.account_id)"));
        assertTrue(authorize.contains("DENIED_NOT_ADMIN"));
        assertTrue(resolve.contains("JOIN public.platform_administrators administrator"));
        assertTrue(resolve.contains("administrator.revoked_at IS NULL"));
        assertTrue(resolve.contains(
                "elmos_platform_admin_identity_eligible(directory.account_id)"));
    }

    @Test void grantBootstrapAndDirectWritesCannotMintAnotherAdministrator() throws Exception {
        String sql = migration();
        String grant = bodyOf(sql, "elmos_platform_grant_admin");
        String bootstrap = bodyOf(sql, "elmos_platform_bootstrap_admin");
        String guard = bodyOf(sql, "elmos_platform_admin_identity_guard");

        assertTrue(grant.contains(
                "NOT public.elmos_platform_admin_identity_eligible(p_target_account_id)"));
        assertTrue(bootstrap.contains(
                "NOT public.elmos_platform_admin_identity_eligible(p_target_account_id)"));
        assertTrue(guard.contains("ELMOS_PLATFORM_ADMIN_VERIFIED_EMAIL_REQUIRED"));
        assertTrue(guard.contains("FOR SHARE"),
                "direct grants must serialize with concurrent account identity changes");
        assertTrue(sql.contains("CREATE TRIGGER platform_administrators_identity_guard"));
        assertTrue(sql.contains("BEFORE INSERT OR UPDATE OF account_id, revoked_at"));
    }

    @Test void upgradeRevokesAndAuditsEveryExistingIneligibleLiveRow() throws Exception {
        String sql = migration();

        assertTrue(sql.contains("UPDATE public.platform_administrators administrator"));
        assertTrue(sql.contains("administrator.revoked_at IS NULL"));
        assertTrue(sql.contains(
                "NOT public.elmos_platform_admin_identity_eligible(administrator.account_id)"));
        assertTrue(sql.contains("SYSTEM_SECURITY_MIGRATION_V79_IDENTITY_INELIGIBLE"));
        assertTrue(sql.contains("MIGRATION_REVOKE_IDENTITY"));
        assertTrue(sql.contains("INSERT INTO public.platform_admin_access_log"));
        assertTrue(sql.contains(
                "LOCK TABLE public.platform_administrators IN SHARE ROW EXCLUSIVE MODE"));
        assertTrue(sql.contains(
                "LOCK TABLE public.accounts IN SHARE ROW EXCLUSIVE MODE"));
    }

    @Test void LosingVerifiedIdentityAutoRevokesInsteadOfBlockingTheAccountUpdate()
            throws Exception {
        String sql = migration();
        String revoke = bodyOf(sql, "elmos_platform_admin_revoke_on_identity_loss");

        assertTrue(sql.contains("CREATE TRIGGER accounts_platform_admin_identity_loss"));
        assertTrue(sql.contains("AFTER UPDATE OF primary_email, email_verified_at, status"));
        assertTrue(revoke.contains("SET revoked_at = v_revoked_at"));
        assertTrue(revoke.contains("SYSTEM_IDENTITY_ELIGIBILITY_LOST_V79"));
        assertTrue(revoke.contains("AUTO_REVOKE_IDENTITY"));
        assertFalse(revoke.contains("RAISE EXCEPTION"),
                "revoking verification or disabling the account must remain possible");
    }

    @Test void NewSecurityDefinerFunctionsPinSearchPathAndAreNotPublic() throws Exception {
        String sql = migration();

        for (String function : new String[]{
                "elmos_platform_admin_identity_eligible",
                "elmos_platform_admin_identity_guard",
                "elmos_platform_admin_revoke_on_identity_loss",
                "elmos_platform_authorize",
                "elmos_platform_resolve_admin_account",
                "elmos_platform_grant_admin",
                "elmos_platform_bootstrap_admin"}) {
            String body = bodyOf(sql, function);
            assertTrue(body.contains("SECURITY DEFINER"), () -> function + " must be definer-owned");
            assertTrue(body.contains("SET search_path = pg_catalog, public, pg_temp"),
                    () -> function + " must pin its search path");
            assertTrue(sql.contains("REVOKE ALL ON FUNCTION " + function + "("),
                    () -> function + " must not remain executable by PUBLIC");
        }
    }

    private static String bodyOf(String sql, String function) {
        int start = sql.indexOf("CREATE OR REPLACE FUNCTION " + function + "(");
        if (start < 0) {
            return "";
        }
        int end = sql.indexOf("\n$$;", start);
        return end < 0 ? sql.substring(start) : sql.substring(start, end);
    }
}
