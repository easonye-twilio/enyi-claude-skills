#!/usr/bin/env python3
"""Tests for manifest.py. Run: python3 -I -m unittest discover -s scripts -p 'test_*.py'"""
import contextlib
import importlib.util
import io
import os
import stat
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("manifest", os.path.join(HERE, "manifest.py"))
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)

SAMPLE = """\
# Manifest: demo
Repo: demo
Base: main
Run: run_old

## Rollout (coordinator)
- Status: this is a rollout line, not a bucket field
1. ship it

## Bucket A — T-1: First
- Tickets: T-1
- Status: done (2026-10-08, dispatch ctx_1)
- Validated: pending
- PR: https://example.com/pull/1
- Notes: first line
  continuation of notes
  - nested bullet
- Acceptance:
  - A1 `make test`
  - Status: nested, must not match

## Bucket B — T-2: Second
- Tickets: T-2
- Status: pending
- Validated: n/a
- PR: —

```
## Bucket C — fenced, not a bucket
- Status: fenced
```

## Handoff
- Status: handoff text, not a bucket field
"""


def run(func, *args):
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            func(*args)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "m.md")
        self.write(SAMPLE)

    def write(self, text, newline=""):
        with open(self.path, "w", encoding="utf-8", newline=newline) as handle:
            handle.write(text)

    def read(self):
        with open(self.path, encoding="utf-8", newline="") as handle:
            return handle.read()

    def set(self, bucket, field, value):
        return run(manifest.cmd_set, self.path, bucket, field, value)

    def changed_lines(self, before):
        old, new = before.splitlines(), self.read().splitlines()
        return [line for line in new if line not in old], [line for line in old if line not in new]


class StatusTest(ManifestTest):
    def test_prints_run_and_each_bucket_with_first_word_values(self):
        code, out, _ = run(manifest.cmd_status, self.path)
        self.assertEqual(code, 0)
        self.assertEqual(
            out.splitlines(),
            [
                "Run: run_old",
                "A  done  validated=pending  pr=https://example.com/pull/1",
                "B  pending  validated=n/a",
            ],
        )

    def test_ignores_fenced_bucket_headings_and_non_bucket_sections(self):
        _, out, _ = run(manifest.cmd_status, self.path)
        self.assertNotIn("C ", out)
        self.assertNotIn("handoff", out)
        self.assertNotIn("rollout", out)

    def test_fails_when_no_buckets(self):
        self.write("# Manifest\nRepo: x\n")
        code, _, err = run(manifest.cmd_status, self.path)
        self.assertEqual(code, 1)
        self.assertIn("no `## Bucket` sections", err)

    def test_fails_on_missing_file(self):
        code, _, err = run(manifest.cmd_status, os.path.join(self.dir.name, "nope.md"))
        self.assertEqual(code, 1)
        self.assertIn("cannot read", err)

    def test_backticked_value_uses_inner_word(self):
        self.write(SAMPLE.replace("Run: run_old", "Run: `run_abc` (bound)"))
        _, out, _ = run(manifest.cmd_status, self.path)
        self.assertEqual(out.splitlines()[0], "Run: run_abc")

    def test_status_shows_worktree_and_dispatch_when_set(self):
        self.set("B", "Worktree", "/tmp/wt")
        self.set("B", "Dispatch", "ctx_9")
        _, out, _ = run(manifest.cmd_status, self.path)
        self.assertIn("B  pending  validated=n/a  worktree=/tmp/wt  dispatch=ctx_9", out)


