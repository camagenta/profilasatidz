# Lessons Learned: Duplicate Issues & FE Contribution Flow

> **Dibuat**: 2026-06-07
> **Konteks**: Sesi QA untuk memvalidasi bahwa alamat kontribusi di FE untuk 31 nama duplikat sudah benar.

## TL;DR

Cleanup duplikat 31 issue di repo `camagenta/profilasatidz` berhasil, tapi **QA menemukan 1 profil "Ahmad Sabiq" yang broken**: FE kontribusi tidak akan berfungsi karena search API return issue yang closed.

**Root cause**: `findGitHubIssue()` di `main.go` tidak filter `state:open`, dan cleanup script saya pick keeper berdasarkan created_at tanpa prefer ke issue OPEN.

**Fix**: 3 perubahan (sudah di-commit).

---

## 1. Latar Belakang

### Apa yang terjadi
- 2 guardian run bersamaan (nohup + tmux) membuat 30 issue duplikat + 1 yang sebenarnya salah-pair (#9 dan #37 untuk "Ahmad Sabiq")
- `cleanup_duplicate_issues.py` close 31 duplikat, keep oldest
- Tapi `findGitHubIssue()` di FE tidak filter state, jadi bisa return issue closed

### Dampak
- **30 dari 31 nama duplikat**: Aman. FE akan return 1 OPEN issue (yang kita keep).
- **1 nama (Ahmad Sabiq)**: BROKEN. Kedua issue di-close, FE return best-match closed issue.

## 2. Bug yang Ditemukan

### Bug A: `findGitHubIssue()` tidak filter state
**Lokasi**: `main.go:130`

**Sebelum**:
```go
searchQuery := fmt.Sprintf(`repo:%s "[Profil Asatidz] %s" in:title label:profil-asatidz`, ghRepo, profileName)
apiURL := fmt.Sprintf("https://api.github.com/search/issues?q=%s&per_page=1", url.QueryEscape(searchQuery))
```

**Masalah**:
- Tanpa `state:open`, search return SEMUA issue termasuk closed
- `per_page=1` ambil best-match (default sort by relevance, BUKAN by recency)
- Kalau semua issue untuk nama tersebut closed, FE tetap return issue closed → post comment ke issue closed

**Sesudah**:
```go
searchQuery := fmt.Sprintf(`repo:%s "[Profil Asatidz] %s" in:title label:profil-asatidz state:open`, ghRepo, profileName)
apiURL := fmt.Sprintf("https://api.github.com/search/issues?q=%s&per_page=1&sort=created&order=desc", url.QueryEscape(searchQuery))
```

**Kenapa sort=created&order=desc**: Issue terbaru biasanya punya body paling lengkap (guardian build dari master yang sudah ter-update). Saat duplikat ada, issue terbaru adalah yang paling representatif.

### Bug B: Cleanup script keep wrong issue
**Lokasi**: `cleanup_duplicate_issues.py:sorting logic`

**Sebelum**:
```python
copies.sort(key=lambda x: x["created_at"])
keep = copies[0]  # oldest
```

**Masalah**:
- Sort by oldest, tanpa prefer state
- Kalau oldest closed dan newest open, kita keep closed → FE kontribusi ke issue closed

**Sesudah**:
```python
open_copies = [c for c in copies if c["state"] == "open"]
if open_copies:
    keep = open_copies[0]  # oldest OPEN
else:
    keep = copies[0]  # all closed, just pick oldest (with warning)
    broken_reported.append((name, [c["number"] for c in copies]))
    print(f"  ⚠ WARNING: all {len(copies)} issues for '{name[:50]}' are closed")
```

**Improvement**: Sekarang prefer OPEN state. Kalau semua closed, log warning dan laporkan nama-nama yang perlu manual review.

### Bug C: Bio salah untuk "Ahmad Sabiq"
**Lokasi**: `detail/kajian-ahmad-sabiq.json` (data corruption dari enrichment sebelumnya)

**Penyebab**: Bot enrichment cari Wikipedia untuk "Ahmad Sabiq", URL Wikipedia di-redirect ke "Firanda Andirja" (mungkin Firanda Andirja adalah halaman yang di-redirect untuk Ahmad Sabiq, atau ada ambiguitas). Bot ambil bio Firanda Andirja dan assign ke profil Ahmad Sabiq.

**Fix**:
- Hapus bio + foto dari detail file
- Set `has_bio=False, has_foto=False` di master
- Set `completeness=15%` (hanya count kajian)
- Backup bio salah ke `sources[]` dengan `sitename="QA Fix 2026-06-07"` untuk audit trail
- Reopen issue #9 (body clean, tidak ada Firanda) dan rebuild body
- Close issue #37 (body punya Firanda)

## 3. Verifikasi Akhir

```
Master profiles: 283
Profiles with NO open issue: 0    ← semua punya issue OPEN
Profiles with MULTI open issues: 0 ← tidak ada duplikat OPEN
```

Untuk 31 nama yang sebelumnya duplikat, FE kontribusi sekarang akan:
- 30 nama: return 1 OPEN issue, kontribusi bekerja normal
- 1 nama (Ahmad Sabiq): return #9 (di-reopen, body clean), kontribusi bekerja normal

## 4. Lessons Learned

### Lesson 1: Selalu filter `state:open` di search query FE
Search API GitHub return SEMUA issue (open + closed) secara default. Untuk use case "cari issue untuk kontribusi", HARUS filter `state:open` dan `sort=created&order=desc` agar dapat issue terbaru yang open.

**Kapan apply**: Setiap kali backend mencari issue berdasarkan title prefix.

### Lesson 2: Cleanup script harus smart-pick keeper
Saat close duplikat, **bukan hanya sort by created_at** — prioritaskan state OPEN. Kalau semua closed, **STOP dan laporkan untuk manual review**, jangan auto-close yang penting.

**Anti-pattern**:
```python
copies.sort(key=lambda x: x["created_at"])
keep = copies[0]  # bisa jadi closed!
```

**Best practice**:
```python
open_copies = [c for c in copies if c["state"] == "open"]
keep = open_copies[0] if open_copies else None
if keep is None:
    # Report, don't auto-clean
    broken_reported.append(name)
```

### Lesson 3: Wikipedia redirect adalah silent killer
Saat bot enrichment ambil data dari Wikipedia, **periksa apakah URL di-redirect** atau apakah judul halaman asli berbeda dengan yang dicari. Firanda Andirja ≠ Ahmad Sabiq, tapi URL Wikipedia-nya bisa sama.

**Mitigasi** (belum di-implement, next session):
- Cek `wgArticleId` atau compare canonical title dengan yang dicari
- Verify first sentence mengandung nama profile (fuzzy match)
- Log warning kalau bio tidak sesuai dengan nama profile

### Lesson 4: QA wajib untuk long-running cleanup
Script cleanup yang auto-close 31 issue perlu QA. Saya melakukan QA manual dan menemukan 1 broken case (Ahmad Sabiq). Kalau tidak ada QA, broken case bisa terlewat dan kontribusi user akan hilang diam-diam.

**Checklist QA**:
- [ ] Verifikasi setiap nama punya tepat 1 OPEN issue
- [ ] Sample beberapa issue yang di-close, cek body-nya tidak punya data unik
- [ ] Test FE kontribusi end-to-end untuk 2-3 nama yang di-close
- [ ] Verifikasi keeper issue untuk nama duplikat punya body paling lengkap

### Lesson 5: Backup data yang dihapus
Saat fix bug data corruption (seperti bio Firanda di profile Ahmad Sabiq), **jangan langsung hapus** — backup ke `sources[]` dengan metadata `note` dan `sitename="QA Fix {date}"`. Ini untuk:
- Audit trail (siapa yang hapus, kapan, kenapa)
- Recovery kalau ternyata data itu benar
- Reference untuk issue troubleshooting

### Lesson 6: Tmux untuk SSH long-running
**WAJIB pakai tmux untuk proses > 1 menit di SSH**. SSH biasa timeout 2 menit. Guardian run 3 menit = SSH timeout. Pakai tmux:
```bash
ssh juragan "tmux new-session -d -s guardian -c /home/ubuntu/profilasatidz"
ssh juragan "tmux send-keys -t guardian 'python3 script.py' Enter"
ssh juragan "tmux capture-pane -t guardian -p"  # monitor
ssh juragan "tmux kill-session -t guardian"  # cleanup
```

### Lesson 7: Race condition = duplicate
Jalankan 2 long-running script bersamaan (nohup + tmux) = race condition. Hasil: 30 duplikat. Solusi: **satu metode saja, tunggu sampai selesai** sebelum luncurkan yang lain. Atau pakai `flock` untuk mutual exclusion.

## 5. Tindak Lanjut

### Segera (Done in this session)
- [x] Fix `findGitHubIssue()` dengan `state:open` + `sort=created&order=desc`
- [x] Fix cleanup script prefer OPEN state + warning untuk all-closed
- [x] Fix detail file Ahmad Sabiq (clear wrong bio + foto)
- [x] Update master Ahmad Sabiq (completeness=15%, has_bio=False, has_foto=False)
- [x] Reopen #9, rebuild body, close #37
- [x] Verifikasi 0 broken, 0 multi-open dari 283 master

### Re-enrich (Next session)
- [ ] Re-enrich Ahmad Sabiq dari KajianLive.my.id (id=350) untuk dapat foto + bio yang benar
  - Cek apakah foto URL `350_ustadz_ahmad_sabiq__lc.jpg` valid
  - Cek apakah KajianLive punya bio text (bukan hanya foto)
- [ ] Audit enrichment lain yang mungkin punya bug similar:
  - Cek semua bio di `detail/*.json` apakah relevan dengan nama profile
  - Cross-check dengan master `name` field

### Preventif
- [ ] Tambah Wikipedia redirect detection di `enrich_*.py`
- [ ] Tambah `flock` di `guardian_cron.sh` untuk prevent race condition
- [ ] Cron schedule stagger 1-2 menit antar script untuk avoid overlap

## 6. Test Verification Commands

Untuk verify FE kontribusi bekerja normal:
```bash
# Test search API (simulasi FE findGitHubIssue)
gh api "search/issues?q=repo:camagenta/profilasatidz+%22%5BProfil+Asatidz%5D+Ahmad+Sabiq%22+in:title+label:profil-asatidz+state:open&sort=created&order=desc"
# Should return: #9 state=open

# Test master data
python3 -c "
import json, unicodedata
master = json.load(open('asatidz_master.json'))
for m in master:
    if 'sabiq' in m['name'].lower():
        print(f'{m[\"name\"]}: bio={m[\"has_bio\"]}, foto={m[\"has_foto\"]}, comp={m[\"completeness\"]}%')
"
# Should return: Ahmad Sabiq: bio=False, foto=False, comp=15%

# Test issue body
gh issue view 9 --repo camagenta/profilasatidz --json body | grep "Profil Live"
# Should show: "Belum ada deskripsi biografi"
```

---

**Maintainer note**: Dokumen ini harus di-review setiap kali:
- Ada cleanup script baru yang auto-close issue
- Ada perubahan `findGitHubIssue()` atau endpoint `/api/contribute`
- Ada bug data corruption baru yang ditemukan QA
