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
"""Checks that every example directory has a README.md.

This exists because python/extauthz/example/block_ip/ and
python/extproc/l4_example/network_basic/ went undocumented for a
while with nothing to catch it. New example directories are expected
to ship a README the same day the code does.

"Example directories" are the immediate children of the roots below,
minus a short, explicit exclude-list for known non-example helpers
(test harnesses, shared service code, etc.) -- new folders are
opt-out, not opt-in, so a forgotten README fails CI by default.

Usage:
    python3 callouts/scripts/check_example_readmes.py
"""

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CALLOUTS_DIR = REPO_ROOT / "callouts"

EXAMPLE_ROOTS = [
    "python/extproc/example",
    "python/extauthz/example",
    "python/extproc/l4_example",
    "go/extproc/examples",
    "java/service-callout/src/main/java/example",
]

# Known non-example helper directories that intentionally have no
# example README of their own.
EXCLUDE_DIR_NAMES = {"e2e_tests", "client"}


def main():
    missing = []
    for root_rel in EXAMPLE_ROOTS:
        root = CALLOUTS_DIR / root_rel
        if not root.is_dir():
            print(f"warning: example root does not exist: {root_rel}", file=sys.stderr)
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name in EXCLUDE_DIR_NAMES:
                continue
            if not (child / "README.md").exists():
                missing.append(child.relative_to(REPO_ROOT))

    if missing:
        print(f"{len(missing)} example director{'y' if len(missing)==1 else 'ies'} missing a README.md:\n",
              file=sys.stderr)
        for m in missing:
            print(f"  {m}/", file=sys.stderr)
        return 1

    print("Every example directory has a README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
