#!/usr/bin/env python3
"""
Reformat GitHub Issues for the 85 mapped asatidz:
1. Issue Body: contains the Profil Live (bio, education, kary, foto) + Status Profiling.
2. Issue Comments: contains the OSINT enrichment history (KajianLive details and raw extracted bio).
"""
import base64
import json
import subprocess
import time
import sys
from datetime import datetime, timezone, timedelta

CONTAINER = "profilasatidz"
MASTER_FILE = "/root/asatidz_master.json"
DETAIL_DIR = "/root/detail"
JAKARTA_TZ = timezone(timedelta(hours=7))

def log(msg):
    ts = datetime.now(JAKARTA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def docker_exec(cmd):
    """Run command inside container, return (stdout, returncode)"""
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "sh", "-c", cmd],
        capture_output=True, text=True, timeout=120
    )
    return result.stdout.strip(), result.returncode

def get_detail_from_container(profile_id):
    detail_path = f"{DETAIL_DIR}/{profile_id}.json"
    out, rc = docker_exec(f"cat {detail_path} 2>/dev/null")
    if rc == 0 and out.strip():
        try:
            return json.loads(out)
        except:
            return None
    return None

def build_issue_body(profile_name, profile_id, entry, detail):
    slug = entry.get("slug", "")
    count = entry.get("count", 0)
    has_bio = entry.get("has_bio", False)
    has_detail = entry.get("has_detail", False)
    completeness = entry.get("completeness", 0)
    
    # Detail data
    bio = detail.get("bio", "").strip() if detail else ""
    foto = detail.get("foto", "").strip() if detail else ""
    education = detail.get("education", []) if detail else []
    karya = detail.get("kary", []) if detail else []
    social_media = detail.get("social_media", {}) if detail else {}
    sources = detail.get("sources", []) if detail else []
    
    body_lines = [
        f"# {profile_name}",
        f"",
    ]
    
    if foto:
        body_lines.append(f"![Foto {profile_name}]({foto})")
        body_lines.append("")
        
    body_lines.append("## 📝 Profil Live")
    if bio:
        body_lines.append(bio)
    else:
        body_lines.append("*Belum ada deskripsi biografi.*")
    body_lines.append("")
    
    if education:
        body_lines.append("### 🎓 Pendidikan")
        for edu in education:
            body_lines.append(f"- {edu}")
        body_lines.append("")
        
    if karya:
        body_lines.append("### 📚 Karya Tulis / Ilmiah")
        for kar in karya:
            body_lines.append(f"- {kar}")
        body_lines.append("")
        
    if social_media and any(social_media.values()):
        body_lines.append("### 🔗 Media Sosial & Informasi Kontak")
        for k, v in social_media.items():
            if v:
                body_lines.append(f"- **{k.capitalize()}**: {v}")
        body_lines.append("")
        
    body_lines.append("---")
    body_lines.append("## 📊 Status Profiling")
    body_lines.append(f"- **ID**: `{profile_id}`")
    body_lines.append(f"- **Slug**: `{slug}`")
    body_lines.append(f"- **Jumlah Kajian**: {count}")
    body_lines.append(f"- **Bio**: {'✅' if has_bio else '❌'}")
    body_lines.append(f"- **Detail**: {'✅' if has_detail else '❌'}")
    body_lines.append(f"- **Completeness**: {completeness}%")
    
    if sources:
        body_lines.append("- **Sumber OSINT**:")
        for s in sources:
            sitename = s.get("sitename", "Web")
            url = s.get("url", "")
            title = s.get("title", "Link")
            body_lines.append(f"  - [{sitename} - {title}]({url})")
            
    body_lines.append("")
    body_lines.append(f"*Last updated: {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M')} WIB*")
    
    return "\n".join(body_lines)

def build_enrichment_comment(profile_name, detail):
    # This represents the enrichment event log from KajianLive
    bio = detail.get("bio", "").strip() if detail else ""
    education = detail.get("education", []) if detail else []
    karya = detail.get("kary", []) if detail else []
    foto = detail.get("foto", "").strip() if detail else ""
    
    lines = [
        "### 🔄 OSINT Enrichment Log - KajianLive",
        f"*Waktu: {datetime.now(JAKARTA_TZ).strftime('%Y-%m-%d %H:%M:%S')} WIB*",
        "",
        "Berhasil melakukan enrichment data dari **KajianLive.my.id** dengan rincian berikut:",
        f"- **Biografi**: {'✅ Diperbarui/Dimasukkan' if bio else '❌ Tidak ditemukan/Blank'}",
        f"- **Pendidikan**: {len(education)} entri berhasil di-merge/dimasukkan" if education else "- **Pendidikan**: ❌ Tidak ditemukan",
        f"- **Karya Tulis**: {len(karya)} entri berhasil di-merge/dimasukkan" if karya else "- **Karya Tulis**: ❌ Tidak ditemukan",
        f"- **Foto**: {'✅ URL foto diperoleh' if foto else '❌ Foto tidak ditemukan'}",
        ""
    ]
    
    if bio:
        lines.append("**Teks Biografi yang dimasukkan:**")
        lines.append(f"> {bio.replace('\n', '\n> ')}")
        lines.append("")
        
    return "\n".join(lines)

