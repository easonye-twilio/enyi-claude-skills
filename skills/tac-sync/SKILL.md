---
name: tac-sync
description: Refresh the local TAC context. Re-snapshots Google Docs listed in ~/.claude/references/tac/INDEX.md to markdown and fast-forwards the TAC repos. Use when the user runs /tac-sync or says the TAC docs or repos changed.
---

# TAC sync

1. Read `~/.claude/references/tac/INDEX.md`.
2. **Google Docs.** Handle every row that has a docs.google.com URL and a `snapshot` filename:
   - Get the file ID from the URL and read the doc with Google Drive `read_file_content`.
   - Write the content to `~/.claude/references/tac/<snapshot>` as markdown. Keep headings and tables. Drop images and boilerplate.
   - Start the file with this header: `<!-- source: <url> | doc modified: <modifiedTime> | synced: <today> -->`.
   - Before reading, check `get_file_metadata.modifiedTime` against the existing header. If the doc hasn't changed, skip it.
   - These docs are large. Run each one in a `sonnet` subagent that writes the file and returns only the path and size.
3. **Repos.** For each local path in the index, run `git -C <path> pull --ff-only`. If the working tree is dirty or the branch isn't main or master, skip the repo and report it. Never stash or reset.
   - If a path doesn't exist, clone it with the user's `goto <org>/<repo>` shell function. Twilio-public repos live under the `twilio` org.
4. Report a short table: each source and whether it was updated, unchanged, skipped (with the reason) or failed.
