# Topic 31 — Semantic Event Reporting for Remote Monitoring

Live at **https://github.com/endeavorxn/topic31-semantic-event-reporting**

Reproducible numerical study for the EEEN3008J Wireless Communications
Topic 31 group report: **periodic vs change-only (send-on-delta) vs hybrid
(change threshold + maximum silence interval) reporting** over a
packet-erasure link, with a hold-last-value receiver.

All parameters are illustrative experimental assumptions; no measured
device data is used. Group research draft, 14 November 2026.

## Repository layout

| Path | Purpose |
| --- | --- |
| `report/Topic31_Semantic_Event_Reporting_Report_EN.pdf` | The report: 10-page main body (single column, within the 15-page limit) + Appendix A with the complete code (excluded from the page count per course rule R4). |
| `simulate.py` | Complete numerical script (identical to the report's Appendix A). Runs every experiment, validation gate and stress case; writes `results.json` with per-run values. |
| `results.json` | Raw results produced by `simulate.py` on 2026-11-14 (seeds below). |
| `make_figs.py` | Regenerates the report figures (Figs. 1–5) from `results.json` into `figs/`. |
| `make_report.py` | Rebuilds the report PDF from `results.json` + `figs/`. |
| `verify_report.py` | Re-checks the PDF against course format rules R1–R4 and layout QA. |
| `figs/` | Report figures. |

## How to run

```bash
python simulate.py        # ~1 min; writes results.json and prints a summary
python make_figs.py       # writes figs/*.png (needs matplotlib)
python make_report.py     # rebuilds the PDF (needs pymupdf)
python verify_report.py   # format compliance checks
```

## Environment used

- Windows, Python 3.13.5
- NumPy 2.2.6, SciPy 1.16.1 (t-quantiles)
- Matplotlib 3.10.3, PyMuPDF 2.0 (figures and PDF build only)

## Reproducibility

- Test runs: 30 independent one-hour traces per configuration, seeds
  **1000–1029** (fixed in code).
- Traffic-matched baseline design seeds: **2000–2009** (kept separate from
  test seeds).
- Statistics are run-level: mean ± 95% Student-t interval over runs;
  hybrid–periodic comparisons are paired within each run (identical source
  trace and channel realization).
- Deterministic stress cases (lost onset packet, slow drift) use no random
  draws.
- With the same NumPy version, `simulate.py` regenerates every number in the
  report exactly; different NumPy versions may change RNG stream details.

## Validation

`simulate.py` starts by asserting known-answer cases: a constant source with
no loss sends exactly one packet (change-only) or the expected heartbeats
(hybrid); full sampling without loss reconstructs perfectly; total loss
freezes the receiver; loss-free change-based reporting keeps the error below
delta; and the nominal periodic baseline sends exactly 360 packets = 11,520
bytes = 360 ms airtime = 10.8 mJ of transmit-energy proxy per hour. Four
conservation identities (packets, bytes, airtime, energy) are asserted on
every run.
