"""
Shared helpers for Wikipedia enrichment.

Lesson #14 (AGENTS.md): Wikipedia search can return the wrong page for generic
names. Searching for "Muhammad Zaki" returns the "Muhammad" (Nabi Muhammad ﷺ)
page, and saving the resulting bio creates corruption.

This module provides verify_wikipedia_match() — a name-match guard to be called
BEFORE saving any Wikipedia-sourced bio. It rejects pages whose title does not
contain all significant words of the queried name (optionally cross-checked
against the first paragraph of the extract).
"""
import re
import unicodedata


HONORIFICS = {
    "ustadz", "ustad", "ustadzah", "ust", "ustz",
    "haji", "h", "hj", "hajah",
    "syaikh", "sheikh", "syekh", "shaykh",
    "kiai", "kyai",
    "dr", "drs", "prof", "lc", "ma", "mh", "mpd", "mpdi",
    "kh", "k.h", "k.h.",
    "m.a", "m.a.", "ph.d", "ph.d.",
    "al-hafidz", "al-hafiz", "alim", "alimullah",
    "habib", "sayyid", "syarif",
    "tuan", "mister", "mr", "mrs", "ms",
}

_CONNECTOR_WORDS = {"bin", "binti", "ibn", "bint", "al", "el", "van", "von", "de", "di"}


def _normalize(s):
    """NFKC normalize + lowercase + strip whitespace."""
    if s is None:
        return ""
    return unicodedata.normalize("NFKC", str(s)).lower().strip()


def _word_set(s):
    """Tokenize normalized string into a set of words (letters/digits/underscore only)."""
    return set(re.sub(r"[^\w\s]", " ", _normalize(s)).split())


def _significant_words(name):
    """Extract significant words: NFKC, lowercase, no honorifics, no connectors, len > 2."""
    cleaned = re.sub(r"[^\w\s]", " ", _normalize(name))
    words = cleaned.split()
    return [
        w for w in words
        if w not in HONORIFICS and w not in _CONNECTOR_WORDS and len(w) > 2
    ]


def verify_wikipedia_match(query_name, wiki_title, wiki_first_para=None):
    """
    Verify that a Wikipedia page is actually about the queried person.

    Primary rule: every significant word from query_name must appear in
    wiki_title. This catches the Lesson #14 corruption: "Muhammad Zaki" query
    with "Muhammad" (Nabi) page title — "zaki" missing → REJECT.

    Secondary rule (optional): if a first-paragraph excerpt is provided, the
    same all-words rule is checked against the union of title + first_para
    words. This salvages correct matches when Wikipedia uses a generic title
    or a redirect (e.g. "Muhammad" → first_para mentions "Zaki").

    Args:
        query_name: The name from master.json (or contribution source).
        wiki_title: The Wikipedia page title returned by the API.
        wiki_first_para: Optional first 100-500 chars of the page extract.

    Returns:
        True if the page appears to be about the query, False otherwise.
    """
    if not query_name or not wiki_title:
        return False

    q_words = _significant_words(query_name)
    if not q_words:
        return False

    title_words = _word_set(wiki_title)

    if all(w in title_words for w in q_words):
        return True

    if wiki_first_para:
        para_words = _word_set(wiki_first_para)
        combined = title_words | para_words
        if all(w in combined for w in q_words):
            return True

    return False
