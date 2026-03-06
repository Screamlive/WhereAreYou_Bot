import unittest
from unittest.mock import patch

from app.ops import governance_ops


class GovernanceOpsTests(unittest.TestCase):
    def test_parse_github_repo_variants(self):
        self.assertEqual(
            governance_ops.parse_github_repo("git@github.com:owner/repo.git"),
            ("owner", "repo"),
        )
        self.assertEqual(
            governance_ops.parse_github_repo("https://github.com/owner/repo"),
            ("owner", "repo"),
        )
        self.assertEqual(
            governance_ops.parse_github_repo("ssh://git@github.com/owner/repo.git"),
            ("owner", "repo"),
        )
        self.assertIsNone(governance_ops.parse_github_repo("https://example.com/owner/repo.git"))

    def test_extract_status_checks(self):
        payload = {
            "required_status_checks": {
                "contexts": ["security-gate", "unit-tests"],
                "checks": [{"context": "lint"}, "build"],
            }
        }
        checks = governance_ops._extract_status_checks(payload)
        self.assertIn("security-gate", checks)
        self.assertIn("unit-tests", checks)
        self.assertIn("lint", checks)
        self.assertIn("build", checks)

    @patch("app.ops.governance_ops.shutil.which", return_value=None)
    def test_branch_protection_warn_when_gh_missing(self, _mock_which):
        result = governance_ops._check_branch_protection("main")
        self.assertEqual(result.status, "warn")


if __name__ == "__main__":
    unittest.main()
