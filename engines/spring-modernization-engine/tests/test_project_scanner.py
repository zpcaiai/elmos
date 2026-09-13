from elmos_spring_modernization.project_scanner import SpringProjectScanner
from elmos_spring_modernization.models import SpringVersion

def test_scan():
    scanner = SpringProjectScanner()
    profile = scanner.scan("/tmp")
    assert profile.version == SpringVersion.BOOT_2_7
