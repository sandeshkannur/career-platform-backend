"""
One-time diagnostic: verify the live scorecard PDF report for en and kn-IN.

NOT part of the app. Do not import from app code; talks to a deployed backend
over HTTP only. Requires: requests, PyMuPDF (pip install requests pymupdf) in
whatever throwaway env you run it from — do NOT add these to requirements.txt.

Usage:
    python scripts/verify_pdf_report.py [--base-url https://mapyourcareer.in]

For each locale it:
  - saves the raw PDF to scripts/output/report_{locale}.pdf
  - renders every page to scripts/output/report_{locale}_page{N}.png at 150 DPI
  - extracts the text and runs the checks below, printing PASS/FAIL per check
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import requests
import fitz  # PyMuPDF

# NOTE: the bare domain serves the frontend SPA; the API is on the api. subdomain.
DEFAULT_BASE_URL = "https://api.mapyourcareer.in"
EMAIL = "teststudent1@mapyourcareer.in"
PASSWORD = "BetaTest@2026"
LOCALES = ["en", "kn-IN"]
EXPECTED_CAREER_COUNT = 5  # test student is free tier

# NOTE: "salary" and "pathway" are deliberately NOT in this list — they appear
# legitimately in the closing CTA (naming premium features, not leaking data).
FORBIDDEN_STRINGS = [
    "₹",  # ₹
    "keyskill",
    "automation risk",
    "future outlook",
    "score",
    "weight",
    "career_id",
]

# Markers for section presence — English + Kannada (kn-IN PDFs localize titles).
# NOTE: PyMuPDF extraction of WeasyPrint's subsetted Kannada font is lossy for
# conjunct glyphs (ToUnicode CMap gaps), so exact Kannada title matching is
# unreliable; the structural pattern below ("— <count> <kannada word>") is the
# robust signal for the cluster-signals bullet list. Visual truth = the PNGs.
CLUSTER_SECTION_MARKERS = ["cluster signals", "ಕ್ಲಸ್ಟರ್ ಸಂಕೇತಗಳು"]
CLUSTER_STRUCTURE_RE = re.compile(r"—\s*\d+\s*(career|[ಀ-೿])", re.IGNORECASE)  # "— 2 careers" / "— 1 ವೃತ್ತಿ"
CTA_MARKERS = [
    "see your full results",
    "log in to your account",
    "does not constitute professional career counselling advice",
    "ನಿಮ್ಮ ಪೂರ್ಣ ಫಲಿತಾಂಶಗಳನ್ನು ನೋಡಿ",
    "ನಿಮ್ಮ ಖಾತೆಗೆ ಲಾಗಿನ್",
    "ವೃತ್ತಿಪರ ವೃತ್ತಿ ಮಾರ್ಗದರ್ಶನ",
]

KANNADA_RE = re.compile(r"[ಀ-೿]")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def login(base_url: str) -> str:
    r = requests.post(
        f"{base_url}/v1/auth/login",
        data={"username": EMAIL, "password": PASSWORD},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_student_id(base_url: str, token: str) -> int:
    r = requests.get(
        f"{base_url}/v1/students/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def fetch_pdf(base_url: str, token: str, student_id: int, locale: str) -> bytes:
    r = requests.get(
        f"{base_url}/v1/reports/scorecard/{student_id}",
        params={"format": "pdf", "locale": locale},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "pdf" not in ctype:
        raise RuntimeError(f"Expected a PDF response, got content-type={ctype!r}: {r.text[:300]}")
    return r.content


def render_pages(pdf_path: Path, locale: str) -> list[Path]:
    pngs = []
    with fitz.open(pdf_path) as doc:
        zoom = 150 / 72  # 150 DPI
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            out = OUTPUT_DIR / f"report_{locale}_page{i}.png"
            pix.save(out)
            pngs.append(out)
    return pngs


def extract_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as doc:
        return "\n".join(page.get_text() for page in doc)


def find_career_titles(text: str) -> list[str]:
    """
    Each career card renders as one line: '<title>  <5 stars> <band label>'.
    The 5-star run (filled + unfilled '★') is unique to career cards, so lines
    containing '★' identify cards and the text before the first star is the title.
    """
    titles = []
    for line in text.splitlines():
        if "★" in line:
            title = line.split("★")[0].strip().strip(" ").strip()
            if title:
                titles.append(title)
    return titles


def snippet_around(text: str, idx: int, width: int = 60) -> str:
    lo, hi = max(0, idx - width), min(len(text), idx + width)
    return " ".join(text[lo:hi].split())


def check_locale(base_url: str, token: str, student_id: int, locale: str) -> bool:
    print(f"\n{'=' * 70}\nLOCALE: {locale}\n{'=' * 70}")

    pdf_bytes = fetch_pdf(base_url, token, student_id, locale)
    pdf_path = OUTPUT_DIR / f"report_{locale}.pdf"
    pdf_path.write_bytes(pdf_bytes)
    print(f"Saved PDF: {pdf_path} ({len(pdf_bytes):,} bytes)")

    pngs = render_pages(pdf_path, locale)
    for p in pngs:
        print(f"Rendered:  {p} ({p.stat().st_size:,} bytes)")

    text = extract_text(pdf_path)
    lower = text.lower()
    all_ok = True

    def report(name: str, ok: bool, detail: str = "") -> None:
        nonlocal all_ok
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    print("\nChecks:")

    # a) career count
    titles = find_career_titles(text)
    report(
        f"career count == {EXPECTED_CAREER_COUNT} (free tier)",
        len(titles) == EXPECTED_CAREER_COUNT,
        f"found {len(titles)}",
    )

    # b) forbidden strings
    hits = []
    for bad in FORBIDDEN_STRINGS:
        for m in re.finditer(re.escape(bad), lower):
            hits.append((bad, snippet_around(text, m.start())))
    if hits:
        report("no forbidden strings", False, f"{len(hits)} hit(s)")
        for bad, snip in hits:
            print(f"         forbidden {bad!r} in: ...{snip}...")
    else:
        report("no forbidden strings", True)

    # c) cluster signals section present
    marker = next((m for m in CLUSTER_SECTION_MARKERS if m in lower), None)
    structural = CLUSTER_STRUCTURE_RE.search(text)
    report(
        "cluster signals section present",
        bool(marker or structural),
        f"matched {marker!r}" if marker else ("matched structural '— N careers' pattern" if structural else "no marker found"),
    )

    # d) closing CTA / disclaimer present
    cta_hits = [m for m in CTA_MARKERS if m in lower]
    report(
        "closing CTA/disclaimer present",
        bool(cta_hits),
        f"matched {cta_hits}" if cta_hits else "no CTA/disclaimer markers found",
    )

    # e) Kannada script actually present (kn-IN only)
    if locale == "kn-IN":
        kn_chars = KANNADA_RE.findall(text)
        ok = len(kn_chars) > 0
        detail = f"{len(kn_chars)} Kannada codepoints found"
        if ok:
            sample = KANNADA_RE.search(text)
            detail += f", e.g. {unicodedata.name(sample.group(), '?')}"
        else:
            detail += " — text is not localized or the font did not embed"
        report("Kannada Unicode characters present", ok, detail)

    print("\nCareer titles found (visual cross-check):")
    if titles:
        for i, t in enumerate(titles, 1):
            print(f"  {i}. {t}")
    else:
        print("  (none detected)")

    return all_ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify live scorecard PDF report (en + kn-IN)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = ap.parse_args()
    base_url = args.base_url.rstrip("/")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Backend: {base_url}")
    token = login(base_url)
    print("Login OK")
    student_id = get_student_id(base_url, token)
    print(f"student_id = {student_id}")

    results = {loc: check_locale(base_url, token, student_id, loc) for loc in LOCALES}

    print(f"\n{'=' * 70}\nOVERALL\n{'=' * 70}")
    for loc, ok in results.items():
        print(f"  {loc}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
