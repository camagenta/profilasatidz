#!/usr/bin/env python3
"""
Test suite for audit_corruption.py — file-based corruption audit + pendidikan
field audit + multi-agent safe partitioning + GitHub issue tracking.

Lesson #11 patterns: garbage first sentence, Wikipedia+name mismatch,
first sentence about someone else.
Lesson #15: continuous audit via scheduled cron.
New: pendidikan (education) field pollution detection.

Run with: /usr/bin/python3 test_audit_corruption.py
"""
import sys
import os
import json
import tempfile
import unittest
import shutil
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestAuditBio(unittest.TestCase):
    """Lesson #11 bio corruption pattern detection."""

    def setUp(self):
        from audit_corruption import audit_bio
        self.audit_bio = audit_bio

    def test_clean_bio_passes(self):
        detail = {
            "name": "Abdul Hakim Amir Abdat",
            "bio": "Abdul Hakim Amir Abdat adalah seorang ulama hadits Indonesia yang lahir di Kertasemaya, Indramayu.",
            "sources": [
                {"url": "https://id.wikipedia.org/wiki/Abdul_Hakim_bin_Amir_Abdat"}
            ],
        }
        verdict, reasons = self.audit_bio(detail, "Abdul Hakim Amir Abdat")
        self.assertEqual(verdict, "clean")
        self.assertEqual(reasons, [])

    def test_pattern_a_garbage_first_sentence_detected(self):
        detail = {
            "name": "Some Ustadz",
            "bio": "Gambar bawah adalah ustadz X. Beliau menyampaikan ceramah tentang pentingnya menuntut ilmu.",
            "sources": [],
        }
        verdict, _ = self.audit_bio(detail, "Some Ustadz")
        self.assertEqual(verdict, "corrupt")

    def test_pattern_a_short_first_sentence_with_schedule_detected(self):
        detail = {
            "name": "Some Ustadz",
            "bio": "Jadwal kajian Senin 19:00, Selasa 19:00, Rabu 19:00, Kamis 19:00. Lebih lengkap bisa follow Instagram kami.",
            "sources": [],
        }
        verdict, _ = self.audit_bio(detail, "Some Ustadz")
        self.assertEqual(verdict, "corrupt")

    def test_pattern_b_wikipedia_name_mismatch_marks_ambiguous(self):
        detail = {
            "name": "Muhammad Zaki",
            "bio": "Muhammad (bahasa Arab: مُحَمَّد) adalah pemimpin agama, sosial, dan politik beretnis Arab sekaligus pendiri agama Islam.",
            "sources": [
                {"url": "https://id.wikipedia.org/wiki/Muhammad"}
            ],
        }
        verdict, reasons = self.audit_bio(detail, "Muhammad Zaki")
        self.assertEqual(verdict, "ambiguous")
        self.assertTrue(any("wikipedia" in r.lower() or "name" in r.lower() for r in reasons))

    def test_pattern_b_wikipedia_with_matching_name_passes(self):
        detail = {
            "name": "Muhammad Zaki",
            "bio": "Muhammad Zaki adalah seorang ustadz Indonesia yang aktif di bidang dakwah.",
            "sources": [
                {"url": "https://id.wikipedia.org/wiki/Muhammad_Zaki"}
            ],
        }
        verdict, _ = self.audit_bio(detail, "Muhammad Zaki")
        self.assertEqual(verdict, "clean")

    def test_no_wikipedia_source_means_no_pattern_b(self):
        detail = {
            "name": "Some Ustadz",
            "bio": "Some Ustadz adalah seorang ulama dari Indonesia.",
            "sources": [
                {"url": "https://kajian.net/ustadz/some"}
            ],
        }
        verdict, _ = self.audit_bio(detail, "Some Ustadz")
        self.assertEqual(verdict, "clean")

    def test_empty_bio_is_not_corrupt_just_incomplete(self):
        detail = {
            "name": "Some Ustadz",
            "bio": "",
            "sources": [],
        }
        verdict, _ = self.audit_bio(detail, "Some Ustadz")
        self.assertEqual(verdict, "incomplete")

    def test_nfkc_normalization_in_name_matching(self):
        detail = {
            "name": "Muhammad Zaki",
            "bio": "MUHAMMAD ZAKI adalah ustadz dari Indonesia.",
            "sources": [
                {"url": "https://id.wikipedia.org/wiki/MUHAMMAD_ZAKI"}
            ],
        }
        verdict, _ = self.audit_bio(detail, "Muhammad Zaki")
        self.assertEqual(verdict, "clean")