class SetTest(ManifestTest):
    def test_replaces_only_the_target_line(self):
        before = self.read()
        code, out, _ = self.set("B", "Status", "dispatched")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "B Status: dispatched")
        added, removed = self.changed_lines(before)
        self.assertEqual(added, ["- Status: dispatched"])
        self.assertEqual(removed, ["- Status: pending"])

    def test_older_prose_value_is_replaced_whole(self):
        self.set("A", "Status", "failed")
        self.assertIn("- Status: failed\n", self.read())
        self.assertNotIn("dispatch ctx_1", self.read())

    def test_replacing_a_field_drops_its_continuation_lines(self):
        self.set("A", "Notes", "rewritten")
        text = self.read()
        self.assertIn("- Notes: rewritten\n- Acceptance:", text)
        self.assertNotIn("continuation of notes", text)
        self.assertNotIn("nested bullet", text)

    def test_nested_field_lookalike_is_not_matched(self):
        self.set("A", "Status", "failed")
        self.assertIn("  - Status: nested, must not match", self.read())

    def test_other_sections_stay_byte_identical(self):
        self.set("B", "Status", "done")
        text = self.read()
        self.assertIn("- Status: this is a rollout line, not a bucket field\n1. ship it\n", text)
        self.assertIn("- Status: fenced\n```", text)
        self.assertTrue(text.endswith("- Status: handoff text, not a bucket field\n"))

    def test_inserts_missing_field_after_last_field_before_trailing_blank(self):
        self.set("B", "Worktree", "/tmp/wt")
        text = self.read()
        self.assertIn("- PR: —\n- Worktree: /tmp/wt\n\n```", text)

    def test_hyphenated_validated_at_field_is_inserted_then_replaced(self):
        self.set("B", "Validated-at", "abc123")
        self.assertIn("- PR: —\n- Validated-at: abc123\n\n```", self.read())
        self.set("B", "validated-at", "def456")
        text = self.read()
        self.assertIn("- Validated-at: def456\n", text)
        self.assertNotIn("abc123", text)

    def test_counters_show_in_status(self):
        self.set("A", "Fixes", "1")
        code, out, _ = run(manifest.cmd_status, self.path)
        self.assertIn("fixes=1", out)

    def test_redispatches_counter_is_its_own_field_and_survives_notes_writes(self):
        self.set("B", "Redispatches", "1")
        self.set("B", "Notes", "nits")
        text = self.read()
        self.assertIn("- Redispatches: 1\n", text)
        self.assertIn("- Notes: nits\n", text)

    def test_inserts_into_last_bucket_without_trailing_newline(self):
        self.write("# M\n\n## Bucket A — x\n- Status: pending")
        code, _, _ = self.set("A", "PR", "https://example.com/1")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.read(), "# M\n\n## Bucket A — x\n- Status: pending\n- PR: https://example.com/1\n"
        )

    def test_bucket_and_field_names_are_case_insensitive(self):
        self.set("b", "status", "done")
        self.assertIn("## Bucket B — T-2: Second\n- Tickets: T-2\n- Status: done\n", self.read())

    def test_manifest_header_field_is_replaced(self):
        before = self.read()
        self.set("manifest", "Run", "run_new")
        added, removed = self.changed_lines(before)
        self.assertEqual((added, removed), (["Run: run_new"], ["Run: run_old"]))

    def test_manifest_header_field_is_inserted_before_first_section(self):
        self.write(SAMPLE.replace("Run: run_old\n", ""))
        self.set("manifest", "Run", "run_new")
        self.assertIn("Base: main\nRun: run_new\n\n## Rollout", self.read())

    def test_crlf_line_endings_are_preserved(self):
        self.write(SAMPLE, newline="")
        crlf = SAMPLE.replace("\n", "\r\n")
        self.write(crlf)
        self.set("B", "Worktree", "/tmp/wt")
        self.set("B", "Status", "dispatched")
        text = self.read()
        self.assertNotIn("\n", text.replace("\r\n", ""))
        self.assertIn("- Status: dispatched\r\n", text)
        self.assertIn("- Worktree: /tmp/wt\r\n", text)

    def test_value_is_stripped_and_kept_verbatim(self):
        self.set("A", "Notes", "  uses `#` and \\ and --flag  ")
        self.assertIn("- Notes: uses `#` and \\ and --flag\n", self.read())

    def test_file_mode_is_preserved_and_no_temp_files_left(self):
        os.chmod(self.path, 0o640)
        self.set("A", "Status", "failed")
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)
        self.assertEqual(os.listdir(self.dir.name), ["m.md"])


