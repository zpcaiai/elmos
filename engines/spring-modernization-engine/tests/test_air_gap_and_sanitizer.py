from __future__ import annotations

import json
from pathlib import Path
import tarfile
import tempfile

from elmos_spring_modernization.enterprise_source_sanitizer import (
    EnterpriseSourceSanitizer,
    SanitizationManifest,
)
from elmos_spring_modernization.air_gapped_offline_packager import (
    AirGappedOfflinePackager,
)


def test_enterprise_source_sanitizer_masking_and_reversibility():
    raw_config = """spring:
  datasource:
    url: jdbc:mysql://dbuser:MySuperSecretP@ss99@10.240.0.15:3306/production_db
    username: dbuser
    password: MySuperSecretP@ss99
  security:
    oauth2:
      client:
        secret: mock_oauth_client_secret_xyz987
"""

    manifest = SanitizationManifest(project_id="test-app", total_sanitized_items=0)
    sanitized = EnterpriseSourceSanitizer.sanitize_content(raw_config, "application.yml", manifest)

    # Validate secrets are masked
    assert "MySuperSecretP@ss99" not in sanitized
    assert "10.240.0.15" not in sanitized
    assert "mock_oauth_client_secret_xyz987" not in sanitized

    assert "__ELMOS_SAN_DB_PASSWORD_" in sanitized or "__ELMOS_SAN_JDBC_CREDENTIALS_" in sanitized
    assert "__ELMOS_SAN_INTERNAL_IP_" in sanitized
    assert "__ELMOS_SAN_API_SECRET_" in sanitized

    # Validate manifest
    assert manifest.total_sanitized_items >= 2
    assert "application.yml" in manifest.sanitized_files

    # Validate bit-exact reversibility
    restored = EnterpriseSourceSanitizer.desanitize_content(sanitized, manifest)
    assert restored == raw_config


def test_enterprise_source_sanitizer_directory_workflow():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        app_yml = root / "src" / "main" / "resources" / "application.yml"
        app_yml.parent.mkdir(parents=True, exist_ok=True)
        app_yml.write_text("db.password=ProdSecurePassword1234\nhost=192.168.1.50\n", encoding="utf-8")

        java_file = root / "src" / "main" / "java" / "Config.java"
        java_file.parent.mkdir(parents=True, exist_ok=True)
        java_file.write_text('String token = "auth_token: secretToken123456";\n', encoding="utf-8")

        manifest = EnterpriseSourceSanitizer.sanitize_directory(root, project_id="demo")

        assert "ProdSecurePassword1234" not in app_yml.read_text(encoding="utf-8")
        assert "192.168.1.50" not in app_yml.read_text(encoding="utf-8")
        assert "secretToken123456" not in java_file.read_text(encoding="utf-8")

        # Now reverse desanitize
        restored_count = EnterpriseSourceSanitizer.desanitize_directory(root, manifest)
        assert restored_count >= 2

        assert "db.password=ProdSecurePassword1234" in app_yml.read_text(encoding="utf-8")
        assert "host=192.168.1.50" in app_yml.read_text(encoding="utf-8")
        assert "secretToken123456" in java_file.read_text(encoding="utf-8")


def test_air_gapped_offline_packager_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        src_dir = Path(tmpdir) / "source_project"
        src_dir.mkdir()
        (src_dir / "pom.xml").write_text("<project><version>3.5.3</version></project>", encoding="utf-8")
        (src_dir / "Main.java").write_text("public class Main {}", encoding="utf-8")

        archive_file = Path(tmpdir) / "dist" / "modernization-package.tar.gz"

        # 1. Package
        AirGappedOfflinePackager.create_package(src_dir, archive_file, package_id="pkg-001")
        assert archive_file.is_file()

        # 2. Verify valid package
        extract_dir = Path(tmpdir) / "extracted"
        result = AirGappedOfflinePackager.verify_package(archive_file, extract_to_dir=extract_dir)

        assert result.is_valid
        assert result.package_id == "pkg-001"
        assert result.total_files_verified == 2
        assert len(result.corrupted_files) == 0
        assert (extract_dir / "pom.xml").is_file()
        assert (extract_dir / "Main.java").is_file()

        # 3. Test tampering detection
        tampered_archive = Path(tmpdir) / "tampered.tar.gz"
        # Extract, tamper with a file, repack without updating manifest
        with tarfile.open(archive_file, "r:gz") as tar:
            tar.extractall(Path(tmpdir) / "tamper_scratch")

        (Path(tmpdir) / "tamper_scratch" / "Main.java").write_text("public class Tampered {}", encoding="utf-8")
        with tarfile.open(tampered_archive, "w:gz") as tar:
            for f in (Path(tmpdir) / "tamper_scratch").iterdir():
                tar.add(f, arcname=f.name)

        tampered_result = AirGappedOfflinePackager.verify_package(tampered_archive)
        assert not tampered_result.is_valid
        assert "Main.java" in tampered_result.corrupted_files
