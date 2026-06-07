"""
Regression test: Lesson #14 corruption prevention.

The corruption scenario from detail/kajian-muhammad-zaki.json (now quarantined):
- query: "Muhammad Zaki"
- Wikipedia returned: title="Muhammad", extract=Nabi Muhammad article
- File created at 2026-06-07T01:11:08+07:00

This test verifies the guard would have prevented the corruption by testing:
1. Mocked historical corruption data (deterministic)
2. Live Wikipedia API for the same query (current state)

Run with: /usr/bin/python3 test_regression_muhammad_zaki.py
"""
import sys
import os
import json
import urllib.request
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wikifetch import verify_wikipedia_match


CORRUPTION_NABI_BIO = (
    "Muhammad (bahasa Arab: مُحَمَّدcode: ar is deprecated ; ca 570 – 8 Juni 632 M) "
    "adalah seorang pemimpin agama, sosial, dan politik beretnis Arab sekaligus pendiri "
    "agama Islam menurut perspektif sejarah modern. Menurut keyakinan umat Islam, ia "
    "adalah Nabi dan Rasul yang diberikan wahyu ilahi untuk memberitakan dan meneguhkan "
    "prinsip monoteistis dalam ajaran Adam, Ibrahim (Abraham), Musa, Isa (Yesus), dan nabi "
    "lainnya. Ia diyakini sebagai Penutup Para Nabi dalam Islam. Muhammad menyatukan "
    "Jazirah A"
)


def fetch_wiki_title(name, lang="id"):
    """Mimics enrich_sanad.wiki_search — returns (title, extract) or None."""
    url = f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={urllib.parse.quote(name)}&prop=extracts&exintro=true&explaintext=true&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ProfilAsatidz/1.0 (regression test)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        pages = data.get("query", {}).get("pages", {})
        for pid, page in pages.items():
            if pid == "-1":
                return None
            return {
                "title": page.get("title", name),
                "extract": page.get("extract", "")[:500],
            }
    except Exception as e:
        print(f"  ERROR fetching: {e}")
        return None


def main():
    print("=" * 70)
    print("Regression test: Lesson #14 — Muhammad Zaki corruption scenario")
    print("=" * 70)

    failures = 0

    print("\n[PART 1] Mocked historical corruption data (from quarantine file)")
    print("-" * 70)

    query = "Muhammad Zaki"
    mock_corrupt_title = "Muhammad"
    mock_corrupt_extract = CORRUPTION_NABI_BIO

    is_match = verify_wikipedia_match(query, mock_corrupt_title, mock_corrupt_extract)
    print(f"  query       : {query!r}")
    print(f"  mock title  : {mock_corrupt_title!r}  (Wikipedia returned this for the corruption)")
    print(f"  mock extract: Nabi Muhammad bio (truncated)")
    print(f"  verify_wikipedia_match() = {is_match}")

    if is_match:
        print("  FAIL: guard accepted the corruption — would have been saved!")
        failures += 1
    else:
        print("  PASS: guard correctly rejected the corruption")

    print("\n[PART 2] Live Wikipedia API for 'Muhammad Zaki' (current state)")
    print("-" * 70)

    result_id = fetch_wiki_title("Muhammad Zaki", "id")
    if result_id is None:
        print("  ID Wikipedia: no page found (page doesn't exist)")
    else:
        print(f"  ID Wikipedia returned title: '{result_id['title']}'")
        is_match = verify_wikipedia_match("Muhammad Zaki", result_id["title"], result_id["extract"])
        print(f"  verify_wikipedia_match('Muhammad Zaki', '{result_id['title']}', ...) = {is_match}")
        if result_id["title"].lower() == "muhammad":
            if is_match:
                print("  FAIL: API returned 'Muhammad' (Nabi) page and guard accepted it")
                failures += 1
            else:
                print("  PASS: API returned 'Muhammad' (Nabi) page and guard correctly rejected it")
        else:
            print(f"  OK: API returned specific page '{result_id['title']}' (not generic)")

    result_en = fetch_wiki_title("Muhammad Zaki", "en")
    if result_en is None:
        print("  EN Wikipedia: no page found")
    else:
        print(f"  EN Wikipedia returned title: '{result_en['title']}'")
        is_match = verify_wikipedia_match("Muhammad Zaki", result_en["title"], result_en["extract"])
        print(f"  verify_wikipedia_match('Muhammad Zaki', '{result_en['title']}', ...) = {is_match}")
        if result_en["title"].lower() == "muhammad":
            if is_match:
                print("  FAIL: API returned 'Muhammad' (Nabi) page and guard accepted it")
                failures += 1
            else:
                print("  PASS: API returned 'Muhammad' (Nabi) page and guard correctly rejected it")
        else:
            print(f"  OK: API returned specific page '{result_en['title']}' (not generic)")

    print("\n[PART 3] Positive control: 'Abdul Hakim Amir Abdat' (known real match)")
    print("-" * 70)

    result_ok = fetch_wiki_title("Abdul Hakim Amir Abdat", "id")
    if result_ok:
        print(f"  ID Wikipedia returned title: '{result_ok['title']}'")
        is_match = verify_wikipedia_match("Abdul Hakim Amir Abdat", result_ok["title"], result_ok["extract"])
        print(f"  verify_wikipedia_match = {is_match}")
        if is_match:
            print("  PASS: legitimate match preserved")
        else:
            print("  FAIL: legitimate match incorrectly rejected (false negative)")
            failures += 1
    else:
        print("  (No Wikipedia ID page for Abdul Hakim, skipping)")

    print("\n" + "=" * 70)
    if failures == 0:
        print("ALL REGRESSION CHECKS PASSED")
        print("=" * 70)
        return 0
    else:
        print(f"REGRESSION FAILURES: {failures}")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
