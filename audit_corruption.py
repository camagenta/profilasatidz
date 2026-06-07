#!/usr/bin/env python3
"""
audit_corruption.py — file-based corruption audit (bio + pendidikan + others)

Implements:
- Lesson #11: 3 bio corruption patterns (garbage first sentence, wikipedia+name
  mismatch, first sentence about someone else)
- Pendidikan field pollution (URL, social media, bio content, page header,
  search snippet, event description, narrative, non-string)
- Multi-agent safe file partitioning (disjoint sets)
- Per-agent state files (atomic write, resume)
- Quarantine + delete (Lesson #10) with audit trail
- GitHub issue body formatter for ambiguous cases (idempotent label pattern)

PHASE 1 (default, file-based, zero API):
- Static pattern detection
- Result: clean / corrupt / ambiguous / incomplete

PHASE 2 (targeted API, opt-in via --max-api N):
- For ambiguous cases only
- Limit N=3 by default to be polite to Wikipedia
- Use verify_wikipedia_match from wikifetch.py

Run: /usr/bin/python3 audit_corruption.py --detail-dir detail/ --batch 5
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone


AUDIT_LABEL = "profil-asatidz"
AUDIT_PENDING_LABEL = "audit-pending"
AUDIT_RESOLVED_LABEL = "audit-resolved"
REPO = "camagenta/profilasatidz"

# === Pattern definitions (Lesson #11) ===

GARBAGE_FIRST_PATTERNS = [
    re.compile(r"^\s*[Gg]ambar\s+(bawah|atas|di\s+bawah)", re.UNICODE),
    re.compile(r"^\s*[Aa]udio\s+kajian", re.UNICODE),
    re.compile(r"^\s*[Dd]ownload\s+(kajian|mp3|pdf)", re.UNICODE),
    re.compile(r"^\s*[Jj]adwal\s+(kajian|ceramah)\s+\w+", re.UNICODE),
    re.compile(r"^\s*[Bb]eranda\b", re.UNICODE),
    re.compile(r"^\s*[Tt]entang\s+[Kk]ami\b", re.UNICODE),
]

SCHEDULE_ONLY_HEURISTIC = re.compile(
    r"\b(senin|selasa|rabu|kamis|jumat|sabtu|minggu)\b.*\b\d{1,2}[:.]\d{2}\b",
    re.IGNORECASE | re.UNICODE,
)

# === Pendidikan (education) pollution patterns ===

URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
SOCIAL_MEDIA_PATTERN = re.compile(
    r"(facebook\.com|instagram\.com|twitter\.com|youtu\.?be|wa\.me|t\.me|tiktok\.com)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.UNICODE)
PHONE_PATTERN = re.compile(
    r"(?:\+62[\s-]?\d|\(0\d{2,4}\)\s*\d|^0\d{2,4}[\s-]\d{4,}\d|\d{4,}[\s.-]\d{4,}[\s.-]\d{4,})"
)
# Used to disqualify year ranges (1996-1998) from phone matching
YEAR_RANGE_PATTERN = re.compile(r"\b\d{4}\s*[-–—]\s*\d{4}\b")

INSTITUTION_MARKERS = re.compile(
    r"\b("
    r"universitas|university|college|fakultas|faculty|"
    r"madrasah|sekolah|ma'had|mahad|pondok|pesantren|"
    r"lipia|darul|darussalam|al-?azhar|jamiah|"
    r"jakarta|madinah|mekkah|mekah|makkah|"
    r"stai|stis|stkip|ptais|iain|uin|"
    r"diploma|sarjana|s[1-3]|s\.?(1|2|3)|"
    r"lc\.?|ma\.?|mphil|phd|dr\.?|"
    r"alumni|lulusan|studied|graduated|"
    r"kulliyyah|jam'iyyah|mu'assasah|markaz"
    r")\b",
    re.IGNORECASE | re.UNICODE,
)

BIO_PREFIX_MARKERS = re.compile(
    r"^\s*("
    r"ceramah|kajian|audio|video|download|beranda|tentang|home|profil|"
    r"beliau|ia\s+(adalah|merupakan|punya)|ustadz|ustadz|"
    r"sekolah\s+di|ditempuh\s+dalam|menempuh\s+pendidikan|"
    r"tempat\s+(lahir|tanggal)|"
    r"allah|rasulullah|nabi"
    r")",
    re.IGNORECASE | re.UNICODE,
)

PAGE_HEADER_PATTERNS = [
    re.compile(r"^\s*[Tt]entang\s+[Kk]ami\b"),
    re.compile(r"^\s*[Bb]eranda\b"),
    re.compile(r"^\s*[Mm]eniti\s+[Jj]ejak"),
    re.compile(r"^\s*[Hh]ome\b"),
    re.compile(r"^\s*[Pp]rofil\s+[Pp]esantren\b"),
]

SEARCH_SNIPPET_PATTERNS = [
    re.compile(r"^\s*[Dd]ownload\s+(kajian|mp3|pdf|video)", re.IGNORECASE),
    re.compile(r"^\s*[Aa]udio\s+kajian\b", re.IGNORECASE),
    re.compile(r"^\s*[Vv]ideo\s+kajian\b", re.IGNORECASE),
    re.compile(r"^\s*[Kk]umpulan\s+(kajian|ceramah)", re.IGNORECASE),
]

EVENT_DESC_PATTERNS = [
    re.compile(r"\bkajian\s+(intensif|rutin|pekanan|bulanan)\b", re.IGNORECASE),
    re.compile(r"\b(masjid|pondok|pesantren)\s+[A-Z][\w-]+", re.UNICODE),
    re.compile(r"\b(disampaikan|disiarkan)\s+(oleh|pada|di)\b", re.IGNORECASE),
    re.compile(r"\bbekerja\s+sama\s+(dengan|dengan)\b", re.IGNORECASE),
]

# Generic common Arabic name tokens — kept for reference, not used for strict match
# (Lesson #11: too loose, high false positive). Use NFKC name-token match instead.

PENDIDIKAN_MAX_LENGTH = 200


# === Utility ===

def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip()


def name_tokens(name: str) -> set:
    """Lowercased, NFKC-normalized tokens. Empty tokens removed."""
    cleaned = re.sub(r"[^\w\s]", " ", nfkc(name), flags=re.UNICODE)
    return {t.lower() for t in cleaned.split() if t}


def first_sentence(text: str) -> str:
    """First sentence (split on '. ' or '.\n')."""
    if not text:
        return ""
    text = text.strip()
    parts = re.split(r"(?:\. |\.\n|\.$)", text, maxsplit=1, flags=re.UNICODE)
    return parts[0].strip() if parts else ""


def get_wikipedia_url(sources: list) -> str | None:
    """Extract Wikipedia URL from sources[].url."""
    if not isinstance(sources, list):
        return None
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = s.get("url", "")
        if isinstance(url, str) and "wikipedia.org" in url:
            return url
    return None


def is_garbage_first_sentence(first: str) -> bool:
    for p in GARBAGE_FIRST_PATTERNS:
        if p.search(first):
            return True
    # Short first sentence that has a clear schedule pattern = garbage
    if len(first) < 150 and SCHEDULE_ONLY_HEURISTIC.search(first):
        return True
    return False


def name_in_text(name: str, text: str) -> bool:
    """Check if NFKC-normalized name tokens appear in text (case-insensitive)."""
    if not name or not text:
        return False
    n_tokens = name_tokens(name)
    text_nfkc = nfkc(text).lower()
    if not n_tokens:
        return False
    # ALL tokens must appear (whole-word boundary)
    for tok in n_tokens:
        if not re.search(rf"\b{re.escape(tok)}\b", text_nfkc, re.IGNORECASE | re.UNICODE):
            return False
    return True


# === Core: bio audit (Lesson #11) ===

def audit_bio(detail: dict, profile_name: str) -> tuple[str, list[str]]:
    """
    Return (verdict, reasons).
    verdict ∈ {"clean", "corrupt", "ambiguous", "incomplete"}
    """
    bio = detail.get("bio", "")
    if not bio or not isinstance(bio, str) or not bio.strip():
        return "incomplete", ["empty_bio"]

    first = first_sentence(bio)
    reasons = []

    if is_garbage_first_sentence(first):
        return "corrupt", [f"pattern_a_garbage_first_sentence: {first[:80]}"]

    sources = detail.get("sources", [])
    wiki_url = get_wikipedia_url(sources)
    if wiki_url and profile_name:
        # Pattern B: Wikipedia + first sentence doesn't mention own name = ambiguous
        if not name_in_text(profile_name, first):
            reasons.append(
                f"pattern_b_wikipedia_name_mismatch: first sentence lacks '{profile_name}'"
            )
            return "ambiguous", reasons

    # Pattern C (heuristic): first sentence has many first-person third-person
    # references + no own name. Simple check: first sentence doesn't mention
    # the profile_name at all (and not wikipedia-sourced).
    if profile_name and not wiki_url and not name_in_text(profile_name, first):
        # Only flag if first sentence is substantive (>50 chars)
        if len(first) > 50:
            reasons.append(
                f"pattern_c_first_sentence_no_name: {first[:80]}"
            )
            return "ambiguous", reasons

    return "clean", []


# === Core: pendidikan audit (NEW) ===

def _check_pendidikan_entry(entry) -> tuple[bool, str]:
    """Check single entry. Return (is_polluted, reason)."""
    if entry is None:
        return True, "non_string_none"
    if not isinstance(entry, str):
        return True, f"non_string_type:{type(entry).__name__}"
    if not entry.strip():
        return True, "empty_string"

    if URL_PATTERN.search(entry):
        return True, "contains_url"
    if SOCIAL_MEDIA_PATTERN.search(entry):
        return True, "contains_social_media_handle"
    if EMAIL_PATTERN.search(entry):
        return True, "contains_email"
    # Phone check excludes year ranges (1996-1998, 2000-2001, etc.)
    if PHONE_PATTERN.search(entry) and not YEAR_RANGE_PATTERN.search(entry):
        return True, "contains_phone"

    if BIO_PREFIX_MARKERS.search(entry):
        return True, "bio_content_prefix"

    if INSTITUTION_MARKERS.search(entry):
        return False, ""

    if len(entry) > PENDIDIKAN_MAX_LENGTH:
        return True, f"excess_length:{len(entry)}"

    for p in PAGE_HEADER_PATTERNS:
        if p.search(entry):
            return True, "page_header"

    for p in SEARCH_SNIPPET_PATTERNS:
        if p.search(entry):
            return True, "search_snippet"

    for p in EVENT_DESC_PATTERNS:
        if p.search(entry):
            return True, "event_description"

    narrative_signals = re.search(
        r"\b(ditempuh|dilakukan|menempuh|selama|tiga tahun|setelah itu|kemudian)\b",
        entry, re.IGNORECASE | re.UNICODE
    )
    if narrative_signals and len(entry) > 80:
        return True, "narrative_paragraph"

    if len(entry) > 80:
        return True, f"no_institution_marker:{entry[:40]}"

    return False, ""


def audit_pendidikan(edu: list) -> tuple[str, list[str]]:
    """
    Return (verdict, reasons) for the pendidikan list.
    """
    if not isinstance(edu, list):
        return "corrupt", ["pendidikan_not_list"]
    if not edu:
        return "incomplete", ["empty_pendidikan"]

    polluted_reasons = []
    for i, entry in enumerate(edu):
        is_polluted, reason = _check_pendidikan_entry(entry)
        if is_polluted:
            preview = str(entry)[:60] if entry else "<empty>"
            polluted_reasons.append(f"[{i}] {reason}: {preview}")

    if polluted_reasons:
        return "corrupt", polluted_reasons
    return "clean", []


# === Core: other fields (expertise, karya) — same patterns as pendidikan ===

def audit_expertise(field_value) -> tuple[str, list[str]]:
    """Expertise field — same rules as pendidikan."""
    if not isinstance(field_value, list):
        return "incomplete", ["expertise_not_list_or_empty"]
    polluted = []
    for i, entry in enumerate(field_value):
        is_polluted, reason = _check_pendidikan_entry(entry)
        if is_polluted:
            preview = str(entry)[:60] if entry else "<empty>"
            polluted.append(f"[{i}] {reason}: {preview}")
    if polluted:
        return "corrupt", polluted
    if not field_value:
        return "incomplete", ["empty_expertise"]
    return "clean", []


# === Multi-agent partitioning ===

def partition_files(all_files: list, num_agents: int) -> list[list[str]]:
    """Split into N roughly-equal disjoint batches."""
    if num_agents < 1:
        raise ValueError("num_agents must be >= 1")
    if not all_files:
        return [[] for _ in range(num_agents)]

    # Sort for deterministic partitioning (so same input → same partition)
    sorted_files = sorted(all_files)
    batches = [[] for _ in range(num_agents)]
    for i, f in enumerate(sorted_files):
        batches[i % num_agents].append(f)
    return batches


# === State management ===

class AuditState:
    """Per-agent state file. Atomic write via temp file + os.replace."""

    def __init__(self, state_dir: str, agent_id: str):
        self.state_dir = state_dir
        self.agent_id = agent_id
        self.path = os.path.join(state_dir, f"audit_state_agent_{agent_id}.json")
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "agent_id": self.agent_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "audited_files": {},
        }

    def _flush(self):
        os.makedirs(self.state_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def mark_audited(self, slug: str, verdict: str, reasons: list[str]):
        self.data["audited_files"][slug] = {
            "verdict": verdict,
            "reasons": reasons,
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }
        self._flush()

    def get_entry(self, slug: str) -> dict | None:
        return self.data["audited_files"].get(slug)

    def get_unprocessed(self, all_slugs: list[str]) -> list[str]:
        audited = set(self.data["audited_files"].keys())
        return [s for s in all_slugs if s not in audited]

    def summary(self) -> dict:
        audited = self.data["audited_files"]
        return {
            "total": len(audited),
            "clean": sum(1 for v in audited.values() if v["verdict"] == "clean"),
            "corrupt": sum(1 for v in audited.values() if v["verdict"] == "corrupt"),
            "ambiguous": sum(1 for v in audited.values() if v["verdict"] == "ambiguous"),
            "incomplete": sum(1 for v in audited.values() if v["verdict"] == "incomplete"),
        }


def merge_states(state_dir: str, agent_ids: list[str]) -> dict:
    """Merge per-agent states into master. Master is read-only at this layer."""
    master = {
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "agent_ids": agent_ids,
        "audited_files": {},
    }
    for aid in agent_ids:
        path = os.path.join(state_dir, f"audit_state_agent_{aid}.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                agent_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        for slug, entry in agent_data.get("audited_files", {}).items():
            # If same slug audited by multiple agents, keep last write (deterministic
            # ordering from agent_ids list)
            master["audited_files"][slug] = entry
    return master


# === Quarantine (Lesson #10) ===

def quarantine_file(
    detail_path: str,
    quarantine_dir: str,
    reason: str,
    original_slug: str,
) -> str:
    """
    Move corrupt detail file to quarantine with metadata + original content.
    Returns the new path.
    """
    if not os.path.exists(detail_path):
        raise FileNotFoundError(f"detail not found: {detail_path}")

    os.makedirs(quarantine_dir, exist_ok=True)
    with open(detail_path) as f:
        original_content = json.load(f)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dest = os.path.join(quarantine_dir, f"{original_slug}-{today}.json")
    # Avoid overwrite
    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(quarantine_dir, f"{original_slug}-{today}-{counter}.json")
        counter += 1

    wrapped = {
        "_quarantine_metadata": {
            "quarantined_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "original_slug": original_slug,
            "original_path": detail_path,
        },
        "original_content": original_content,
    }
    with open(dest, "w") as f:
        json.dump(wrapped, f, ensure_ascii=False, indent=2)
    os.remove(detail_path)
    return dest


# === GitHub issue body formatter ===

def format_audit_issue_body(
    profile_name: str,
    slug: str,
    verdict: str,
    reasons: list[str],
    detail_path: str,
    sources_summary: str = "",
) -> str:
    """Format the body for an audit-pending issue."""
    reasons_block = "\n".join(f"- {r}" for r in reasons) if reasons else "- (none)"
    return f"""## Audit Pending — {profile_name}

