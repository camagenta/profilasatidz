# AGENTS.md — Rules for AI Agents Working on `profilasatidz`

## Wajib Dibaca Saat Memulai Sesi Baru

Sebelum mengerjakan apa pun, agent **WAJIB**:

1. **Membaca handoff terbaru** di `docs/handoff-*.md` (ambil file dengan timestamp paling akhir). Handoff berisi:
   - **Goal**: tujuan sesi
   - **Constraints & Preferences**: aturan scraping, commit style, format Issue, dll
   - **Progress (Done / In Progress / Blocked)**: status pekerjaan terakhir
   - **Key Decisions**: keputusan teknis yang sudah diambil
   - **Next Steps**: rencana langkah selanjutnya
   - **Critical Context**: ID container, struktur data, repo info, dll
   - **Relevant Files**: path file yang relevan

2. **Mengecek `git status` dan `git log --oneline -10`** untuk melihat perubahan lokal dan commit terakhir.

3. **Melanjutkan dari `Next Steps`** di handoff, bukan dari awal.

## Wajib Dilakukan Sebelum Sesi Berakhir (Handoff)

Sebelum agent mengakhiri sesi (baik karena user selesai, maupun karena batas waktu sesi), agent **WAJIB**:

1. **Membuat handoff baru** di `docs/handoff-{ISO8601-timestamp}.md` dengan struktur persis seperti di bawah ini.
2. **Update `AGENTS.md`** jika ada aturan/metode baru yang dipelajari selama sesi.
3. **Commit & push** ke `main`:
   ```bash
   git add docs/ AGENTS.md
   git commit -m "docs(handoff): session handoff for {date}"
   git push origin main
   ```

### Format Handoff (`docs/handoff-{timestamp}.md`)

```markdown
# Handoff — {ISO8601 timestamp} ({short session description})

## Goal
- (1-2 kalimat tujuan sesi)

## Constraints & Preferences
- (aturan teknis, preferensi, threshold, dll)

## Progress
### Done
- (poin-poin yang sudah selesai)

### In Progress
- (poin yang sedang berjalan)

### Blocked
- (poin yang terblokir + alasannya)

## Key Decisions
- (keputusan teknis yang sudah final dan alasannya)

## Next Steps
- (langkah yang harus dilakukan agent berikutnya)

## Critical Context
- (informasi teknis yang penting: container, path, ID, formula, encoding fix, dll)

## Relevant Files
- (path file yang relevan dengan sesi ini)
```

Timestamp menggunakan format `YYYY-MM-DDTHH-MM-SSZ` (contoh: `2026-06-05T14-45-19Z`).

## Aturan Teknis Proyek `profilasatidz`

### OSINT Scraping
- **Polite scraping**: random delay 2.0–5.0 detik antar request
- **Batch processing**: 10 ustadz per batch
- **Encoding fix**: gunakan `bytes.decode('utf-8', errors='replace')` untuk halaman dengan Windows-1252 characters
- **Match threshold**: `match_score >= 1.0` untuk fuzzy matching nama (SequenceMatcher + normalisasi gelar)
- **Jadwal filter**: jangan discard bio hanya karena ada substring `"ceramah"` (juga match `"penceramah"`) atau `"kajian rutin"`. Pakai heuristic: length < 150 char + ada jadwal, atau 3+ hari + format waktu

### Parser HTML
- KajianLive punya nested tags (`<h3>` di dalam `<p>`). Gunakan `card_text.find_all(recursive=False)` lalu proses nested children secara manual
- Selalu cek raw text nodes (`NavigableString`) sebelum descend ke children

### Git Commit Style
- `feat(osint): ...` untuk fitur baru
- `fix(osint): ...` untuk bug fix
- `docs(handoff): ...` untuk handoff/AGENTS.md
- `chore: ...` untuk maintenance
- **Jangan commit `__pycache__/`** (cek `.gitignore`)

### GitHub Issue Documentation (per asatidz)
- **Body**: Profil Live (foto, bio, pendidikan, karya, social media) + Status Profiling (ID, slug, count, field status, completeness %, source links)
- **Comments**: Log histori enrichment per-sumber (tanggal, field yang berubah, versi raw bio)
- **Title format**: `[Profil Asatidz] {profile_name}`
- **Label**: `profil-asatidz`
- **Repo**: `camagenta/profilasatidz`

### Docker
- Container `profilasatidz` (port 8080)
- Volume mount: `./asatidz.json`, `./asatidz_enriched.json`, `./asatidz_master.json`, `./detail/` → `/root/*`
- Rebuild & restart: `docker compose down && docker compose up -d --build`
- Dockerfile: `golang:1.24-alpine` + `alpine:latest`

## Lessons Learned (jangan diulang!)

