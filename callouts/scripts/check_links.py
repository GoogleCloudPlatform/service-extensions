#!/usr/bin/env python3
# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Checks that every relative markdown link under callouts/ resolves to a
real file or directory on disk.

This exists because callouts/python/extproc/example/README.md,
callouts/go/extproc/examples/README.md, and the Java equivalent all
pointed at a `samples/` directory that never existed, undetected for
some time. This script is meant to make that class of bug fail CI
instead.

Only checks relative links (no scheme, doesn't start with http(s)://,
mailto:, etc.) -- external URLs are out of scope here. `#anchor`-only
links and the fragment portion of a link are ignored, since anchors
depend on markdown rendering, not the filesystem.

Usage:
    python3 callouts/scripts/check_links.py
"""

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CALLOUTS_DIR = REPO_ROOT / "callouts"

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")  # http:, https:, mailto:, etc.


def find_links(text):
    for match in LINK_RE.finditer(text):
        target = match.group(1).strip()
        # Drop a trailing "title" in quotes, e.g. (path "title")
        target = target.split(" ", 1)[0]
        yield target


def check_file(md_path):
    errors = []
    text = md_path.read_text(encoding="utf-8", errors="replace")
    for target in find_links(text):
        if not target or target.startswith("#"):
            continue
        if SCHEME_RE.match(target):
            continue  # external link, not our concern here
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        if path_part.startswith("/"):
            # GitHub resolves a leading "/" against the repo root, not the filesystem root.
            resolved = (REPO_ROOT / path_part.lstrip("/")).resolve()
        else:
            resolved = (md_path.parent / path_part).resolve()
        if not resolved.exists():
            errors.append((md_path, target))
    return errors


def main():
    all_errors = []
    for md_path in sorted(CALLOUTS_DIR.rglob("*.md")):
        all_errors.extend(check_file(md_path))

    if all_errors:
        print(f"Found {len(all_errors)} broken relative link(s):\n", file=sys.stderr)
        for md_path, target in all_errors:
            rel = md_path.relative_to(REPO_ROOT)
            print(f"  {rel}: link target does not exist -> {target}", file=sys.stderr)
        return 1

    print("All relative links under callouts/ resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
