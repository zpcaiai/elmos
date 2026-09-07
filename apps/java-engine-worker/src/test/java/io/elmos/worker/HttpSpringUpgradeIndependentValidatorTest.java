package io.elmos.worker;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Clock;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpSpringUpgradeIndependentValidatorTest {
    @TempDir Path temporary;

    @Test
    void productionRequiresHttpsAndTestTransportAllowsOnlyLoopbackHttp() throws Exception {
        Path secret = temporary.toRealPath().resolve("verifier.secret");
        Files.writeString(secret, "verifier-transport-test-secret-0123456789", StandardCharsets.UTF_8);
        Files.setPosixFilePermissions(secret, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE));
        ObjectMapper json = new ObjectMapper().findAndRegisterModules();

        assertDoesNotThrow(() -> new HttpSpringUpgradeIndependentValidator(
                temporary,
                URI.create("https://verifier.example.test"),
                secret,
                "verifier-test",
                json,
                Clock.systemUTC()
        ));

        IllegalArgumentException productionHttp = assertThrows(
                IllegalArgumentException.class,
                () -> new HttpSpringUpgradeIndependentValidator(
                        temporary,
                        URI.create("http://127.0.0.1:8082"),
                        secret,
                        "verifier-test",
                        json,
                        Clock.systemUTC()
                ));
        assertTrue(productionHttp.getMessage().contains("absolute HTTPS"));
        assertThrows(IllegalArgumentException.class, () -> new HttpSpringUpgradeIndependentValidator(
                temporary,
                URI.create("/relative-verifier"),
                secret,
                "verifier-test",
                json,
                Clock.systemUTC()
        ));

        assertDoesNotThrow(() -> new HttpSpringUpgradeIndependentValidator(
                temporary,
                URI.create("http://127.0.0.1:8082"),
                secret,
                "verifier-test",
                json,
                Clock.systemUTC(),
                true
        ));
        assertThrows(IllegalArgumentException.class, () -> new HttpSpringUpgradeIndependentValidator(
                temporary,
                URI.create("http://verifier.example.test:8082"),
                secret,
                "verifier-test",
                json,
                Clock.systemUTC(),
                true
        ));
    }
}
