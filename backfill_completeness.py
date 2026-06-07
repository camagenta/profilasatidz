#!/usr/bin/env python3
"""
Backfill completeness field in asatidz_master.json for entries where it is None.
Formula: bio(35) + foto(25) + detail(25) + count>0(15) = max 100
"""
import json
import sys

MASTER_FILE = "asatidz_master.json"


def compute_completeness(entry):
    c = 0
    if entry.get("has_bio"):
        c += 35
    if entry.get("has_foto"):
        c += 25
    hd = entry.get("has_detail")
    if isinstance(hd, bool) and hd:
        c += 25
    elif isinstance(hd, list) and len(hd) > 0:
        c += 25
    if entry.get("count", 0) > 0:
        c += 15
    return c


def main():
    with open(MASTER_FILE) as f:
        master = json.load(f)

    fixed = 0
    for entry in master:
        if entry.get("completeness") is None:
            entry["completeness"] = compute_completeness(entry)
            fixed += 1
            print(f"  + {entry['name']}: completeness={entry['completeness']}%")

    if fixed > 0:
        with open(MASTER_FILE, "w") as f:
            json.dump(master, f, indent=2, ensure_ascii=False)
        print(f"\n✓ Fixed {fixed} entries. Master updated.")
    else:
        print("No entries need fixing.")


if __name__ == "__main__":
    main()
