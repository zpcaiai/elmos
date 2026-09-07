package io.elmos.runner;

import java.io.IOException;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.util.List;

/**
 * Durable, owner-only node credential state.
 *
 * <p>A rotation has two durable phases. The next token and request id are written
 * before the HTTP request; after confirmation, the pending token becomes current.
 * After a crash the agent can try the pending token first and therefore recover
 * even if the server committed while the response was lost.</p>
 */
final class NodeCredentialStore {
    record State(
            String currentToken,
            String pendingToken,
            String rotationRequestId,
            boolean preexisting) {
        boolean hasPendingRotation() {
            return pendingToken != null && rotationRequestId != null;
        }
    }

    private static final String VERSION =
            "ELMOS_RUNNER_NODE_CREDENTIAL_V2";
    private final Path path;
    private State state;

    NodeCredentialStore(Path workRoot, String initialToken) {
        this.path = workRoot.resolve(".runner-node-credential").normalize();
        if (!path.getParent().equals(workRoot.normalize())) {
            throw new AgentConfig.ConfigException(
                    "runner node credential path escapes work root");
        }
        this.state = loadOrCreate(initialToken);
    }

    synchronized State state() {
        return state;
    }

    synchronized void stageRotation(String nextToken, String requestId) {
        if (state.hasPendingRotation()) {
            return;
        }
        State next = new State(
                state.currentToken(), nextToken, requestId,
                state.preexisting());
        persist(next);
        state = next;
    }

    synchronized void markEnrolled() {
        if (state.preexisting()) {
            return;
        }
        State next = new State(
                state.currentToken(), state.pendingToken(),
                state.rotationRequestId(), true);
        persist(next);
        state = next;
    }

    synchronized void commitPending() {
        if (!state.hasPendingRotation()) {
            return;
        }
        State next = new State(
                state.pendingToken(), null, null, true);
        persist(next);
        state = next;
    }

    private State loadOrCreate(String initialToken) {
        try {
            Files.createDirectories(path.getParent());
            if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
                State created = new State(
                        requireToken(initialToken), null, null, false);
                persist(created);
                return created;
            }
            if (Files.isSymbolicLink(path)
                    || !Files.isRegularFile(
                            path, LinkOption.NOFOLLOW_LINKS)) {
                throw new AgentConfig.ConfigException(
                        "runner node credential file is unsafe");
            }
            requireOwnerOnly(path);
            List<String> lines = Files.readAllLines(path);
            if (lines.size() != 5 || !VERSION.equals(lines.get(0))) {
                throw new AgentConfig.ConfigException(
                        "runner node credential file is malformed");
            }
            String current = requireToken(lines.get(1));
            String pending = "-".equals(lines.get(2))
                    ? null : requireToken(lines.get(2));
            String requestId = "-".equals(lines.get(3))
                    ? null : requireRequestId(lines.get(3));
            if ((pending == null) != (requestId == null)) {
                throw new AgentConfig.ConfigException(
                        "runner node credential rotation state is incomplete");
            }
            boolean enrolled = switch (lines.get(4)) {
                case "ENROLLED" -> true;
                case "NEW" -> false;
                default -> throw new AgentConfig.ConfigException(
                        "runner node credential enrollment state is malformed");
            };
            return new State(
                    current, pending, requestId, enrolled);
        } catch (AgentConfig.ConfigException error) {
            throw error;
        } catch (IOException error) {
            throw new AgentConfig.ConfigException(
                    "runner node credential file is unavailable");
        }
    }

    private void persist(State next) {
        Path temporary = path.resolveSibling(
                path.getFileName() + ".next");
        try {
            Files.deleteIfExists(temporary);
            Files.createFile(
                    temporary,
                    PosixFilePermissions.asFileAttribute(
                            PosixFilePermissions.fromString(
                                    "rw-------")));
            Files.writeString(
                    temporary,
                    VERSION + "\n"
                            + requireToken(next.currentToken()) + "\n"
                            + (next.pendingToken() == null
                                ? "-" : requireToken(next.pendingToken()))
                            + "\n"
                            + (next.rotationRequestId() == null
                                ? "-" : requireRequestId(
                                        next.rotationRequestId()))
                            + "\n"
                            + (next.preexisting()
                                ? "ENROLLED" : "NEW")
                            + "\n",
                    StandardOpenOption.TRUNCATE_EXISTING);
            try {
                Files.move(
                        temporary, path,
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException ignored) {
                Files.move(
                        temporary, path,
                        StandardCopyOption.REPLACE_EXISTING);
            }
            requireOwnerOnly(path);
        } catch (AgentConfig.ConfigException error) {
            throw error;
        } catch (IOException error) {
            throw new AgentConfig.ConfigException(
                    "cannot persist runner node credential");
        } finally {
            try {
                Files.deleteIfExists(temporary);
            } catch (IOException ignored) {
                // A .next file never authenticates and is overwritten next time.
            }
        }
    }

    private static void requireOwnerOnly(Path target) throws IOException {
        try {
            var permissions = Files.getPosixFilePermissions(
                    target, LinkOption.NOFOLLOW_LINKS);
            if (!permissions.equals(
                    PosixFilePermissions.fromString("rw-------"))) {
                throw new AgentConfig.ConfigException(
                        "runner node credential file must be owner-only");
            }
        } catch (UnsupportedOperationException ignored) {
            // Checked by the platform-specific deployment ACL.
        }
    }

    private static String requireToken(String value) {
        if (value == null
                || !value.matches("^[A-Za-z0-9_-]{32,256}$")) {
            throw new AgentConfig.ConfigException(
                    "runner node credential token is malformed");
        }
        return value;
    }

    private static String requireRequestId(String value) {
        if (value == null
                || !value.matches(
                        "^[A-Za-z0-9][A-Za-z0-9._:-]{7,95}$")) {
            throw new AgentConfig.ConfigException(
                    "runner credential rotation id is malformed");
        }
        return value;
    }
}
