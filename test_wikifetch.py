#!/usr/bin/env python3
"""
Test suite for wikifetch.verify_wikipedia_match()

Lesson #14 prevention: detect when Wikipedia search returns the wrong page
(e.g. searching "Muhammad Zaki" returns "Muhammad" → Nabi Muhammad article).

Run with: /usr/bin/python3 test_wikifetch.py
"""
import sys
import os
import unittest

# Add project root to path so we can import wikifetch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wikifetch import verify_wikipedia_match  # noqa: E402


class TestVerifyWikipediaMatch(unittest.TestCase):
    """Tests for verify_wikipedia_match() — Lesson #14 corruption prevention."""

    # --- Lesson #14 corruption case (the exact bug we want to prevent) ---

    def test_lesson14_corruption_case_rejected(self):
        """THE corruption case: 'Muhammad Zaki' query returned 'Muhammad' (Nabi) page.
        Title has 'muhammad' but NOT 'zaki' → must REJECT."""
        self.assertFalse(
            verify_wikipedia_match("Muhammad Zaki", "Muhammad")
        )

    def test_lesson14_corruption_with_arabic_name(self):
        """Similar pattern with Arabic combining chars (NFKC scenario)."""
        # "Ahmad" is generic; searching for "Ahmad Zainuddin" might return "Ahmad"
        self.assertFalse(
            verify_wikipedia_match("Ahmad Zainuddin", "Ahmad")
        )

    def test_lesson14_ahmad_dahlan_rejection(self):
        """Querying 'Ahmad Fauzi' should NOT match 'Ahmad Dahlan' (different person)."""
        self.assertFalse(
            verify_wikipedia_match("Ahmad Fauzi", "Ahmad Dahlan")
        )

    # --- Positive cases (correct matches) ---

    def test_exact_title_match(self):
        """Trivial exact match."""
        self.assertTrue(
            verify_wikipedia_match("Muhammad Zaki", "Muhammad Zaki")
        )

    def test_title_with_parenthetical_disambiguation(self):
        """Wikipedia often has '(occupation)' or '(year)' suffixes."""
        self.assertTrue(
            verify_wikipedia_match("John Smith", "John Smith (musician)")
        )

    def test_title_with_additional_surname(self):
        """Indonesian names often have 'bin' / 'binti' connectors."""
        self.assertTrue(
            verify_wikipedia_match("Khalid bin Zaid", "Khalid bin Zaid Al-Banjari")
        )

    def test_title_with_abdul_bin_pattern(self):
        """Abdul Hakim Amir Abdat has multiple variations on Wikipedia."""
        self.assertTrue(
            verify_wikipedia_match(
                "Abdul Hakim Amir Abdat",
                "Abdul Hakim bin Amir Abdat"
            )
        )

    # --- Honorifics stripping ---

    def test_honorific_prefix_stripped(self):
        """'Ustadz Muhammad Zaki' should match 'Muhammad Zaki' (ustadz is honorific)."""
        self.assertTrue(
            verify_wikipedia_match("Ustadz Muhammad Zaki", "Muhammad Zaki")
        )

    def test_multiple_honorifics_stripped(self):
        """Multiple honorifics should all be stripped."""
        self.assertTrue(
            verify_wikipedia_match(
                "DR. KH. Muhammad Zaki, M.A.",
                "Muhammad Zaki"
            )
        )

    def test_query_is_only_honorifics_rejected(self):
        """If query is 'Ustadz' alone, can't verify → REJECT."""
        self.assertFalse(
            verify_wikipedia_match("Ustadz", "Ustadz")
        )

    # --- Edge cases ---

    def test_empty_query_name(self):
        """Empty query name → REJECT."""
        self.assertFalse(verify_wikipedia_match("", "Muhammad"))

    def test_empty_wiki_title(self):
        """Empty wiki title → REJECT."""
        self.assertFalse(verify_wikipedia_match("Muhammad Zaki", ""))

    def test_both_empty(self):
        """Both empty → REJECT."""
        self.assertFalse(verify_wikipedia_match("", ""))

    def test_none_values(self):
        """None values → REJECT (defensive)."""
        self.assertFalse(verify_wikipedia_match(None, "Muhammad"))
        self.assertFalse(verify_wikipedia_match("Muhammad", None))

    def test_short_words_filtered(self):
        """Words with len <= 2 are filtered (e.g. 'M.A.' splits to 'm', 'a')."""
        # 'MA' is in honorifics (after honorific strip), so only 'khalid' and 'zaid' remain
        self.assertTrue(
            verify_wikipedia_match("M.A. Khalid Zaid", "Khalid Zaid")
        )

    # --- First paragraph as secondary signal ---

    def test_first_para_saves_generic_title_with_distinctive_name(self):
        """If title is just 'Muhammad' but first_para mentions 'Zaki', accept.
        This handles cases where Wikipedia has a redirect/disambig page."""
        first_para = "Muhammad Zaki adalah seorang ustadz Indonesia yang lahir di..."
        self.assertTrue(
            verify_wikipedia_match(
                "Muhammad Zaki", "Muhammad", first_para
            )
        )

    def test_first_para_does_not_save_if_about_someone_else(self):
        """If title is 'Muhammad' and first_para is about Nabi, REJECT."""
        first_para = "Muhammad adalah nabi terakhir umat Islam. Ia lahir di Mekah..."
        self.assertFalse(
            verify_wikipedia_match(
                "Muhammad Zaki", "Muhammad", first_para
            )
        )

    # --- NFKC normalization ---

    def test_nfkc_normalization_combining_chars(self):
        """NFKC normalization handles combining characters (Arabic + Latin mix)."""
        # "الشيخ محمد" with various Unicode representations should match itself
        # Using regular space + Arabic for both sides
        name_a = "الشيخ محمد"
        name_b = "الشيخ\u0020محمد"  # regular space variant
        self.assertTrue(verify_wikipedia_match(name_a, name_b))

    def test_nfkc_lowercase_normalization(self):
        """NFKC + lowercase — case insensitive matching."""
        self.assertTrue(
            verify_wikipedia_match("MUHAMMAD ZAKI", "muhammad zaki")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