**Slug**: `{slug}`
**Detail file**: `{detail_path}`
**Verdict**: **{verdict.upper()}**

### Detected Issues
{reasons_block}

### Sources
{sources_summary if sources_summary else "_(see detail file)_"}

### Action Required
Manual review. Options:
1. **False positive** → mark issue as `audit-resolved` and re-enrich
2. **True corruption** → re-enrich from a different source
3. **Needs API verification** → run Phase 2 with `--max-api`

### History
<!-- audit_corruption will append future verdicts here -->
"""


def find_existing_audit_issue(slug: str) -> str | None:
    """
    Search GitHub for existing audit-pending issue for this slug.
    Returns issue number or None.
    Note: requires `gh` CLI authenticated.
    """
    import subprocess
    try:
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", REPO,
                "--search", f"[Audit Pending] in:title {slug} in:title label:{AUDIT_PENDING_LABEL} state:open",
                "--json", "number", "--limit", "1",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if data and isinstance(data, list) and data[0].get("number"):
                return str(data[0]["number"])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return None


# === Main audit loop ===

def _get_field(detail: dict, *keys: str) -> list:
    """Return the first matching field among candidate keys, default []."""
    for k in keys:
        if k in detail:
            val = detail[k]
            if isinstance(val, list):
                return val
            return []
    return []


def audit_one(detail_path: str, profile_name: str | None = None) -> dict:
    """
    Audit single detail file. Returns verdict dict with bio + pendidikan.
    """
    try:
        with open(detail_path) as f:
            detail = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"verdict": "error", "reasons": [f"read_error: {e}"], "field": None}

    if not profile_name:
        profile_name = detail.get("name", "")

    bio_verdict, bio_reasons = audit_bio(detail, profile_name)
    edu_list = _get_field(detail, "pendidikan", "education")
    edu_verdict, edu_reasons = audit_pendidikan(edu_list)

    # Aggregate
    if "corrupt" in (bio_verdict, edu_verdict):
        verdict = "corrupt"
    elif "ambiguous" in (bio_verdict, edu_verdict):
        verdict = "ambiguous"
    elif "incomplete" in (bio_verdict, edu_verdict):
        verdict = "incomplete"
    else:
        verdict = "clean"

    all_reasons = []
    if bio_reasons:
        all_reasons.append(f"[bio] {bio_reasons[0]}" if len(bio_reasons) == 1 else f"[bio] {'; '.join(bio_reasons)}")
    if edu_reasons:
        for r in edu_reasons:
            all_reasons.append(f"[pendidikan] {r}")

    return {
        "verdict": verdict,
        "reasons": all_reasons,
        "field": None,
        "bio_verdict": bio_verdict,
        "pendidikan_verdict": edu_verdict,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit corruption in detail files.")
    p.add_argument("--detail-dir", default="detail/", help="Path to detail/ dir")
    p.add_argument("--state-dir", default="osint_archive/", help="Path to state dir")
    p.add_argument("--quarantine-dir", default="osint_archive/quarantine/", help="Path to quarantine")
    p.add_argument("--batch", type=int, default=5, help="Max files to process (file-based)")
    p.add_argument("--max-api", type=int, default=3, help="Max API calls for ambiguous verification")
    p.add_argument("--agents", type=int, default=1, help="Number of parallel agents")
    p.add_argument("--agent-id", default="0", help="This agent's ID (used by multi-agent runner)")
    p.add_argument("--dry-run", action="store_true", help="Don't write state or quarantine")
    p.add_argument("--create-issues", action="store_true", help="Create GH issues for ambiguous")
    return p.parse_args(argv)


def main():
    args = parse_args()

    # Gather all detail files
    detail_files = []
    if os.path.isdir(args.detail_dir):
        for fname in os.listdir(args.detail_dir):
            if fname.endswith(".json"):
                detail_files.append(os.path.join(args.detail_dir, fname))
    detail_files.sort()

    # Partition for this agent (work in slugs to match state keys)
    all_slugs = sorted(
        os.path.splitext(os.path.basename(f))[0] for f in detail_files
    )
    batches = partition_files(all_slugs, args.agents)
    my_slugs = batches[int(args.agent_id)] if args.agent_id.isdigit() and int(args.agent_id) < len(batches) else all_slugs

    slug_to_path = {
        os.path.splitext(os.path.basename(f))[0]: f for f in detail_files
    }

    # State
    state = AuditState(state_dir=args.state_dir, agent_id=args.agent_id)
    unprocessed = state.get_unprocessed(my_slugs)
    todo = unprocessed[:args.batch]

    print(f"[agent={args.agent_id}] files={len(my_slugs)} unprocessed={len(unprocessed)} todo={len(todo)}", file=sys.stderr)

    audited = 0
    for slug in todo:
        path = slug_to_path[slug]
        result = audit_one(path)
        state.mark_audited(slug, result["verdict"], result["reasons"])
        print(f"  {slug}: {result['verdict']} ({'; '.join(result['reasons'][:1])})", file=sys.stderr)
        audited += 1

    print(f"[agent={args.agent_id}] done. audited={audited}", file=sys.stderr)
    print(json.dumps({"agent": args.agent_id, "audited": audited, "summary": state.summary()}))


if __name__ == "__main__":
    main()