class SetValidationTest(ManifestTest):
    def assert_rejected(self, bucket, field, value, fragment):
        before = self.read()
        code, _, err = self.set(bucket, field, value)
        self.assertEqual(code, 2)
        self.assertIn(fragment, err)
        self.assertEqual(self.read(), before)

    def test_rejects_unknown_field(self):
        self.assert_rejected("A", "Tickets", "T-9", "field must be one of")

    def test_rejects_non_integer_counters(self):
        self.assert_rejected("A", "Redispatches", "two", "non-negative integer")
        self.assert_rejected("A", "Fixes", "-1", "non-negative integer")

    def test_rejects_bad_status_value(self):
        self.assert_rejected("A", "Status", "bogus", "Status must start with one of")

    def test_rejects_bad_validated_value(self):
        self.assert_rejected("A", "Validated", "maybe", "Validated must start with one of")

    def test_accepts_every_documented_validated_value_with_trailing_prose(self):
        for value in ("pass", "fail", "waiting", "unverified", "pending", "n/a — no UI change"):
            with self.subTest(value=value):
                self.assertEqual(self.set("A", "Validated", value)[0], 0)

    def test_status_check_is_case_insensitive_on_the_first_word(self):
        self.assertEqual(self.set("A", "Status", "Done (today)")[0], 0)

    def test_rejects_unknown_bucket_and_lists_known_ones(self):
        self.assert_rejected("Z", "Status", "done", "known: A, B")

    def test_rejects_multiline_value(self):
        self.assert_rejected("A", "Notes", "one\ntwo", "single line")

    def test_rejects_duplicate_bucket_headings(self):
        self.write(SAMPLE + "\n## Bucket A — again\n- Status: pending\n")
        code, _, err = self.set("A", "Status", "done")
        self.assertEqual(code, 1)
        self.assertIn("duplicate bucket heading", err)


class RobustnessTest(ManifestTest):
    def test_set_keeps_a_code_fence_that_follows_the_field(self):
        self.write("## Bucket A — x\n- Notes: old\n```\ncode\n```\n")
        self.set("A", "Notes", "new")
        self.assertEqual(self.read(), "## Bucket A — x\n- Notes: new\n```\ncode\n```\n")

    def test_longer_fence_is_not_closed_by_a_shorter_inner_fence(self):
        self.write(
            "## Bucket A — x\n- Status: pending\n"
            "````\n```\n## Bucket Z — inside\n- Status: inside\n```\n````\n"
            "\n## Bucket B — y\n- Status: pending\n"
        )
        self.assertEqual(self.set("B", "Status", "done")[0], 0)
        self.assertEqual(self.set("Z", "Status", "done")[0], 2)

    def test_tilde_fence_is_not_closed_by_backticks(self):
        self.write("## Bucket A — x\n- Status: pending\n~~~\n```\n## Bucket Z — inside\n~~~\n## Bucket B — y\n- Status: pending\n")
        _, out, _ = run(manifest.cmd_status, self.path)
        self.assertEqual([line.split()[0] for line in out.splitlines()], ["A", "B"])

    def test_symlinked_manifest_keeps_the_link_and_updates_the_target(self):
        link = os.path.join(self.dir.name, "link.md")
        os.symlink(self.path, link)
        code, _, _ = run(manifest.cmd_set, link, "B", "Status", "done")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.islink(link))
        self.assertIn("- Status: done\n", self.read())

    def locked_set(self, bucket, field, value):
        with manifest.locked(self.path):
            manifest.apply_set(self.path, bucket, field, value)

    def test_concurrent_sets_lose_no_updates(self):
        import threading

        self.write("## Bucket A — x\n- Status: pending\n")
        fields = ["PR", "Notes", "Worktree", "Dispatch", "Evidence"] * 6
        threads = [
            threading.Thread(target=self.locked_set, args=("A", f, str(i)))
            for i, f in enumerate(fields)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        text = self.read()
        for field in {"PR", "Notes", "Worktree", "Dispatch", "Evidence"}:
            self.assertEqual(text.count(f"- {field}: "), 1, field)


class MainTest(unittest.TestCase):
    def test_usage_on_bad_arguments(self):
        code, _, err = run(manifest.main, ["manifest.py"])
        self.assertEqual(code, 2)
        self.assertIn("manifest.py status", err)

    def test_dispatches_status_and_set(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "m.md")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(SAMPLE)
            code, _, _ = run(manifest.main, ["manifest.py", "set", path, "B", "Status", "done"])
            self.assertEqual(code, 0)
            code, out, _ = run(manifest.main, ["manifest.py", "status", path])
            self.assertEqual(code, 0)
            self.assertIn("B  done", out)


if __name__ == "__main__":
    unittest.main()
