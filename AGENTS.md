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
