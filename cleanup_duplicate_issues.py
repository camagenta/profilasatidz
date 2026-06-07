#!/usr/bin/env python3
"""
Close duplicate issues for the same profile name.
Strategy: for each duplicated title, keep the OLDEST issue, close all others as duplicate.
"""
import json
import subprocess
import sys

GH_REPO = "camagenta/profilasatidz"
PREFIX = "[Profil Asatidz] "


def fetch_all_issues():
    """Fetch all [Profil Asatidz] issues using gh issue list."""
    r = subprocess.run(
        ["gh", "issue", "list", "--repo", GH_REPO,
         "--state", "all", "--limit", "500",
         "--json", "number,title,state,createdAt",
         "--search", "[Profil Asatidz] in:title"],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        print(f"Error: {r.stderr[:200]}")
        sys.exit(1)
    data = json.loads(r.stdout)
    return [
        {
            "number": d["number"],
            "state": d["state"].lower(),
            "created_at": d["createdAt"],
            "name": d["title"][len(PREFIX):].strip() if d["title"].startswith(PREFIX) else d["title"],
        }
        for d in data
        if d["title"].startswith(PREFIX)
    ]


def main():
    issues = fetch_all_issues()
    print(f"Fetched {len(issues)} [Profil Asatidiz] issues")

    by_name = {}
    for issue in issues:
        norm = " ".join(issue["name"].split()).lower()
        by_name.setdefault(norm, []).append(issue)

    duplicates = {k: v for k, v in by_name.items() if len(v) > 1}
    print(f"Found {len(duplicates)} names with duplicate issues")

    if not duplicates:
        print("No duplicates to clean up")
        return

    closed = 0
    for name, copies in duplicates.items():
        copies.sort(key=lambda x: x["created_at"])
        keep = copies[0]
        for dup in copies[1:]:
            if dup["state"] == "closed":
                print(f"  - #{dup['number']} already closed, skipping")
                continue
            print(f"  Closing #{dup['number']} (dup of #{keep['number']}, name='{name[:60]}')")
            r = subprocess.run(
                ["gh", "issue", "close", str(dup["number"]),
                 "--repo", GH_REPO,
                 "--comment", f"Closed as duplicate of #{keep['number']}. Detected by Profile Guardian cleanup script."],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                closed += 1
            else:
                print(f"    FAILED: {r.stderr[:100]}")

    print(f"\nClosed {closed} duplicate issues")


if __name__ == "__main__":
    main()
