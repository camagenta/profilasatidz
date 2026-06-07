#!/usr/bin/env python3
"""
Profile Issue Guardian
======================

Memastikan SETIAP profil asatidz di asatidz_master.json memiliki GitHub Issue
di repo camagenta/profilasatidz (label: profil-asatidz).

Tujuan:
- Kontributor selalu menemukan issue untuk profil yang ingin dikoreksi
- Profil baru otomatis ter-ekspos ke komunitas
- Status OSINT (jumlah kajian di kajian.net, info awal dari kajianlive.my.id)
  tercatat di body issue

Cara kerja:
1. Load asatidz_master.json (dari container atau local)
2. Query semua issue OPEN berlabel profil-asatidz dari GitHub
3. Bandingkan: profil mana yang BELUM punya issue?
4. Untuk profil yang belum punya issue:
   a. Ambil data dari detail/{id}.json jika ada (bio, foto, dll)
   b. Coba lookup kajianlive.my.id info awal (slug, expertise) dari mapping
   c. Buat issue baru dengan body yang menjelaskan status OSINT-nya
   d. Kirim notifikasi Telegram via Hermes
5. Simpan log ke osint_archive/guardian-{date}.log
6. Return exit code 0 jika semua OK, 1 jika ada error

Jadwal:
- Cron harian (recommended 02:00 WIB)
- Atau trigger manual: python3 profile_issue_guardian.py [--dry-run]
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

# --- Config ---
CONTAINER = "profilasatidz"
MASTER_FILE = "/root/asatidz_master.json"
DETAIL_DIR = "/root/detail"
ARCHIVE_DIR = "osint_archive"
GH_REPO = "camagenta/profilasatidz"
GH_LABEL = "profil-asatidz"
HERMES_CMD = "/home/ubuntu/.hermes/hermes-agent/venv/bin/python"
HERMES_ARGS = ["-m", "hermes_cli.main", "send", "--to", "telegram"]
JAKARTA_TZ = timezone(timedelta(hours=7))


def log(msg, level="INFO"):
    ts = datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def docker_exec(cmd, timeout=120):
    """Run command inside container, return (stdout, returncode)"""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip(), result.returncode


def docker_exec_or_local(cmd, local_fallback_path, timeout=120):
    """Run command in container, fall back to local file if container unavailable."""
    out, rc = docker_exec(cmd, timeout=timeout)
    if rc == 0 and out.strip():
        return out
    if os.path.exists(local_fallback_path):
        with open(local_fallback_path) as f:
            return f.read()
    return None


def load_master():
    """Load asatidz_master.json from container, fallback to local."""
    raw = docker_exec_or_local(f"cat {MASTER_FILE}", "asatidz_master.json")
    if not raw:
        log("ERROR: Cannot read master file from container nor local", "ERROR")
        sys.exit(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log(f"ERROR: Invalid JSON in master: {e}", "ERROR")
        sys.exit(1)


def load_detail(profile_id):
    """Load detail/{profile_id}.json from container, fallback to local."""
    raw = docker_exec_or_local(
        f"cat {DETAIL_DIR}/{profile_id}.json 2>/dev/null",
        f"detail/{profile_id}.json",
        timeout=15
    )
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def load_kajianlive_mapping():
    """Load kajianlive_mapping.json (local)."""
    if not os.path.exists("kajianlive_mapping.json"):
        return {}
    try:
        with open("kajianlive_mapping.json") as f:
            data = json.load(f)
        # Build kajian_net_id -> kajianlive info
        result = {}
        for m in data.get("mapping", []):
            kn = m.get("kajian_net", {})
            kl = m.get("kajianlive", {})
            if kn.get("id") and kl.get("id") and m.get("match_score", 0) >= 1.0:
                result[kn["id"]] = {
                    "kajianlive_id": kl["id"],
                    "kajianlive_url": kl.get("url", ""),
                    "kajianlive_name": kl.get("name", ""),
                    "match_score": m.get("match_score", 0),
                }
        return result
    except (json.JSONDecodeError, KeyError) as e:
        log(f"WARN: Cannot parse kajianlive_mapping.json: {e}", "WARN")
        return {}


def fetch_existing_issues():
    """
    Fetch ALL issues (open + closed) matching '[Profil Asatidz] {name}' title pattern.
    Strategy:
      1. Search by label (profil-asatidz) via search API
      2. Search by title prefix '[Profil Asatidz]' in:title (catches mislabeled ones)
    Returns dict: {profile_name_lowercase: {number, state, title}}
    """
    name_to_issue = {}

    queries = [
        f"repo:{GH_REPO} label:{GH_LABEL}",
        f"repo:{GH_REPO} [Profil Asatidz] in:title",
    ]

    for search_query in queries:
        page = 1
        while page <= 10:  # max 1000 results per query
            api_path = f"search/issues?q={urllib.parse.quote(search_query)}&per_page=100&page={page}"
            result = subprocess.run(
                ["gh", "api", api_path],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                log(f"WARN: search API page {page} failed for '{search_query[:50]}...': {result.stderr[:100]}", "WARN")
                break

            try:
                data = json.loads(result.stdout)
                items = data.get("items", [])
                if not items:
                    break
                for issue in items:
                    title = issue.get("title", "")
                    prefix = f"[Profil Asatidz] "
                    if title.startswith(prefix):
                        name = title[len(prefix):].strip()
                        # Dedupe: keep first seen (open > closed doesn't matter for our purpose)
                        if name.lower() not in name_to_issue:
                            name_to_issue[name.lower()] = {
                                "number": issue["number"],
                                "state": issue["state"],
                                "title": title,
                            }
                if len(items) < 100:
                    break
                page += 1
            except json.JSONDecodeError:
                break

    log(f"Found {len(name_to_issue)} existing issues matching '[Profil Asatidz]' pattern (any state, any label)")

    # Normalize: collapse "Abu Salma Muhammad" vs "Abu Salma muhammad" to one entry
    # (case-insensitive comparison is already done, but trim/collapse whitespace)
    normalized = {}
    for key, val in name_to_issue.items():
        norm_key = " ".join(key.split())
        if norm_key not in normalized:
            normalized[norm_key] = val
    log(f"After whitespace normalization: {len(normalized)} unique issues")
    return normalized


def build_issue_body(profile_name, profile_id, entry, detail, kajianlive_info):
    """
    Build the issue body with Profil Live (if available) + Status Profiling.
    """
    slug = entry.get("slug", profile_id.replace("kajian-", ""))
    count = entry.get("count", 0)
    has_bio = entry.get("has_bio", False)
    has_foto = entry.get("has_foto", False)
    has_detail = entry.get("has_detail", False)
    completeness = entry.get("completeness", 0)

    # Detail data (may be None)
    bio = (detail.get("bio", "") or "").strip() if detail else ""
    foto = (detail.get("foto", "") or "").strip() if detail else ""
    education = detail.get("education", []) if detail else []
    karya = detail.get("kary", []) if detail else []
    social_media = detail.get("social_media", {}) if detail else []
    expertise = detail.get("expertise", []) if detail else []

    lines = [f"# {profile_name}", ""]

    # Foto
    if foto:
        lines.append(f"![Foto {profile_name}]({foto})")
        lines.append("")

    # Profil Live
    lines.append("## 📝 Profil Live")
    if bio:
        lines.append(bio)
    else:
        lines.append("*Belum ada deskripsi biografi. Kontribusi dari Anda akan sangat membantu!*")
    lines.append("")

    if education:
        lines.append("### 🎓 Pendidikan")
        for edu in education:
            lines.append(f"- {edu}")
        lines.append("")

    if karya:
        lines.append("### 📚 Karya Tulis / Ilmiah")
        for kar in karya:
            lines.append(f"- {kar}")
        lines.append("")

    if social_media and any(social_media.values()):
        lines.append("### 🔗 Media Sosial & Informasi Kontak")
        for k, v in social_media.items():
            if v:
                lines.append(f"- **{k.capitalize()}**: {v}")
        lines.append("")

    if expertise:
        lines.append("### 🎯 Topik Keahlian")
        lines.append(", ".join(expertise))
        lines.append("")

    # Info awal dari KajianLive (jika ada mapping)
    if kajianlive_info:
        lines.append("## 🔍 Info Awal dari KajianLive.my.id")
        lines.append(f"- **Slug KajianLive**: `{kajianlive_info.get('kajianlive_id', '')}`")
        lines.append(f"- **URL**: {kajianlive_info.get('kajianlive_url', '')}")
        lines.append(f"- **Nama di KajianLive**: {kajianlive_info.get('kajianlive_name', '')}")
        lines.append(f"- **Match Score**: {kajianlive_info.get('match_score', 0):.2f}")
        lines.append("")

    # Status Profiling
    lines.append("---")
    lines.append("## 📊 Status Profiling")
    lines.append(f"- **ID**: `{profile_id}`")
    lines.append(f"- **Slug**: `{slug}`")
    lines.append(f"- **Jumlah Kajian (kajian.net)**: {count}")
    lines.append(f"- **Bio**: {'✅' if has_bio else '❌'}")
    lines.append(f"- **Foto**: {'✅' if has_foto else '❌'}")
    lines.append(f"- **Detail**: {'✅' if has_detail else '❌'}")
    lines.append(f"- **Completeness**: {completeness}%")

    # Sumber referensi
    sources = []
    if detail and detail.get("sources"):
        sources = detail["sources"]
    if bio:
        sources.append({
            "sitename": "Kajian.net",
            "url": f"https://kajian.net/ustadz/{slug}",
            "title": f"Profil {profile_name} di Kajian.net"
        })
    if kajianlive_info:
        sources.append({
            "sitename": "KajianLive.my.id",
            "url": kajianlive_info.get("kajianlive_url", ""),
            "title": f"Profil {profile_name} di KajianLive.my.id"
        })

    if sources:
        lines.append("- **Sumber Referensi**:")
        for s in sources:
            sitename = s.get("sitename", "Web")
            url = s.get("url", "")
            title = s.get("title", "Link")
            if url:
                lines.append(f"  - [{sitename} - {title}]({url})")
            else:
                lines.append(f"  - {sitename} - {title}")

    lines.append("")
    lines.append("## 🤝 Cara Berkontribusi")
    lines.append("Klik **'Kontribusi'** di halaman profil untuk menambahkan:")
    lines.append("- Koreksi biografi")
    lines.append("- Riwayat pendidikan")
    lines.append("- Karya tulis / ilmiah")
    lines.append("- Media sosial & kontak")
    lines.append("- Foto dengan kualitas lebih baik")
    lines.append("- Topik keahlian")
    lines.append("")
    lines.append(f"*Issue ini dibuat otomatis oleh Profile Issue Guardian pada {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*")
    return "\n".join(lines)


def create_issue(profile_name, body, dry_run=False):
    """
    Create new GitHub issue for the profile.
    Returns (success, issue_number, issue_url)
    """
    title = f"[Profil Asatidz] {profile_name}"
    if dry_run:
        log(f"  [DRY-RUN] Would create issue: {title}")
        return True, None, None

    result = subprocess.run(
        ["gh", "issue", "create", "--repo", GH_REPO,
         "--title", title,
         "--body", body,
         "--label", GH_LABEL],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        log(f"  ✗ Issue create failed: {result.stderr[:200]}", "ERROR")
        return False, None, None

    # Extract issue URL from stdout (gh prints the URL)
    issue_url = result.stdout.strip()
    issue_number = None
    if "/issues/" in issue_url:
        try:
            issue_number = int(issue_url.rstrip("/").split("/")[-1])
        except ValueError:
            pass
    log(f"  ✓ Issue created: {title} (#{issue_number})")
    return True, issue_number, issue_url


def send_telegram_notification(profile_name, profile_id, issue_url, count, dry_run=False):
    """
    Send Telegram notification via Hermes.
    """
    msg = (
        f"🛡️ *Profile Issue Guardian*\n\n"
        f"Issue baru dibuat otomatis untuk profil yang belum ter-ekspos:\n\n"
        f"👤 *Profil:* {profile_name}\n"
        f"🆔 *ID:* `{profile_id}`\n"
        f"📊 *Jumlah Kajian:* {count}\n\n"
        f"🔗 {issue_url}"
    )
    if dry_run:
        log(f"  [DRY-RUN] Would send Telegram:\n{msg}")
        return True

    if not os.path.exists(HERMES_CMD):
        log(f"  ⚠ Hermes not found at {HERMES_CMD}, skipping notification", "WARN")
        return False

    cmd = [HERMES_CMD, *HERMES_ARGS, msg]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        log(f"  ✓ Telegram notification sent")
        return True
    else:
        log(f"  ⚠ Telegram notification failed: {result.stderr[:200]}", "WARN")
        return False


def save_log(missing_profiles, created_issues, dry_run=False):
    """Save run log to osint_archive/guardian-{date}.log"""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    date_str = datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d")
    log_path = os.path.join(ARCHIVE_DIR, f"guardian-{date_str}.log")

    lines = [
        f"# Profile Issue Guardian Run",
        f"Date: {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M:%S')} WIB",
        f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}",
        f"Missing profiles found: {len(missing_profiles)}",
        f"Issues created: {len(created_issues)}",
        "",
    ]
    for p in missing_profiles:
        lines.append(f"- MISSING: {p['name']} ({p['id']}) - kajian_count={p['count']}, completeness={p['completeness']}%")
    for c in created_issues:
        lines.append(f"- CREATED: {c['name']} -> {c['issue_url']}")
    lines.append("")

    with open(log_path, "a") as f:
        f.write("\n".join(lines))

    log(f"Log saved to {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Profile Issue Guardian")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without creating issues")
    parser.add_argument("--notify", action="store_true", help="Send Telegram notification for each created issue")
    args = parser.parse_args()

    log("=" * 60)
    log("🛡️  PROFILE ISSUE GUARDIAN")
    log("=" * 60)
    if args.dry_run:
        log("⚠️  DRY-RUN MODE: No issues will be created", "WARN")

    # 1. Load master data
    log("Loading asatidz_master.json...")
    master = load_master()
    log(f"Loaded {len(master)} master entries")

    # 2. Load kajianlive mapping
    log("Loading kajianlive mapping...")
    kajianlive_map = load_kajianlive_mapping()
    log(f"Loaded {len(kajianlive_map)} kajianlive mappings")

    # 3. Fetch existing issues
    log(f"Fetching existing issues from {GH_REPO}...")
    existing = fetch_existing_issues()

    # 4. Find missing profiles
    missing = []
    for entry in master:
        name = entry.get("name", "").strip()
        if not name:
            continue
        if name.lower() not in existing:
            missing.append(entry)

    log(f"Found {len(missing)} profiles without GitHub issue")
    if not missing:
        log("✓ All profiles have issues. Nothing to do.")
        return 0

    # 5. Print sample of missing
    log("Sample of missing profiles (max 10):")
    for entry in missing[:10]:
        log(f"  - {entry.get('name', '?')} (id={entry.get('id', '?')}, count={entry.get('count', 0)})")

    if args.dry_run:
        log(f"[DRY-RUN] Would create {len(missing)} issues")
        return 0

    # 6. Create issues one by one
    created = []
    failed = []
    for i, entry in enumerate(missing):
        name = entry.get("name", "").strip()
        profile_id = entry.get("id", "")
        count = entry.get("count", 0)
        log(f"[{i+1}/{len(missing)}] Processing: {name}")

        # Load detail
        detail = load_detail(profile_id)
        kajianlive_info = kajianlive_map.get(profile_id)

        # Build body
        body = build_issue_body(name, profile_id, entry, detail, kajianlive_info)

        # Create issue
        success, issue_num, issue_url = create_issue(name, body, dry_run=args.dry_run)
        if success and issue_url:
            created.append({
                "name": name,
                "id": profile_id,
                "issue_url": issue_url,
                "issue_number": issue_num,
                "count": count,
            })
            # Send notification
            if args.notify:
                send_telegram_notification(name, profile_id, issue_url, count, dry_run=args.dry_run)
        else:
            failed.append({"name": name, "id": profile_id})

        # Rate limit: 3s between creations (be polite to GitHub)
        if i < len(missing) - 1:
            time.sleep(3.0)

    # 7. Save log
    save_log(missing, created, dry_run=args.dry_run)

    # 8. Summary
    log("=" * 60)
    log(f"✓ Created {len(created)} issues")
    if failed:
        log(f"✗ Failed: {len(failed)}")
        for f in failed:
            log(f"  - {f['name']} ({f['id']})")
    log("=" * 60)

    # 9. Send summary notification
    if created and not args.dry_run:
        summary_msg = (
            f"🛡️ *Profile Issue Guardian - Summary*\n\n"
            f"📊 *Scan Result:*\n"
            f"  • Total profiles: {len(master)}\n"
            f"  • Missing issues: {len(missing)}\n"
            f"  • Created: {len(created)}\n"
            f"  • Failed: {len(failed)}\n"
        )
        if created[:5]:
            summary_msg += f"\n📝 *Recent:*\n"
            for c in created[:5]:
                summary_msg += f"  • {c['name']}\n"
        if os.path.exists(HERMES_CMD):
            subprocess.run(
                [HERMES_CMD, *HERMES_ARGS, summary_msg],
                capture_output=True, text=True, timeout=30
            )

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