class TestAuditPendidikan(unittest.TestCase):
    """Pendidikan (education) field pollution detection."""

    def setUp(self):
        from audit_corruption import audit_pendidikan
        self.audit_pendidikan = audit_pendidikan

    def test_clean_education_passes(self):
        edu = [
            "LIPIA (Lembaga Ilmu Pengetahuan Islam dan Arab)",
            "S1 - Fakultas Syariah, Universitas Islam Madinah",
            "S2 - Jurusan Aqidah, Universitas Islam Madinah",
        ]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "clean")
        self.assertEqual(reasons, [])

    def test_url_in_education_detected(self):
        edu = ["https://facebook.com/some-ustadz", "LIPIA"]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")
        self.assertTrue(any("url" in r.lower() for r in reasons))

    def test_social_media_handle_detected(self):
        edu = ["Follow ustadz di instagram.com/ustadz_x", "S1 Universitas Y"]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")
        self.assertTrue(any("social" in r.lower() for r in reasons))

    def test_bio_content_in_education_detected_by_length(self):
        edu = [
            "S1 Universitas Islam Madinah",
            "Beliau merupakan alumni S-2, Jurusan Hadis, Universitas Islam Madinah. Beliau dikenal sebagai ustadz manajemen qalbu dan keindahan iman. Banyak kajian dan karya ilmiah beliau yang bertajuk 'obat hati' sepanjang karirnya hingga sekarang dan telah menghasilkan banyak karya tulis yang tersebar di berbagai media",
        ]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")
        self.assertTrue(any("long" in r.lower() or "bio" in r.lower() or "excess" in r.lower() for r in reasons))

    def test_page_header_detected(self):
        edu = ["Tentang Kami - Meniti Jejak Para Sahabat", "S1 Universitas X"]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")

    def test_search_snippet_detected(self):
        edu = ["Download kajian nama Ahlus Sunnah dan Ahlul Bid'ah", "S1 Universitas X"]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")

    def test_event_description_detected(self):
        edu = [
            "Audio kajian bersama ustad Abu Ihsan Al-Atsary dari medan Sumatra Utara pada kajian intensif dua hari di masjid An-Nuur",
        ]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")

    def test_empty_education_is_incomplete(self):
        verdict, _ = self.audit_pendidikan([])
        self.assertEqual(verdict, "incomplete")

    def test_non_string_entry_in_list_detected(self):
        edu = ["S1 Universitas X", 123, None]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")
        self.assertTrue(any("non_string" in r.lower() or "type" in r.lower() for r in reasons))

    def test_narrative_paragraph_detected_by_verbosity(self):
        edu = ["sekolah di MAN 2 Kebumen ditempuh dalam waktu tiga tahun pelajaran, mulai dari Kelas X sampai Kelas XII dengan penuh kesungguhan dan kesabaran"]
        verdict, reasons = self.audit_pendidikan(edu)
        self.assertEqual(verdict, "corrupt")


class TestMultiAgentPartitioning(unittest.TestCase):
    """Multi-agent safe file partitioning for parallel execution."""

    def setUp(self):
        from audit_corruption import partition_files
        self.partition_files = partition_files

    def test_partition_no_overlap(self):
        all_files = [f"file_{i}" for i in range(100)]
        batches = self.partition_files(all_files, num_agents=4)
        all_assigned = []
        for batch in batches:
            all_assigned.extend(batch)
        self.assertEqual(sorted(all_assigned), sorted(all_files))
        self.assertEqual(len(set(all_assigned)), len(all_files))

    def test_partition_handles_uneven_division(self):
        all_files = [f"file_{i}" for i in range(10)]
        batches = self.partition_files(all_files, num_agents=4)
        sizes = [len(b) for b in batches]
        self.assertEqual(sum(sizes), 10)
        self.assertLessEqual(max(sizes) - min(sizes), 1)

    def test_partition_single_agent(self):
        all_files = [f"file_{i}" for i in range(50)]
        batches = self.partition_files(all_files, num_agents=1)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 50)

    def test_partition_more_agents_than_files(self):
        all_files = [f"file_{i}" for i in range(3)]
        batches = self.partition_files(all_files, num_agents=10)
        non_empty = [b for b in batches if b]
        self.assertEqual(sum(len(b) for b in batches), 3)
        self.assertLessEqual(len(non_empty), 3)