def update_issue_and_comment(profile_id, profile_name, entry, detail):
    title = f"[Profil Asatidz] {profile_name}"
    labels = "profil-asatidz"
    
    # 1. Build body
    body = build_issue_body(profile_name, profile_id, entry, detail)
    
    # 2. Check if issue exists
    result = subprocess.run(
        ["gh", "issue", "list", "--repo", "camagenta/profilasatidz",
         "--search", f'"{title}"', "--state", "all", "--json", "number,title",
         "--limit", "1"],
        capture_output=True, text=True, timeout=15
    )
    
    existing = []
    if result.returncode == 0 and result.stdout.strip():
        try:
            existing = json.loads(result.stdout)
        except:
            pass
            
    issue_num = None
    if existing:
        # Update existing issue body
        issue_num = existing[0]["number"]
        update_result = subprocess.run(
            ["gh", "issue", "edit", str(issue_num), "--repo", "camagenta/profilasatidz",
             "--body", body],
            capture_output=True, text=True, timeout=15
        )
        if update_result.returncode == 0:
            log(f"  ✓ Issue #{issue_num} body reformatted: {profile_name}")
        else:
            log(f"  ✗ Issue reformat failed: {update_result.stderr[:100]}")
    else:
        # Create new issue with this body
        create_result = subprocess.run(
            ["gh", "issue", "create", "--repo", "camagenta/profilasatidz",
             "--title", title, "--body", body, "--label", labels],
            capture_output=True, text=True, timeout=15
        )
        if create_result.returncode == 0:
            # Get the new issue number
            # We assume it created successfully and we output the new URL.
            # Let's search again to find its number
            time.sleep(1.0)
            res2 = subprocess.run(
                ["gh", "issue", "list", "--repo", "camagenta/profilasatidz",
                 "--search", f'"{title}"', "--state", "all", "--json", "number",
                 "--limit", "1"],
                capture_output=True, text=True, timeout=15
            )
            try:
                issue_num = json.loads(res2.stdout)[0]["number"]
                log(f"  ✓ Issue #{issue_num} created: {profile_name}")
            except:
                log(f"  ✓ Issue created but number not resolved: {profile_name}")
        else:
            log(f"  ✗ Issue create failed: {create_result.stderr[:100]}")
            
    # 3. Post enrichment log as comment if issue_num is resolved
    if issue_num:
        # Check if a comment containing "OSINT Enrichment Log - KajianLive" already exists to avoid duplicates
        comments_res = subprocess.run(
            ["gh", "issue", "view", str(issue_num), "--repo", "camagenta/profilasatidz", "--json", "comments"],
            capture_output=True, text=True, timeout=15
        )
        has_comment = False
        if comments_res.returncode == 0 and comments_res.stdout.strip():
            try:
                comments_data = json.loads(comments_res.stdout).get("comments", [])
                has_comment = any("OSINT Enrichment Log - KajianLive" in c.get("body", "") for c in comments_data)
            except:
                pass
                
        if not has_comment:
            comment_body = build_enrichment_comment(profile_name, detail)
            comment_res = subprocess.run(
                ["gh", "issue", "comment", str(issue_num), "--repo", "camagenta/profilasatidz",
                 "--body", comment_body],
                capture_output=True, text=True, timeout=15
            )
            if comment_res.returncode == 0:
                log(f"    ✓ Enrichment comment added to #{issue_num}")
            else:
                log(f"    ✗ Failed to add comment: {comment_res.stderr[:100]}")
        else:
            log(f"    - Enrichment comment already exists on #{issue_num}")

def main():
    log("=== KajianLive Issue Reformatting & Comment Logger ===")
    
    # Load mapping
    with open('kajianlive_mapping.json') as f:
        mapping_data = json.load(f)
        
    targets = [m for m in mapping_data['mapping'] if m['match_score'] >= 1.0]
    log(f"Loaded {len(targets)} mapped targets with score >= 1.0")
    
    # Load master
    master_json, rc = docker_exec(f"cat {MASTER_FILE}")
    if rc != 0:
        log("ERROR: Cannot read master file from container")
        sys.exit(1)
    master = json.loads(master_json)
    master_dict = {m['id']: m for m in master}
    
    total = len(targets)
    for i, t in enumerate(targets):
        profile_id = t['kajian_net']['id']
        name = t['kajian_net']['name']
        
        entry = master_dict.get(profile_id)
        if not entry:
            log(f"[{i+1}/{total}] WARNING: {profile_id} not found in master index")
            continue
            
        detail = get_detail_from_container(profile_id)
        
        log(f"[{i+1}/{total}] Processing {name}...")
        update_issue_and_comment(profile_id, name, entry, detail)
        
        # Small delay to avoid API limits
        time.sleep(2.0)
        
    log("=== All issues reformatted and commented! ===")

if __name__ == "__main__":
    main()