1. **Jangan pakai substring match naif** untuk filter "bio vs jadwal". Selalu pakai heuristic berbasis panjang + pola.
2. **Selalu handle nested HTML** saat parse bio KajianLive. Parser BeautifulSoup naif akan skip isi `<h3>` di dalam `<p>`.
3. **Encoding bukan selalu UTF-8**. Selalu pakai `errors='replace'` saat decode HTML response.
4. **Match score untuk nama Arab butuh threshold lebih tinggi** (>= 1.0 bukan 0.8) untuk menghindari false positive.
5. **Docker bind mount tidak support `os.Rename`** — file yang di-mount ke container tidak bisa di-rename. Selalu fallback ke `os.WriteFile` langsung.
6. **Admin panel path hardcoded** — route path (e.g. `/dapur/`) masih hardcoded di `main.go`. Untuk path dinamis perlu refactor ke konfigurasi/env var.
7. **NFKC unicode normalization** untuk nama Arabic/multilingual — combining chars (`الشيخ محمد موسى آل نصرSyaikh...`) harus di-normalize dengan `unicodedata.normalize('NFKC', ...)` agar dianggap nama yang sama saat search/compare.
8. **`findGitHubIssue` WAJIB filter `state:open` + `sort=created&order=desc`** — kalau tidak, FE kontribusi bisa post ke closed issue, dan saat duplikat, return issue terlama (bukan terbaru dengan body paling lengkap). Pattern: `repo:{ghRepo} "[Profil Asatidz] {name}" in:title label:profil-asatidz state:open&sort=created&order=desc`.
9. **Cleanup duplikat harus prefer OPEN state keeper** — bukan hanya sort by `created_at`. Kalau oldest closed dan newest open, kita keep closed → FE kontribusi ke issue closed. Kalau semua closed, log WARNING + laporkan untuk manual review, jangan auto-clean.
10. **Audit trail convention** saat clear data corruption — push ke `sources[]` dengan `id="qa_audit_<reason>"`, `sitename="QA Audit <date>"`, dan `note` yang menjelaskan first sentence yang salah. JANGAN hapus langsung tanpa backup.
11. **Bio corruption detection (3 patterns)** — saat audit bio, flag jika: (a) first sentence adalah garbage pattern ("Gambar bawah" image caption KajianLive, search snippet, jadwal kajian), (b) Wikipedia source + own name not in first sentence, (c) first sentence tentang orang lain (substantive text). Token-based matching untuk common Arabic name ("abdul", "ahmad", "islam") terlalu loose — banyak false positive.
12. **Race condition = duplicate issue** — jalankan 2 long-running script bersamaan (nohup + tmux) = 30+ duplicate. Solusi: satu metode saja, tunggu sampai selesai. Atau pakai `flock` untuk mutual exclusion.
13. **Python env catatan untuk host local** — `/opt/homebrew/bin/python3` = Python 3.14 dengan expat symbol broken (bs4, lxml tidak bisa install). Untuk HTML parsing di host, SELALU pakai `/usr/bin/python3` (system Python) yang punya bs4 built-in. Server tetap `/usr/bin/python3`.
14. **Wikipedia enrichment bisa return wrong page** — generic names (e.g., "Muhammad", "Ahmad", "Islam") ketika di-enrich via Wikipedia search akan return halaman Nabi Muhammad atau tokoh terkenal, bukan ustadz yang dimaksud. Contoh: `detail/kajian-muhammad-zaki.json` (untracked di server) punya bio Nabi Muhammad ﷺ lengkap dengan `source_url: https://id.wikipedia.org/wiki/Muhammad`. **Detection**: cek first sentence bio apakah match dengan search query (NFKC-normalized). **Prevention**: enrich script harus verify name match di title atau first paragraph sebelum save file.
15. **Audit itu point-in-time, bukan continuous** — sesi audit sebelumnya (commit e9ab753) sudah clear 84 corrupt bio dari 144 audited, tapi session berikutnya bisa create corruption baru (terbukti: `detail/kajian-muhammad-zaki.json` corrupt di server, untracked, post-audit). **Re-audit cadence**: kalau ada nyicil_review run yang menambah file baru, audit ulang batch tersebut. Better: integrate corruption check di dalam enrich script itu sendiri (fail fast sebelum write file).
16. **Continuous audit via scheduled cron (file-based, 0 API)** — `audit_corruption.py` + `audit_cron.sh` runs daily jam 02:00 WIB. Cron entry: `0 2 * * * TZ=Asia/Jakarta /home/ubuntu/profilasatidz/audit_cron.sh`. Pattern: flock mutual exclusion + random delay 0-15m + per-agent state file (atomic write via os.replace) + non-destructive (state only, no auto-quarantine). Conservative approach: zero API calls by default, only file-based pattern detection. **Field name convention**: detail files use `education` (English) and `kary` (not `pendidikan`/`karya`). Audit uses `_get_field(detail, "pendidikan", "education")` for forward-compat. **Phone regex pitfall**: year ranges like "1996-1998" match `\d[\d\s().-]{7,}` — fix with explicit format requirement (`+62`, `(0xxx)`, or `0xx-xxxx-xxxx`). **Corruption scope baseline**: 144 local files = 6 clean + 44 corrupt + 13 ambiguous + 81 incomplete.
17. **Wikipedia wrong page = CORRUPT, not ambiguous** — Kasus 08 Jun 2026: Habib Salim Muhdor di-enrich dengan bio Syekh Abubakar bin Salim, Abu Usamah di-enrich dengan bio Abu Bakar ash-Shiddiq. Keduanya Wikipedia wrong page. Audit script menangkap sebagai pattern_b (ambiguous), tapi seharusnya CORRUPT karena: (a) Wikipedia title tidak match dengan nama profil, (b) first sentence tidak mengandung nama profil sama sekali. Prevention: enrich script harus verify Wikipedia page title match dengan nama profil sebelum accept. Minimal: cek apakah nama profil muncul di page title atau first paragraph. Jika tidak match, skip dan log warning.
