import json

import pytest

from elmos_spring_modernization.cli import main

def test_cli_scan(tmp_path, capsys):
    pom_path = tmp_path / "pom.xml"
    pom_path.write_text("""<project xmlns="http://maven.apache.org/POM/4.0.0">
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>2.7.18</version>
    </parent>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>""", encoding="utf-8")

    main(["scan", "--project", str(tmp_path), "--format", "json"])
    captured = capsys.readouterr().out
    assert "Executed scan" in captured
    assert "2.7" in captured

def test_cli_plan(tmp_path, capsys):
    plan_file = tmp_path / "migration_plan.json"
    main(["plan", "--project", str(tmp_path), "--target", "3.2", "--plan", str(plan_file)])
    captured = capsys.readouterr().out
    assert "Executed plan" in captured
    assert plan_file.exists()
    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
    assert plan_data["target_version"] == "3.2"
    assert len(plan_data["rules"]) > 0

def test_cli_apply_dry_run(tmp_path, capsys):
    main(["apply", "--project", str(tmp_path), "--target", "3.2", "--dry-run"])
    captured = capsys.readouterr().out
    assert "Executed apply" in captured

def test_cli_verify_requires_runtime_evidence():
    with pytest.raises(SystemExit):
        main(["verify"])


def test_cli_verify_reports_transport_failure(tmp_path, capsys):
    requests_file = tmp_path / "requests.json"
    requests_file.write_text('[{"method": "GET", "path": "/health"}]', encoding="utf-8")
    main([
        "verify",
        "--requests", str(requests_file),
        "--source-url", "http://127.0.0.1:1",
        "--target-url", "http://127.0.0.1:2",
        "--request-timeout", "0.1",
    ])
    captured = capsys.readouterr().out
    assert "Executed verify" in captured
    assert '"status": "FAILED"' in captured
    assert '"failed": 1' in captured

def test_cli_report(tmp_path, capsys):
    results_file = tmp_path / "report.json"
    main(["report", "--project", str(tmp_path), "--target", "3.2", "--results", str(results_file)])
    captured = capsys.readouterr().out
    assert "Executed report" in captured
    assert results_file.exists()
    data = json.loads(results_file.read_text(encoding="utf-8"))
    assert "modernization_report" in data
