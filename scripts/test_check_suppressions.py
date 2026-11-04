#!/usr/bin/env python3
"""Tests for check-suppressions.sh. Run: python3 -I -m unittest discover -s scripts -p 'test_*.py'"""
import os
import subprocess
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check-suppressions.sh")

PROFILE = """\
# Profile: demo

## Suppressions

Globs: `*.ts` `*.py`
Patterns: `eslint-disable` `# noqa`
  `ts-expect-error`

Worker rule: ignored by the script.

## Other
Patterns: `not-this-one`
"""


class CheckSuppressionsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.repo = os.path.join(self.dir.name, "repo")
        os.makedirs(os.path.join(self.repo, "src"))
        self.profile = os.path.join(self.dir.name, "profile.md")
        with open(self.profile, "w", encoding="utf-8") as handle:
            handle.write(PROFILE)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@t")
        self.git("config", "user.name", "t")
        self.write("src/a.ts", "ok\n// eslint-disable-next-line old\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.git("checkout", "-qb", "feat")

    def git(self, *args, cwd=None):
        return subprocess.run(
            ["git", *args], cwd=cwd or self.repo, check=True, capture_output=True, text=True
        )

    def write(self, rel, text):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "change")

    def check(self, *extra, cwd=None, profile=None):
        return subprocess.run(
            [SCRIPT, profile or self.profile, "main", *extra],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
        )

    def test_clean_branch_exits_zero(self):
        self.write("src/b.ts", "const x = 1\n")
        self.commit()
        self.assertEqual(self.check().returncode, 0)

    def test_preexisting_suppressions_are_not_reported(self):
        self.write("src/a.ts", "ok\n// eslint-disable-next-line old\nmore\n")
        self.commit()
        self.assertEqual(self.check().returncode, 0)

    def test_added_suppression_reports_file_and_line(self):
        self.write("src/a.ts", "ok\n// eslint-disable-next-line old\nx // ts-expect-error\n")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "src/a.ts:3: x // ts-expect-error")

    def test_wrapped_patterns_line_is_honored_and_other_sections_are_not(self):
        self.write("src/b.ts", "a // ts-expect-error\nb // not-this-one\n")
        self.commit()
        self.assertEqual(self.check().stdout.strip(), "src/b.ts:1: a // ts-expect-error")

    def test_each_profile_glob_applies_and_other_files_are_ignored(self):
        self.write("src/c.py", "x = 1  # noqa\n")
        self.write("README.md", "// eslint-disable\n")
        self.commit()
        self.assertEqual(self.check().stdout.strip(), "src/c.py:1: x = 1  # noqa")

    def test_added_line_starting_with_plus_plus_is_not_a_file_header(self):
        self.write("src/a.ts", "ok\n// eslint-disable-next-line old\n++ /dev/null\n// eslint-disable\n")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "src/a.ts:4: // eslint-disable")

    def test_runs_from_a_subdirectory_against_the_whole_repo(self):
        self.write("src/b.ts", "// eslint-disable\n")
        self.write("other/c.ts", "// eslint-disable\n")
        self.commit()
        result = self.check(cwd=os.path.join(self.repo, "src"))
        self.assertEqual(result.stdout.splitlines(), ["other/c.ts:1: // eslint-disable", "src/b.ts:1: // eslint-disable"])

    def test_external_diff_and_noprefix_config_do_not_hide_or_mangle_hits(self):
        self.git("config", "diff.noprefix", "true")
        self.git("config", "diff.external", "true")
        self.write("src/dir with space/d.ts", "// eslint-disable\n")
        self.commit()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.strip(), "src/dir with space/d.ts:1: // eslint-disable")

    def test_explicit_head_ref_is_checked_instead_of_head(self):
        self.write("src/b.ts", "// eslint-disable\n")
        self.commit()
        self.git("checkout", "-q", "main")
        self.assertEqual(self.check("feat").returncode, 1)
        self.assertEqual(self.check().returncode, 0)

    def test_deleted_files_are_ignored(self):
        os.remove(os.path.join(self.repo, "src/a.ts"))
        self.commit()
        self.assertEqual(self.check().returncode, 0)

    def test_setup_errors_exit_two(self):
        missing = os.path.join(self.dir.name, "missing.md")
        self.assertEqual(self.check(profile=missing).returncode, 2)
        empty = os.path.join(self.dir.name, "empty.md")
        with open(empty, "w", encoding="utf-8") as handle:
            handle.write("# Profile\n\n## Hermetic checks\n")
        self.assertEqual(self.check(profile=empty).returncode, 2)
        bad_base = subprocess.run(
            [SCRIPT, self.profile, "no-such-ref"], cwd=self.repo, capture_output=True, text=True
        )
        self.assertEqual(bad_base.returncode, 2)

    def test_usage_error_exits_two(self):
        result = subprocess.run([SCRIPT], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
