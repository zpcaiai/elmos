package io.elmos.worker.shim;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class SpringPrivateArtifactShimGeneratorTest {

    @Test
    void shouldGenerateShimsFromDiagnostics(@TempDir Path tempDir) throws IOException {
        Path srcMain = tempDir.resolve("src/main/java");
        Files.createDirectories(srcMain);

        List<String> diagnostics = List.of(
                "[ERROR] /path/ToService.java:[15,35] package com.corp.internal.sso does not exist",
                "[ERROR] /path/ToClient.java:[22,40] cannot find symbol",
                "  symbol:   class CorporateSsoClient",
                "  location: package com.corp.internal.sso",
                "[ERROR] /path/ToDto.java:[30,12] cannot find symbol",
                "  symbol:   class SsoTokenResponse",
                "  location: package com.corp.internal.sso"
        );

        var result = SpringPrivateArtifactShimGenerator.generateShimsFromDiagnostics(tempDir, diagnostics);

        assertThat(result.generated()).isTrue();
        assertThat(result.shimCount()).isGreaterThanOrEqualTo(2);
        assertThat(result.generatedPackages()).contains("com.corp.internal.sso");

        // Verify generated client file
        Path clientFile = srcMain.resolve("com/corp/internal/sso/CorporateSsoClient.java");
        assertThat(clientFile).exists();
        String clientCode = Files.readString(clientFile);
        assertThat(clientCode).contains("package com.corp.internal.sso;");
        assertThat(clientCode).contains("CorporateSsoClient");
        assertThat(clientCode).contains("Automatically synthesized Mock Shim stub");

        // Verify generated DTO file
        Path dtoFile = srcMain.resolve("com/corp/internal/sso/SsoTokenResponse.java");
        assertThat(dtoFile).exists();
        String dtoCode = Files.readString(dtoFile);
        assertThat(dtoCode).contains("public class SsoTokenResponse");
    }

    @Test
    void shouldGenerateExplicitShims(@TempDir Path tempDir) throws IOException {
        Path srcMain = tempDir.resolve("src/main/java");
        Files.createDirectories(srcMain);

        var result = SpringPrivateArtifactShimGenerator.generateExplicitShims(
                tempDir,
                "com.enterprise.legacy.service",
                List.of("LegacyPaymentService", "ILegacyPaymentGateway", "PaymentReceiptDTO")
        );

        assertThat(result.generated()).isTrue();
        assertThat(result.shimCount()).isEqualTo(3);

        // Service check
        Path svcPath = srcMain.resolve("com/enterprise/legacy/service/LegacyPaymentService.java");
        assertThat(svcPath).exists();
        String svcCode = Files.readString(svcPath);
        assertThat(svcCode).contains("@ConditionalOnMissingBean");
        assertThat(svcCode).contains("@Component");

        // Interface check
        Path ifacePath = srcMain.resolve("com/enterprise/legacy/service/ILegacyPaymentGateway.java");
        assertThat(ifacePath).exists();
        String ifaceCode = Files.readString(ifacePath);
        assertThat(ifaceCode).contains("public interface ILegacyPaymentGateway");
    }

    @Test
    void shouldHandleEmptyOrNullDiagnostics(@TempDir Path tempDir) {
        var r1 = SpringPrivateArtifactShimGenerator.generateShimsFromDiagnostics(tempDir, List.of());
        assertThat(r1.generated()).isFalse();
        assertThat(r1.shimCount()).isZero();

        var r2 = SpringPrivateArtifactShimGenerator.generateShimsFromDiagnostics(tempDir, null);
        assertThat(r2.generated()).isFalse();
        assertThat(r2.shimCount()).isZero();
    }
}
