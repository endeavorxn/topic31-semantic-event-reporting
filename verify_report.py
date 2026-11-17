"""Verify the built report PDF against the course format rules and layout QA."""
import json
import re
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
PDF = HERE / "Topic31_Semantic_Event_Reporting_Report_EN.pdf"
R = json.loads((HERE / "results.json").read_text())

raw = PDF.read_bytes()
assert raw.startswith(b"%PDF"), "R1: not a PDF file"
print("R1 PASS: %PDF header")

doc = pymupdf.open(str(PDF))
texts = [doc[i].get_text() for i in range(doc.page_count)]
full = "\n".join(texts)

# locate appendix start (there is none: R3 satisfied via repository link)
assert "APPENDIX A" not in full, "appendix should be removed"
assert "github.com/endeavorxn/topic31-semantic-event-reporting" in full, \
    "R3: repository link missing"
assert "simulate.py" in full, "R3: run instructions missing"
main_pages = doc.page_count
print(f"pages: total={doc.page_count} (= main body, limit 15); no appendix")
w = doc[0].rect.width
print(f"page size: {w:.0f} x {doc[0].rect.height:.0f} (Letter=612x792)")
assert main_pages <= 15, "R2 FAIL: main body exceeds 15 single-column pages"
# single-column check: no page has two distinct text-column start clusters
for i in range(doc.page_count):
    xs = sorted({round(x[0]) for x in doc[i].get_text("words") if len(x[4]) > 2})
    if len(xs) > 1:
        gaps = [(a, b) for a, b in zip(xs, xs[1:]) if b - a > 60]
        assert not gaps, f"R2: two-column layout detected on page {i+1}: {gaps}"
print(f"R2 PASS: single-column report, {main_pages} <= 15 pages")
print("R4 PASS: no appendix present, rule not applicable")

assert "requirement R3" in full and "github.com/endeavorxn/topic31-semantic-event-reporting" in full, \
    "GitHub link missing from report (R3 option a)"
print(f"R3 PASS: repository link in report body")

checks = {
    "abstract kb": f"{R['loss']['0.1']['summary']['Hybrid']['bytes']['mean']/1000:.3f}",
    "periodic kb": f"{R['loss']['0.1']['summary']['Periodic']['bytes']['mean']/1000:.3f}",
    "hybrid rmse": f"{R['loss']['0.1']['summary']['Hybrid']['rmse']['mean']:.3f}",
    "refs": "[9] A. Li, S. Wu",
    "slow drift": "slow-drift",
}
for name, needle in checks.items():
    print(f"  content '{name}':", "OK" if needle in full else "MISSING")

img_pages = [i + 1 for i in range(doc.page_count) if doc[i].get_images()]
n_imgs = sum(len(doc[i].get_images()) for i in range(doc.page_count))
print("embedded images:", n_imgs, "on pages", img_pages)

for i in range(1, 6):
    assert f"Fig. {i}." in full, f"Fig. {i} caption missing"
romans = ["I", "II", "III", "IV", "V", "VI", "VII"]
for i, rm in enumerate(romans, 1):
    assert f"TABLE {rm}" in full, f"TABLE {rm} caption missing"
print("Fig. 1-5 and TABLE I-VII captions: OK")

# layout QA: margins and small text (Letter geometry)
LMARGIN, RMARGIN, TOP, BOT = 52.0, 560.0, 30.0, 768.0
bad, small = [], []
for i in range(doc.page_count):
    for b in doc[i].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                x0, y0, x1, y1 = s["bbox"]
                if x0 < LMARGIN or x1 > RMARGIN or y0 < TOP or y1 > BOT:
                    bad.append((i + 1, round(x0), round(x1), s["text"][:40]))
                if s["size"] < 6.6 and not re.match(r"^\d{3}\s", s["text"]):
                    small.append((i + 1, round(s["size"], 2), s["text"][:40]))
print("out-of-margin spans:", len(bad))
for b in bad[:8]:
    print("   ", b)
print("suspiciously small spans (<6.6pt):", len(small))
for s in small[:8]:
    print("   ", s)

heads = ["I. INTRODUCTION", "II. LITERATURE", "III. SYSTEM MODEL",
         "IV. RULE BEHAVIOUR", "V. EXPERIMENTAL DESIGN", "VI. RESULTS",
         "VII. DISCUSSION", "VIII. CONCLUSION",
         "REFERENCES AND REPRODUCIBILITY"]
pos = [full.find(h) for h in heads]
print("headings found in order:", all(p >= 0 for p in pos) and pos == sorted(pos))

# serif font check (IEEE look)
fonts = set()
for i in range(min(3, doc.page_count)):
    for b in doc[i].get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                fonts.add(s["font"])
print("fonts in use:", sorted(fonts)[:6])

# footer page number present (bottom strip of each page)
miss_pg = []
for i in range(doc.page_count):
    words = doc[i].get_text("words")
    bottom = [wd[4] for wd in words if wd[1] > 740]
    if str(i + 1) not in bottom:
        miss_pg.append(i + 1)
print("pages missing footer number:", miss_pg if miss_pg else "none")
print("\nVERIFY DONE")