class TestAuditState(unittest.TestCase):
    """State file handling: atomic write, resume, merge."""

    def setUp(self):
        from audit_corruption import AuditState
        self.tmpdir = tempfile.mkdtemp()
        self.state = AuditState(state_dir=self.tmpdir, agent_id="test")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_atomic_write_creates_file(self):
        self.state.mark_audited("kajian-xxx", "clean", [])
        files = os.listdir(self.tmpdir)
        self.assertIn("audit_state_agent_test.json", files)

    def test_mark_audited_persists(self):
        self.state.mark_audited("kajian-xxx", "clean", [])
        new_state = type(self.state)(state_dir=self.tmpdir, agent_id="test")
        entry = new_state.get_entry("kajian-xxx")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["verdict"], "clean")

    def test_get_unprocessed_files(self):
        all_files = ["kajian-a", "kajian-b", "kajian-c"]
        self.state.mark_audited("kajian-a", "clean", [])
        remaining = self.state.get_unprocessed(all_files)
        self.assertEqual(remaining, ["kajian-b", "kajian-c"])

    def test_summary_counts(self):
        self.state.mark_audited("kajian-a", "clean", [])
        self.state.mark_audited("kajian-b", "corrupt", ["url in education"])
        self.state.mark_audited("kajian-c", "ambiguous", ["wikipedia name mismatch"])
        summary = self.state.summary()
        self.assertEqual(summary["clean"], 1)
        self.assertEqual(summary["corrupt"], 1)
        self.assertEqual(summary["ambiguous"], 1)
        self.assertEqual(summary["total"], 3)

    def test_merge_agents(self):
        from audit_corruption import merge_states
        s1 = type(self.state)(state_dir=self.tmpdir, agent_id="1")
        s1.mark_audited("kajian-a", "clean", [])
        s2 = type(self.state)(state_dir=self.tmpdir, agent_id="2")
        s2.mark_audited("kajian-b", "corrupt", ["url"])
        master = merge_states(self.tmpdir, agent_ids=["1", "2"])
        self.assertIn("kajian-a", master["audited_files"])
        self.assertIn("kajian-b", master["audited_files"])


class TestQuarantine(unittest.TestCase):
    """Quarantine + delete pattern per Lesson #10."""

    def setUp(self):
        from audit_corruption import quarantine_file
        self.quarantine_file = quarantine_file
        self.tmpdir = tempfile.mkdtemp()
        self.detail_path = os.path.join(self.tmpdir, "kajian-xxx.json")
        with open(self.detail_path, "w") as f:
            json.dump({"name": "Test", "bio": "corrupt"}, f)
        self.quarantine_dir = os.path.join(self.tmpdir, "quarantine")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_quarantine_moves_file_with_metadata(self):
        result = self.quarantine_file(
            self.detail_path,
            self.quarantine_dir,
            reason="wikipedia_name_mismatch",
            original_slug="kajian-xxx",
        )
        self.assertFalse(os.path.exists(self.detail_path))
        self.assertTrue(os.path.exists(result))
        with open(result) as f:
            data = json.load(f)
        self.assertIn("_quarantine_metadata", data)
        self.assertEqual(data["_quarantine_metadata"]["reason"], "wikipedia_name_mismatch")
        self.assertEqual(data["_quarantine_metadata"]["original_slug"], "kajian-xxx")
        self.assertIn("original_content", data)


class TestGitHubIntegration(unittest.TestCase):
    """GitHub issue creation for ambiguous cases — idempotent."""

    def setUp(self):
        from audit_corruption import format_audit_issue_body, find_existing_audit_issue, AUDIT_LABEL
        self.format_audit_issue_body = format_audit_issue_body
        self.find_existing_audit_issue = find_existing_audit_issue
        self.AUDIT_LABEL = AUDIT_LABEL

    def test_issue_body_includes_required_fields(self):
        body = self.format_audit_issue_body(
            profile_name="Muhammad Zaki",
            slug="kajian-muhammad-zaki",
            verdict="ambiguous",
            reasons=["wikipedia name mismatch"],
            detail_path="detail/kajian-muhammad-zaki.json",
        )
        self.assertIn("Muhammad Zaki", body)
        self.assertIn("kajian-muhammad-zaki", body)
        self.assertIn("AMBIGUOUS", body)
        self.assertIn("wikipedia name mismatch", body)
        self.assertIn("detail/kajian-muhammad-zaki.json", body)
        self.assertIn("Manual review", body)


class TestAuditCLI(unittest.TestCase):
    """Command-line interface: --batch, --max-api, --agents flags."""

    def setUp(self):
        from audit_corruption import parse_args
        self.parse_args = parse_args

    def test_default_batch_size(self):
        args = self.parse_args(["--detail-dir", "/tmp"])
        self.assertEqual(args.batch, 5)
        self.assertEqual(args.max_api, 3)
        self.assertEqual(args.agents, 1)

    def test_custom_batch_size(self):
        args = self.parse_args(["--batch", "20", "--max-api", "10", "--agents", "4"])
        self.assertEqual(args.batch, 20)
        self.assertEqual(args.max_api, 10)
        self.assertEqual(args.agents, 4)

    def test_dry_run_flag(self):
        args = self.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main(verbosity=2)
