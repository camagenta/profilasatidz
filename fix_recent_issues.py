#!/usr/bin/env python3
"""
Fix body of recently-created issues (#127-#136) to reflect updated
completeness values from master.

Strategy: re-run build_issue_body() with current master data, then
gh issue edit <num> --body <new_body> for each issue in the range.
"""
import json
import re
import subprocess
import sys
from profile_issue_guardian import (
    build_issue_body, load_detail, load_kajianlive_mapping,
    GH_REPO, GH_LABEL
)

# Range of issues created in this session
ISSUE_RANGE = range(127, 137)


def fetch_issue_title_body(num):
    r = subprocess.run(
        ["gh", "issue", "view", str(num), "--repo", GH_REPO, "--json", "title,body"],
        capture_output=True, text=True, timeout=15
    )
    if r.returncode != 0:
        return None, None
    try:
        data = json.loads(r.stdout)
        return data.get("title", ""), data.get("body", "")
    except json.JSONDecodeError:
        return None, None


def main():
    with open("asatidz_master.json") as f:
        master = json.load(f)
    master_by_id = {m["id"]: m for m in master}

    mapping = load_kajianlive_mapping()

    fixed = 0
    for num in ISSUE_RANGE:
        title, old_body = fetch_issue_title_body(num)
        if not title or not old_body:
            print(f"#{num}: cannot fetch, skipping")
            continue

        prefix = "[Profil Asatidz] "
        if not title.startswith(prefix):
            print(f"#{num}: not a profil issue ({title}), skipping")
            continue
        name = title[len(prefix):].strip()

        # Find master entry by name
        entry = None
        for m in master:
            if m.get("name", "").strip().lower() == name.lower():
                entry = m
                break
        if not entry:
            print(f"#{num}: {name} not in master, skipping")
            continue

        profile_id = entry.get("id", "")
        detail = load_detail(profile_id)
        kl_info = mapping.get(profile_id)
        new_body = build_issue_body(name, profile_id, entry, detail, kl_info)

        if new_body == old_body:
            print(f"#{num}: {name} - body unchanged, skipping edit")
            continue

        r = subprocess.run(
            ["gh", "issue", "edit", str(num), "--repo", GH_REPO, "--body", new_body],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            print(f"#{num}: {name} - body updated ✓")
            fixed += 1
        else:
            print(f"#{num}: {name} - FAILED: {r.stderr[:200]}")

    print(f"\n✓ Fixed {fixed}/{len(list(ISSUE_RANGE))} issues")


if __name__ == "__main__":
    main()
