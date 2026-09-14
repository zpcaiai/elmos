from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class BusinessLineEvidenceClaimsTest(unittest.TestCase):
    def test_readme_does_not_promote_local_evidence_to_certification(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")

        forbidden_claims = (
            "100% 工业级生产系统认证",
            "CERTIFIED_INDEPENDENT",
            "Deloitte Tech Assurance",
            "获 Ethan 独立",
        )
        for claim in forbidden_claims:
            with self.subTest(claim=claim):
                self.assertNotIn(claim, readme)

        self.assertIn("0 条 certified", readme)
        self.assertIn("NOT_RUN / NOT_CERTIFIED", readme)

    def test_closure_matrix_tracks_current_local_facts_and_open_evidence(self) -> None:
        matrix = (
            REPOSITORY_ROOT / "docs" / "BUSINESS_LINE_CLOSURE_MATRIX.md"
        ).read_text(encoding="utf-8")

        for fact in (
            "210 路线中 90 `limited`、120 `research`、0 `certified`",
            "1,916/1,916 SQL 单元有显式处置",
            "13 条精确版本路线已有仓库自有源构建",
            "生产矩阵证据需按当前源码重新生成",
            "BLOCKED / NOT_CERTIFIED",
        ):
            with self.subTest(fact=fact):
                self.assertIn(fact, matrix)

        self.assertNotIn("修复当前 CI", matrix)
        self.assertNotIn("修复当前项目生成 CI 失败", matrix)


if __name__ == "__main__":
    unittest.main()
