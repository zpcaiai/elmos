from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def test_transformer_and_worker_images_ship_the_exact_legacy_jdk_registry() -> None:
    expected_stages = {
        "8": (
            "maven:3.9.11-eclipse-temurin-8@sha256:"
            "e3c149f44c95b0e9dd131862b3df67b3f061f7f6f3898a87b170564b3a943611"
        ),
        "11": (
            "maven:3.9.11-eclipse-temurin-11@sha256:"
            "c095e2421eaf3e5cb1573fd0474e68e17062866d454362349e17bbb75f44031e"
        ),
    }
    images = {
        "transformer": ROOT / "apps/java-engine-transformer/Dockerfile",
        "worker": ROOT / "apps/java-engine-worker/Dockerfile",
    }

    for owner, path in images.items():
        dockerfile = path.read_text(encoding="utf-8")
        for release, image in expected_stages.items():
            assert f"FROM {image} AS java{release}" in dockerfile, owner
            assert (
                f"COPY --from=java{release} /opt/java/openjdk "
                f"/opt/java/openjdk-{release}"
            ) in dockerfile, owner
        assert "COPY --from=java17 /opt/java/openjdk /opt/java/openjdk-17" in dockerfile

    assert (
        "ELMOS_TRANSFORMER_JAVA_HOMES="
        "8=/opt/java/openjdk-8,11=/opt/java/openjdk-11"
    ) in images["transformer"].read_text(encoding="utf-8")
    assert (
        "ELMOS_SPRING_UPGRADE_JAVA_HOMES="
        "8=/opt/java/openjdk-8,11=/opt/java/openjdk-11"
    ) in images["worker"].read_text(encoding="utf-8")


def test_application_configuration_and_ephemeral_controller_bind_the_registry() -> None:
    transformer_config = (
        ROOT / "apps/java-engine-transformer/src/main/resources/application.yml"
    ).read_text(encoding="utf-8")
    worker_config = (
        ROOT / "apps/java-engine-worker/src/main/resources/application.yml"
    ).read_text(encoding="utf-8")
    controller = (
        ROOT
        / "apps/java-engine-transformer/src/main/java/io/elmos/worker/"
        "EphemeralTransformerController.java"
    ).read_text(encoding="utf-8")
    broker = (
        ROOT
        / "apps/workspace-service/src/main/java/io/elmos/workspaceservice/"
        "EphemeralSpringTransformerBroker.java"
    ).read_text(encoding="utf-8")

    assert "java-homes: ${ELMOS_TRANSFORMER_JAVA_HOMES:}" in transformer_config
    assert "java-homes: ${ELMOS_SPRING_UPGRADE_JAVA_HOMES:}" in worker_config
    assert '@Value("${elmos.transformer.java-homes:}") String additionalJavaHomes' in controller
    assert (
        "SpringUpgradeConfiguration.javaHomes(\n"
        "                        sourceJavaHome, targetJavaHome, additionalJavaHomes)"
    ) in controller
    assert (
        '"spring-transformer-java8-java11-java17-java21-maven"'
        in broker
    )


def test_verifier_and_rootless_runtime_ship_and_select_java17_and_java21() -> None:
    verifier = (ROOT / "apps/java-engine-verifier/Dockerfile").read_text(encoding="utf-8")
    runtime = (ROOT / "apps/java-runtime-runner/Dockerfile").read_text(encoding="utf-8")
    runtime_service = (
        ROOT
        / "apps/workspace-service/src/main/java/io/elmos/workspaceservice/"
        "RootlessSpringRuntimeService.java"
    ).read_text(encoding="utf-8")

    for dockerfile in (verifier, runtime):
        assert (
            "FROM eclipse-temurin:17-jdk-jammy@sha256:"
            "29467857e8bde40ab1f7befecbda0ea764b95afec1cc7f89aa90f7a766577e19"
        ) in dockerfile
        assert "COPY --from=" in dockerfile and "/opt/java/openjdk-17" in dockerfile

    assert "ELMOS_VERIFIER_JAVA_HOMES=17=/opt/java/openjdk-17" in verifier
    assert 'case "17" -> "/opt/java/openjdk-17/bin/java"' in runtime_service
    assert 'case "21" -> "/opt/java/openjdk/bin/java"' in runtime_service
    assert '"spring-runtime-java17-java21"' in runtime_service


class SpringJdkRegistryTests(unittest.TestCase):
    def test_legacy_source_registry(self) -> None:
        test_transformer_and_worker_images_ship_the_exact_legacy_jdk_registry()

    def test_configuration_binding(self) -> None:
        test_application_configuration_and_ephemeral_controller_bind_the_registry()

    def test_target_verifier_and_runtime_registry(self) -> None:
        test_verifier_and_rootless_runtime_ship_and_select_java17_and_java21()
