package io.elmos.runner;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFileAttributeView;
import java.nio.file.attribute.PosixFilePermissions;
import java.nio.file.attribute.UserPrincipalLookupService;

/**
 * Proves at startup that the workload will actually be able to write its
 * artifacts.
 *
 * <p>Why this exists: the workspace is created by the agent and mounted into a
 * container that runs as {@code --user=<workloadUid>}. If those two identities
 * differ and the agent cannot hand ownership over, the very first artifact write
 * fails with <em>Permission denied</em>. That is bad enough on its own, but the
 * failure mode is worse than it looks: a shell redirection that cannot create its
 * target does not necessarily set a non-zero exit code, so the job reports success
 * and produces nothing. The user sees an empty download and no error.</p>
 *
 * <p>This was found by running the real container flags against real podman, not
 * by reading the code - the two uids were only ever equal by coincidence.</p>
 *
 * <p>The probe is pure filesystem arithmetic and needs no image, so it runs before
 * registration and costs nothing.</p>
 */
public final class WorkspaceAccessProbe {

    private WorkspaceAccessProbe() {
    }

    public record Result(boolean usable, String detail) {
    }

    public static Result verify(AgentConfig config) {
        int agentUid = currentUid();
        int agentGid = currentGid();

        if (config.allowHostExecution()) {
            return new Result(true, "host execution: workload shares the agent identity");
        }

        if (agentUid == config.workloadUid() && agentGid == config.workloadGid()) {
            // The common and intended case: the agent container runs as the same
            // uid the workload container runs as, so 0700 workspaces just work.
            return new Result(true, "workload uid matches the agent uid (" + agentUid + ")");
        }

        // They differ. The agent must be able to hand the directories over, which
        // needs CAP_CHOWN - and the agent deliberately runs with capabilities
        // dropped. Prove it rather than hope.
        Path scratch = null;
        try {
            Files.createDirectories(config.workRoot());
            scratch = Files.createTempDirectory(config.workRoot(), "probe-",
                    PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
            if (!chown(scratch, config.workloadUid(), config.workloadGid())) {
                return new Result(false,
                        "workload uid " + config.workloadUid() + " differs from the agent uid "
                                + agentUid + " and ownership cannot be transferred; the first"
                                + " artifact write would fail with Permission denied");
            }
            return new Result(true, "ownership transfer to uid " + config.workloadUid() + " succeeded");
        } catch (IOException ex) {
            return new Result(false, "work root is not writable by the agent");
        } finally {
            if (scratch != null) {
                try {
                    JobWorkspace.deleteRecursively(scratch);
                } catch (IOException ignored) {
                    // The orphan sweeper will collect it.
                }
            }
        }
    }

    /**
     * Transfers ownership of a workspace directory to the workload identity.
     * Returns false when the platform refuses, which the caller treats as fatal at
     * startup and as a job failure at runtime.
     */
    static boolean chown(Path path, int uid, int gid) {
        try {
            UserPrincipalLookupService lookup = path.getFileSystem().getUserPrincipalLookupService();
            PosixFileAttributeView view = Files.getFileAttributeView(path, PosixFileAttributeView.class);
            if (view == null) {
                return false;
            }
            // Numeric ids have no guaranteed name, so look them up by the string
            // form; on Linux this resolves numeric principals directly.
            view.setOwner(lookup.lookupPrincipalByName(Integer.toString(uid)));
            view.setGroup(lookup.lookupPrincipalByGroupName(Integer.toString(gid)));
            return true;
        } catch (IOException | UnsupportedOperationException | SecurityException ex) {
            return false;
        }
    }

    static int currentUid() {
        return posixId(true, 65532);
    }

    static int currentGid() {
        return posixId(false, 65532);
    }

    private static int posixId(boolean uid, int fallback) {
        try {
            Object system = Class.forName("com.sun.security.auth.module.UnixSystem")
                    .getDeclaredConstructor().newInstance();
            java.lang.reflect.Method method = system.getClass().getMethod(uid ? "getUid" : "getGid");
            return (int) (long) (Long) method.invoke(system);
        } catch (Exception ex) {
            return fallback;
        }
    }
}
