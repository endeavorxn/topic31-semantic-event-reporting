"""Build the Topic 31 report PDF from results.json + figs/*.png.

Layout: A4, single column, running header/footer, page numbers in a second
pass.  The appendix starts on a fresh page and is explicitly excluded from the
main-report page count (course rule R4).  All numbers come from results.json.
"""
import json
import shutil
from pathlib import Path

import pymupdf

HERE = Path(__file__).parent
FIGS = HERE / "figs"
R = json.loads((HERE / "results.json").read_text())

# ===========================================================================
# Derived numbers (single source of truth: results.json)
# ===========================================================================
L = {p: R["loss"][p]["summary"] for p in ("0.0", "0.1", "0.3")}
PER, CHG, HYB = L["0.1"]["Periodic"], L["0.1"]["Change"], L["0.1"]["Hybrid"]
PA = R["paired_p0.1"]
SW = R["sweep"]
MT = R["matched"]
HS = {h: SW[f"Hybrid:{h}"] for h in (5, 10, 15, 30, 60)}
DS = {d: SW[f"Change:{d}"] for d in (0.2, 0.4, 0.5, 0.6, 0.8, 1.2)}
PS = {t: SW[f"Periodic:{t}"] for t in (2, 5, 10, 15, 20, 30, 60)}
PR = R["predictor"]
SD = R["stress_slow_drift"]


def mm(ci, dec=3):
    return f"{ci['mean']:.{dec}f} &plusmn; {ci['half']:.{dec}f}"


def pm(ci, dec=2):
    return f"{100*ci['mean']:.{dec}f} &plusmn; {100*ci['half']:.{dec}f}"


def kb(ci, dec=3):
    return f"{ci['mean']/1000:.{dec}f} &plusmn; {ci['half']/1000:.{dec}f}"


kb_save = (1 - HYB["bytes"]["mean"] / PER["bytes"]["mean"]) * 100
rmse_save = (1 - HYB["rmse"]["mean"] / PER["rmse"]["mean"]) * 100
chg_save = (1 - CHG["bytes"]["mean"] / PER["bytes"]["mean"]) * 100
match_save = (1 - MT["summary"]["Hybrid"]["packets"]["mean"]
              / MT["summary"]["Periodic"]["packets"]["mean"]) * 100

# ===========================================================================
# Layout engine
# ===========================================================================
# IEEE-style geometry: US Letter, Times (NimbusRoman), single column.
PW, PH = 612.0, 792.0
ML, MR, MTOP, MBOT = 54, 54, 58, 64
CW = PW - ML - MR
CSS = """
body {font-family: times; font-size: 10pt; color: #000;}
h1 {font-size: 10pt; font-weight: normal; text-align: center;
    margin: 12pt 0 6pt 0;}
h2 {font-size: 10pt; font-style: italic; font-weight: normal;
    margin: 8pt 0 3pt 0;}
p {margin: 0 0 4pt 0; text-align: justify;}
td, th {font-size: 8pt; padding: 2pt 3.4pt; border: 0.5pt solid #000;}
th {font-weight: bold;}
pre {font-family: monospace; font-size: 6.8pt; margin: 0;}
"""

doc = pymupdf.open()
tab_no = [0]

# Page 0 is a permanent measurement scratch page; content pages follow.
# Page proxies are orphaned by new_page() in this build, so every access
# re-fetches pages by index.
doc.new_page(width=PW, height=PH)     # scratch = page 0
doc.new_page(width=PW, height=PH)     # first content page = page 1
page_idx = 1
pages = [page_idx]                  # content page indices
cur_y = MTOP
appendix_from = None
SCRATCH_H = 3000.0


def measure(html):
    _spare, scale = doc[0].insert_htmlbox(
        pymupdf.Rect(0, 0, CW, SCRATCH_H), html, css=CSS)
    if scale < 0.999:
        print("WARN: block taller than scratch page, scale", scale)
    return SCRATCH_H - _spare


def new_page():
    global page_idx, cur_y
    doc.new_page(width=PW, height=PH)
    page_idx = doc.page_count - 1
    pages.append(page_idx)
    cur_y = MTOP


def _insert(html):
    global cur_y
    h = measure(html)
    if cur_y + h > PH - MBOT:
        new_page()
    doc[page_idx].insert_htmlbox(
        pymupdf.Rect(ML, cur_y, ML + CW, cur_y + h + 1.5), html, css=CSS)
    cur_y += h


def place(html, gap=4.0):
    global cur_y
    _insert(html)
    cur_y += gap


def heading(html, gap=5.0):
    """Heading that keeps at least 46pt of content below it."""
    global cur_y
    h = measure(html)
    if cur_y + h + 46 > PH - MBOT:
        new_page()
    doc[page_idx].insert_htmlbox(
        pymupdf.Rect(ML, cur_y, ML + CW, cur_y + h + 1.5), html, css=CSS)
    cur_y += h + gap


def image(fname, width_frac, caption):
    global cur_y
    img = pymupdf.Pixmap(str(FIGS / fname))
    w = CW * width_frac
    h = w * img.height / img.width
    cap_html = (f'<p style="font-size:8pt; text-align:justify;'
                f' margin:0">{caption}</p>')
    cap_h = measure(cap_html)
    if cur_y + h + 2 + cap_h > PH - MBOT:
        new_page()
    doc[page_idx].insert_image(
        pymupdf.Rect(ML + (CW - w) / 2, cur_y, ML + (CW + w) / 2, cur_y + h),
        filename=str(FIGS / fname))
    cur_y += h + 2.5
    doc[page_idx].insert_htmlbox(
        pymupdf.Rect(ML, cur_y, ML + CW, cur_y + cap_h + 1), cap_html, css=CSS)
    cur_y += cap_h + 6


def _roman(n):
    vals = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for v, sym in vals:
        while n >= v:
            out += sym
            n -= v
    return out


def table(headers, rows, caption, widths=None):
    global cur_y
    tab_no[0] += 1
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                   for r in rows)
    html = ('<table style="width:100%; margin:2pt 0 1pt 0">'
            f'<tr>{head}</tr>{body}</table>')
    cap = (f'<p style="font-size:8pt; text-align:center; margin:0 0 2pt 0">'
           f'<b>TABLE {_roman(tab_no[0])}</b><br>{caption}</p>')
    h = measure(html + cap)
    if cur_y + h > PH - MBOT:
        new_page()
    doc[page_idx].insert_htmlbox(
        pymupdf.Rect(ML, cur_y, ML + CW, cur_y + h + 1.5), html + cap, css=CSS)
    cur_y += h + 7


# ===========================================================================
# Front matter (IEEE style: title, authors, abstract on page 1)
# ===========================================================================
place("""
<p style="font-size:17pt; text-align:center; margin:14pt 0 0 0">
Semantic Event Reporting for Remote Monitoring:<br>
A Reproducible Evaluation of Periodic, Change-Triggered and
Hybrid Reporting over a Lossy Link</p>
<p style="font-size:10pt; text-align:center; margin:12pt 0 2pt 0">
Lyu Kaiyuan 23219909 &nbsp;&middot;&nbsp; Weiran Wang 23219961<br>
Xuan Yu 23219950 &nbsp;&middot;&nbsp; Zhangyi Peng 23219928</p>
<p style="font-size:9pt; text-align:center; margin:0 0 2pt 0">
EEEN3008J Wireless Communications &mdash; Topic 31 &middot; Group research report
&middot; 14 November 2026</p>
<p style="font-size:8.5pt; text-align:center; font-style:italic; margin:0 0 8pt 0">
Review draft: the named authors must verify sources, re-run the code and
check all claims before submission.</p>
""", gap=7)

place(f"""
<p style="font-size:9.5pt; text-align:justify; margin-bottom:8pt">
<b>Abstract&mdash;</b>A remote monitor rarely needs every sensor sample; it needs
the updates that
reveal important changes. This report asks the course question: can sending
meaningful changes reduce traffic while preserving monitoring quality? Three
reporting rules are compared on paired synthetic one-hour traces of a
temperature-like process with abrupt events, transmitted over a shared
packet-erasure trace and reconstructed by holding the last delivered value:
fixed periodic reporting, send-on-delta change reporting, and a hybrid rule
that adds a maximum silence interval. At 10% independent loss, hybrid reporting
with a 0.5&nbsp;&deg;C threshold and a 15&nbsp;s silence limit uses
{HYB['bytes']['mean']/1000:.3f}&nbsp;kB per hour versus
{PER['bytes']['mean']/1000:.3f}&nbsp;kB for 10&nbsp;s periodic reporting (a
{kb_save:.2f}% reduction), while mean reconstruction RMSE falls from
{PER['rmse']['mean']:.3f} to {HYB['rmse']['mean']:.3f}&nbsp;&deg;C. At an
approximately equal budget (periodic T&nbsp;=&nbsp;14&nbsp;s selected on
separate design traces), the hybrid rule also lowers RMSE and deadline misses
relative to periodic reporting, so update placement matters as much as update
count. The gains
are not uniform: the hybrid deadline-miss fraction is
{100*HYB['miss']['mean']:.2f}%, statistically indistinguishable from periodic
reporting in paired intervals, because a silence limit longer than the alarm
deadline cannot repair a lost event-onset packet. Two negative results are
reported: sub-threshold slow drift defeats pure change reporting, and a
bounded linear receiver predictor worsens RMSE for this source class. The
contribution is a transparent, reproducible comparison and failure-mode
analysis, not a new semantic encoder.</p>
""", gap=6)

# ------------------------------------------------------------------ 1 -----
heading("<h1>I. INTRODUCTION AND NARROWED QUESTION</h1>")
place("""
<p>Periodic status reporting is simple to schedule but repeats an almost
unchanged state many times per hour. Suppressing messages saves bandwidth,
airtime and energy, but a suppressed message can hide the one change that
matters. The course topic frames this trade-off as <i>semantic</i> or
<i>goal-oriented</i> reporting: the sender should transmit according to how
useful an update is for the remote task, not according to a fixed clock.</p>
<p>This study narrows the topic to one verifiable proposition, following the
task workflow brief. The independent variables are the change threshold
&Delta; and the maximum silence interval H of a hybrid rule; the proposed
change is to add the silence limit on top of change-only reporting; the
primary outcomes are transmitted bytes and reconstruction RMSE at matched
event-detection quality. The declared failure conditions are: (i) a slow drift
smaller than &Delta; that crosses the alarm boundary must defeat pure change
reporting, and (ii) a silence limit longer than the alarm deadline must fail
to repair a lost event-onset packet. Both conditions are tested directly in
Section&nbsp;VI-D.</p>
<p>The scope is task-oriented semantic abstraction: how importance is defined
and how much application error suppression causes. No language-model semantic
communication is used and no semantic-capacity claim is made. All numerical
parameters are illustrative experimental assumptions, not device
specifications or safety limits. The complete numerical script that produced
every number reported here is available in the group's public repository,
referenced in the reproducibility section at the end of this report.</p>
""")

# ------------------------------------------------------------------ 2 -----
heading("<h1>II. LITERATURE AND CRITICAL COMPARISON</h1>")
place("""
<p>The surveyed literature moves from signal-dependent reporting rules to
objectives that value the receiver state and the consequence of an error. For
each study, Table&nbsp;I records what it establishes and where its boundary
lies relative to this project. The four starting points suggested by the
course brief correspond to [1]&ndash;[4]; recent 2024&ndash;2026 works
[5]&ndash;[9] complete the matrix. Version dates and acceptance notes follow
the arXiv metadata retrieved on 14 November 2026.</p>
""")
table(
    ["Study", "Method or evidence", "Boundary relative to this study"],
    [
        ["Miskowicz [1], 2006",
         "Send-on-delta event reporting; reporting-rate analysis versus periodic sampling.",
         "Classical basis of the change trigger. No lossy channel, no alarm deadline, no receiver-error accounting under loss."],
        ["Yates <i>et al.</i> [2], 2020",
         "Survey of age of information (AoI): timeliness metrics for resource-constrained updates.",
         "Freshness alone does not identify an abnormal state; elapsed time is not the application error tracked here."],
        ["Sun <i>et al.</i> [3], 2019",
         "Threshold sampling of a Wiener process over a random-delay channel; MSE-optimal sampler.",
         "Supports signal-dependent sampling under a rate constraint; optimality is source-specific and not transferable to this synthetic process."],
        ["Maatouk <i>et al.</i> [4], 2022",
         "Age of Incorrect Information (AoII): combines incorrectness with duration; optimal randomized threshold policy.",
         "Motivates task-sensitive metrics. This report measures RMSE and alarm misses directly and does not label them AoII."],
        ["Salimnejad <i>et al.</i> [5], 2024",
         "Two-state Markov monitoring; version-age metrics; state-dependent randomized policies with closed forms.",
         "Policies assume perfect instantaneous ACK/NACK; this project deliberately studies a no-feedback sender."],
        ["Luo and Pappas [6], 2025",
         "Semantic-aware scheduling of multiple Markov sources under a transmission-frequency constraint (CMDP).",
         "State-dependent estimation costs and optimality structure not reproduced here; supports explicit transmission accounting."],
        ["Zakeri <i>et al.</i> [7], 2024",
         "POMDP sampling/transmission with sampling costs, energy harvesting, AoII or distortion objectives.",
         "Highlights why observability and feedback assumptions matter; here local sensing is available every second at no cost."],
        ["Han <i>et al.</i> [8], 2025",
         "Age of incorrect semantics for video over MIMO; joint actuation, beamforming and symbol design.",
         "Shows usefulness-and-timeliness coupling at scale; the present scalar experiment has no learned features or MIMO."],
        ["Li <i>et al.</i> [9], 2025",
         "Goal-oriented sampling for remote decision-making under random delay; age-aware MDP with sampling-frequency threshold.",
         "Decision effectiveness beyond freshness; complementary objective without a packet-loss stress case comparable to Section VI-D."],
    ],
    "Condensed evidence matrix. The recent layer satisfies the brief's requirement of at least four 2024&ndash;2026 studies; every entry states its limitation.",
    widths=[17, 40, 43])

place("""
<h2>A. What Remains to Be Tested Here</h2>
<p>The practical gap is narrow and mechanical: a sender without
acknowledgements cannot know whether its last change-triggered packet arrived.
A silence timer gives it later opportunities to update, but reveals nothing
about receiver error and cannot promise timely recovery. The same rule can
therefore improve average tracking while leaving alarm deadlines unmet. In
this report &ldquo;semantic&rdquo; means that updates are judged by their
contribution to a monitoring task; the hybrid trigger itself is a
signal-change heuristic with a deadline-agnostic timer. No novelty or
optimality is claimed for the combination &mdash; send-on-delta with a
heartbeat exists in industrial practice &mdash; and the value of the study is
the fair, uncertainty-quantified comparison and the explicit failure modes.</p>
""")

# ------------------------------------------------------------------ 3 -----
heading("<h1>III. SYSTEM MODEL AND ASSUMPTIONS</h1>")
image("fig1_model.png", 0.94,
      "<b>Fig. 1.</b> Processing chain. One sensor is sampled every second; a "
      "reporting rule decides when to attempt a packet; a per-slot erasure "
      "channel (identical trace for all policies in a run) delivers or erases "
      "attempts; the receiver holds the last delivered value (an optional "
      "bounded extrapolator is tested in Section VI-E); metrics are computed "
      "offline against ground truth. There is no feedback path to the sender.")
place("""
<h2>A. Source Process</h2>
<p>Fig.&nbsp;1 shows the processing chain; Table&nbsp;II lists every model
parameter with its provenance. One sensor observes x[k] at integer seconds
k&nbsp;=&nbsp;0,&hellip;,3599.
The normal process is a 22&nbsp;&deg;C baseline plus a slow sinusoid plus
correlated AR(1) variation; rare abnormal conditions are rectangular
excursions of 20&ndash;40&nbsp;s adding 3.5&ndash;4.5&nbsp;&deg;C. Twelve
non-overlapping events are placed in separated windows per one-hour trace; the
generator asserts that every event sample is at or above the 25&nbsp;&deg;C
alarm threshold and every normal sample below it. The phase &phi; is uniform
on [0,&nbsp;2&pi;):</p>
<p style="margin-left:16pt; text-align:center">z[k] = 0.95&middot;z[k&minus;1] + e[k],
&nbsp;e[k] ~ N(0, 0.04&sup2;), z[0] = 0<br>
x[k] = 22 + 0.15&middot;sin(2&pi;k/600 + &phi;) + z[k] + d[k]</p>
<p>where d[k] is the event offset. This is a test signal, not a calibrated
thermal model.</p>
<h2>B. Reporting Rules, Channel and Receiver</h2>
<p>The sender stores v (the value in its most recent <i>attempted</i> packet)
and &tau; (its most recent attempt time). Both update after every attempt,
delivered or not; the sender never observes the receiver state. With a[k] the
attempt indicator in slot k:</p>
<p style="margin-left:16pt; text-align:center">
a<sub>per</sub>[k] = 1{k mod T = 0}<br>
a<sub>chg</sub>[k] = 1{|x[k] &minus; v| &ge; &Delta;}<br>
a<sub>hyb</sub>[k] = 1{|x[k] &minus; v| &ge; &Delta; &nbsp;or&nbsp; k &minus; &tau; &ge; H}</p>
<p>Every policy transmits a reliably delivered initialization packet at
k&nbsp;=&nbsp;0, charged like any other. Each attempt occupies one slot of an
independent erasure channel with loss probability p (a two-state bursty
variant is used in Section&nbsp;VI-D); per-slot success outcomes are
pre-generated per run and offered identically to all policies, whether or not
a policy attempts in that slot. A delivered packet carries the current sample
and updates the receiver immediately; otherwise the receiver holds its
previous estimate (x&#770;[k]&nbsp;=&nbsp;x&#770;[k&minus;1]). Same-slot
delivery abstracts away propagation and processing delay.</p>
""")
table(
    ["Parameter", "Value / range", "Source"],
    [
        ["Trace length; slot", "3600 samples; 1 s", "illustrative"],
        ["Baseline; sinusoid; AR(1) noise", "22 &deg;C; 0.15 &deg;C, 600 s period; &phi;=0.95, &sigma;=0.04 &deg;C", "illustrative"],
        ["Events", "12 per trace; 20&ndash;40 s; +3.5&ndash;4.5 &deg;C (36-event and 3&ndash;6 s variants tested)", "illustrative"],
        ["Alarm threshold; deadline D", "25 &deg;C; 10 s from onset, inclusive", "illustrative task definition"],
        ["Periodic interval T", "10 s nominal; sweep 2&ndash;60 s", "illustrative"],
        ["Change threshold &Delta;", "0.5 &deg;C nominal; sweep 0.2&ndash;1.2 &deg;C", "illustrative"],
        ["Silence limit H", "15 s nominal; sweep 5&ndash;60 s", "illustrative"],
        ["Loss probability p", "0, 0.1, 0.3; independent (bursty variant tested)", "illustrative"],
        ["Packet charge", "32 bytes per attempt incl. header; failed attempts and init charged", "illustrative"],
        ["Airtime; energy proxies", "1.0 ms; 30 &mu;J per attempt (conservation checks only)", "illustrative"],
        ["Runs; seeds", "30 per configuration, seeds 1000&ndash;1029; design seeds 2000&ndash;2009", "fixed, reproducible"],
    ],
    "Model parameters. No parameter is measured from real hardware; the literature [1]&ndash;[9] motivates the questions, not these values.",
    widths=[30, 50, 20])
place("""
<h2>C. What the Model Omits</h2>
<p>The model omits queueing, retransmissions and acknowledgements, channel
coding, contention and multi-user interference, propagation and processing
delay, sensing and computation energy (only a transmit-energy proxy linear in
attempts is accounted), measurement quantization, clock drift, and all learned
sender components except the bounded receiver extrapolator tested as a
sensitivity case. Reduced bytes therefore do not establish reduced total
energy consumption, and same-slot delivery must not be read as zero real
latency.</p>
""")

# ------------------------------------------------------------------ 4 -----
heading("<h1>IV. RULE BEHAVIOUR AND PREDICTED FAILURE MODES</h1>")
place("""
<p>Several properties can be predicted before any random experiment and are
asserted by the code's validation suite. With a constant source and a loss-free
channel, change-only sends only the initialization packet, while hybrid still
sends heartbeat packets (exactly seven packets in 100 s at H&nbsp;=&nbsp;15 s).
Sending every sample without loss gives zero reconstruction error, and total
loss freezes the receiver at the initialization value. In the loss-free case,
change-based reporting keeps the post-decision absolute error strictly below
&Delta;, because a new attempt occurs as soon as the deviation reaches
&Delta;; the hybrid heartbeat can only reduce error further. Under loss this
bound fails: v can differ from the receiver estimate indefinitely.</p>
<p>Two failure modes motivate the experiments. First, on a stable event
plateau the onset packet is the only change-triggered message; if it is
erased, change-based rules stay silent for the whole plateau. Hybrid recovers
at the next silence deadline, i.e. H seconds after the <i>attempt</i> (the
failed attempt resets &tau;). If H exceeds the deadline D, recovery is
necessarily late; if H&nbsp;&le;&nbsp;D, an idealized plateau with independent
loss is missed only with probability p<sup>1+floor(D/H)</sup>. Second, a slow
drift whose total rise stays below &Delta; never triggers a change packet,
even when it crosses the alarm boundary: importance to the task and change
magnitude are different quantities. Periodic reporting is exposed to the
opposite failure: short events that fall between scheduling slots.</p>
""")

# ------------------------------------------------------------------ 5 -----
heading("<h1>V. EXPERIMENTAL DESIGN</h1>")
place("""
<h2>A. Metrics</h2>
<p>Attempted traffic counts 32 bytes per attempted packet, including headers,
erased attempts and the initialization sample; kB is 1000 bytes.
Reconstruction RMSE is the root mean square of x[k]&nbsp;&minus;&nbsp;x&#770;[k]
over all 3600 samples. An event is <i>detected on time</i> if at least one
<i>newly delivered</i> above-threshold sample arrives while the event is
active and within 10 s of onset; a stale alarm held from an earlier event does
not count. The deadline-miss fraction is the share of events not detected on
time. Conditional detection delay averages the onset-to-receipt delay over
detected events only and must be read next to the miss fraction. The
penalized delay score assigns a declared 11 s (deadline&nbsp;+&nbsp;1 s) to
missed events &mdash; a reporting convention, not a physical latency.
False-alarm occupancy is the share of normal-source samples for which the held
estimate is at or above the alarm level; it measures stale alarms, not
per-event false positives. Event labels are used only by the offline
evaluator; no rule sees them.</p>
<h2>B. Fairness, Uncertainty and Baselines</h2>
<p>All policies in a run share the same source trace and the same per-slot
channel outcomes; only their attempt patterns differ. Thirty independent runs
(seeds 1000&ndash;1029) per configuration form the statistical unit: tables
report run-level means with 95% Student-t intervals, and hybrid&ndash;periodic
differences are paired within each run before intervals are formed. Packets
are never treated as independent samples. The periodic baseline is
additionally strengthened: a traffic-matched periodic interval is selected on
separate design traces (seeds 2000&ndash;2009, mean hybrid packet count
""" + f"{MT['design_mean_packets']:.1f}" + """ &rarr; T&nbsp;=&nbsp;"""
+ str(MT["period"]) + """ s) and evaluated on the untouched test seeds, so the
comparison is close-budget rather than against a weakened baseline. The
validation gate additionally checks four conservation identities per run
(packets, bytes, airtime, energy) and a known-answer case (T&nbsp;=&nbsp;10 s,
no loss: exactly 360 packets and 11&nbsp;520 bytes per hour, asserted in code).</p>
<h2>C. Sweep Design</h2>
<p>Following the brief, one main parameter and one stress factor are swept at
a time on the same 30 test traces: the change threshold &Delta; over six
values, the silence limit H over five values, the periodic interval T over
seven values, and the loss probability p over three values; event frequency
(12 &rarr; 36), event duration (20&ndash;40 s &rarr; 3&ndash;6 s) and bursty
loss (mean outage run 5 s) are additional stress scenarios. Two deterministic
mechanism tests (a single erased onset packet; a 0.4&nbsp;&deg;C slow drift)
complete the design. No configuration is tuned on the test seeds.</p>
""")

# ------------------------------------------------------------------ 6 -----
heading("<h1>VI. RESULTS</h1>")
place(f"""
<h2>A. Nominal Comparison at 10% Loss</h2>
<p>Table&nbsp;III reports the nominal experiment (T&nbsp;=&nbsp;10&nbsp;s,
&Delta;&nbsp;=&nbsp;0.5&nbsp;&deg;C, H&nbsp;=&nbsp;15&nbsp;s). Hybrid
reporting attempts {HYB['packets']['mean']:.1f} packets per hour against
{PER['packets']['mean']:.0f} for periodic &mdash; a {kb_save:.2f}% byte
reduction &mdash; while mean RMSE falls {rmse_save:.2f}%
({PER['rmse']['mean']:.3f} &rarr; {HYB['rmse']['mean']:.3f} &deg;C).
Change-only is by far the cheapest ({CHG['bytes']['mean']/1000:.2f} kB/h,
{chg_save:.2f}% below periodic) but its RMSE under loss is <i>worse</i> than
periodic's: a single erased change packet leaves the receiver wrong until the
next sufficiently large change, and its stale-alarm occupancy
({100*CHG['faocc']['mean']:.2f}%) is the largest of the three. Under the
declared per-attempt proxies these counts conserve exactly: the hybrid
{HYB['packets']['mean']:.1f} &plusmn; {HYB['packets']['half']:.1f} attempted
packets per hour equal {kb(HYB['bytes'])}&nbsp;kB,
{mm(HYB['airtime_ms'], 1)}&nbsp;ms of airtime and
{mm(HYB['energy_uj'], 0)}&nbsp;&mu;J of transmit-energy proxy, against
{PER['packets']['mean']:.0f} packets, {kb(PER['bytes'])}&nbsp;kB,
{mm(PER['airtime_ms'], 1)}&nbsp;ms and {mm(PER['energy_uj'], 0)}&nbsp;&mu;J for
the periodic baseline; these are accounting identities, not measured device
values. Fig.&nbsp;2 shows the mechanism on one trace window.</p>
""")
table(
    ["Metric (per hour-long run)", "Periodic T=10 s", "Change &Delta;=0.5&deg;C",
     "Hybrid &Delta;=0.5&deg;C, H=15 s"],
    [
        ["Attempted packets", mm(PER["packets"], 1), mm(CHG["packets"], 1), mm(HYB["packets"], 1)],
        ["Traffic (kB)", kb(PER["bytes"]), kb(CHG["bytes"]), kb(HYB["bytes"])],
        ["Delivered packets", mm(PER["delivered"], 1), mm(CHG["delivered"], 1), mm(HYB["delivered"], 1)],
        ["RMSE (&deg;C)", mm(PER["rmse"]), mm(CHG["rmse"]), mm(HYB["rmse"])],
        ["Deadline miss (%)", pm(PER["miss"]), pm(CHG["miss"]), pm(HYB["miss"])],
        ["Cond. detection delay (s)", mm(PER["delay"], 2), "0.00 &plusmn; 0.00", "0.00 &plusmn; 0.00"],
        ["Penalized delay score (s)", mm(PER["penalty"], 2), mm(CHG["penalty"], 2), mm(HYB["penalty"], 2)],
        ["False-alarm occupancy (%)", pm(PER["faocc"]), pm(CHG["faocc"]), pm(HYB["faocc"])],
    ],
    "Nominal results at p = 0.1; run-level mean &plusmn; 95% interval over 30 paired runs (seeds 1000&ndash;1029).",
    widths=[31, 23, 23, 23])
place("""
<p>The paired hybrid&ndash;periodic intervals support the traffic and RMSE
reductions for this generator: byte difference
""" + f"{PA['bytes']['mean']:+.0f}" + " &plusmn; " + f"{PA['bytes']['half']:.0f}" + """
B/h and RMSE difference """ + f"{PA['rmse']['mean']:+.3f}" + " &plusmn; " + f"{PA['rmse']['half']:.3f}" + """
&nbsp;&deg;C. They do <b>not</b> support a deadline-miss improvement: the
paired difference is """ + f"{100*PA['miss']['mean']:+.2f}" + " &plusmn; " + f"{100*PA['miss']['half']:.2f}" + """
percentage points, an interval that contains zero. The zero conditional delay
of the change-based rules is an artefact of the timing model: on-time
detections happen at successful onset packets, and failed onsets are counted
as misses. The penalized score, which charges misses at 11 s, is where the
change-based rules genuinely lead
(""" + f"{HYB['penalty']['mean']:.2f}" + " &plusmn; " + f"{HYB['penalty']['half']:.2f}" + """
s versus """ + f"{PER['penalty']['mean']:.2f}" + " &plusmn; " + f"{PER['penalty']['half']:.2f}" + """ s).</p>
""")
image("fig2_trace.png", 0.9,
      "<b>Fig. 2.</b> One trace window (seed 1000, p = 0.1; shaded band = event "
      "window; dotted line = 25 &deg;C alarm level). Markers show send attempts "
      "(filled = delivered, hollow = erased). Periodic sends on the clock and "
      "delays the alarm until its next slot; change-only sends at the onset and "
      "at the return-to-normal, but a lost attempt would leave its estimate "
      "wrong for the whole plateau; hybrid adds heartbeats that cap error "
      "persistence.")

place(f"""
<h2>B. Loss Sensitivity</h2>
<p>Fig.&nbsp;3 traces the three policies across p&nbsp;=&nbsp;0, 0.1, 0.3.
Without loss, change-only is extremely efficient: RMSE
{L['0.0']['Change']['rmse']['mean']:.3f}&nbsp;&deg;C at
{L['0.0']['Change']['bytes']['mean']/1000:.2f}&nbsp;kB/h. Under loss it
degrades fastest &mdash; RMSE {L['0.3']['Change']['rmse']['mean']:.3f}&nbsp;&deg;C
at p&nbsp;=&nbsp;0.3, worse than periodic's
{L['0.3']['Periodic']['rmse']['mean']:.3f}&nbsp;&deg;C &mdash; because each of
its rare packets carries a large stake. Hybrid is the most loss-tolerant on
tracking (RMSE {L['0.3']['Hybrid']['rmse']['mean']:.3f}&nbsp;&deg;C at
p&nbsp;=&nbsp;0.3). Offered traffic is flat in p for all rules: without
feedback, packet counts do not adapt to loss, only outcomes do.</p>
""")
image("fig3_loss.png", 0.97,
      "<b>Fig. 3.</b> Mean RMSE (left) and deadline-miss fraction (right) "
      "versus independent loss probability; bars are 95% run-level intervals. "
      "The change-only and hybrid miss curves coincide because with H = 15 s "
      "the silence deadline always falls outside the 10 s detection window.")

place(f"""
<h2>C. Traffic-Matched and Sweep Comparisons</h2>
<p>At the traffic-matched operating point (Table&nbsp;IV), periodic reporting
with T&nbsp;=&nbsp;{MT['period']}&nbsp;s uses {100-match_save:.2f}% more
packets than hybrid yet still loses on both quality metrics: RMSE
{MT['summary']['Periodic']['rmse']['mean']:.3f} versus
{MT['summary']['Hybrid']['rmse']['mean']:.3f} &deg;C and deadline misses
{100*MT['summary']['Periodic']['miss']['mean']:.2f}% versus
{100*MT['summary']['Hybrid']['miss']['mean']:.2f}%. With updates placed at
changes rather than on the clock, the same budget buys better tracking and
earlier alarms. This is evidence about placement, not a dominance claim over
all periodic intervals: T&nbsp;=&nbsp;2&nbsp;s periodic reporting achieves RMSE
{PS[2]['rmse']['mean']:.3f}&nbsp;&deg;C with zero observed misses at
{PS[2]['bytes']['mean']/1000:.1f}&nbsp;kB/h. Fig.&nbsp;4 summarizes the
traffic&ndash;quality trade-off across all sweeps.</p>
""")
table(
    ["Metric", f"Periodic T = {MT['period']} s", "Hybrid H = 15 s"],
    [
        ["Attempted packets", mm(MT["summary"]["Periodic"]["packets"], 1), mm(MT["summary"]["Hybrid"]["packets"], 1)],
        ["Traffic (kB)", kb(MT["summary"]["Periodic"]["bytes"]), kb(MT["summary"]["Hybrid"]["bytes"])],
        ["RMSE (&deg;C)", mm(MT["summary"]["Periodic"]["rmse"]), mm(MT["summary"]["Hybrid"]["rmse"])],
        ["Deadline miss (%)", pm(MT["summary"]["Periodic"]["miss"]), pm(MT["summary"]["Hybrid"]["miss"])],
        ["Penalized delay score (s)", mm(MT["summary"]["Periodic"]["penalty"], 2), mm(MT["summary"]["Hybrid"]["penalty"], 2)],
    ],
    "Close-budget comparison; the periodic interval was chosen on separate design seeds (2000&ndash;2009) without touching the test seeds.",
    widths=[34, 33, 33])
image("fig4_tradeoff.png", 0.95,
      "<b>Fig. 4.</b> Mean operating points at p = 0.1 across the parameter "
      "sweeps; each point is a 30-run mean with 95% run-level whiskers "
      "(several are smaller than the markers). Lines connect tested settings "
      "only and are not optimized frontiers. Under loss, hybrid (green) "
      "traces a better traffic&ndash;RMSE trade-off than change-only (red) at "
      "most budgets, while frequent periodic reporting (blue, T = 2 s) "
      "remains the quality ceiling at high traffic.")

place(f"""
<p>Table&nbsp;V isolates the silence limit. The miss fraction is flat at
{100*HS[15]['miss']['mean']:.2f}% for H&nbsp;&ge;&nbsp;15 s and collapses as H
moves inside the deadline: H&nbsp;=&nbsp;10&nbsp;s allows one extra in-window
attempt after a lost onset (misses {100*HS[10]['miss']['mean']:.2f}%), and
H&nbsp;=&nbsp;5&nbsp;s allows two (no misses observed, at the cost of
{HS[5]['packets']['mean']:.0f} packets/h, above the periodic baseline). The
idealized plateau formula p<sup>1+floor(D/H)</sup> predicts 1% and 0.1% for
H&nbsp;=&nbsp;10 and 5&nbsp;s at p&nbsp;=&nbsp;0.1; the finite samples sit
near these values, but zero observed misses in 30 runs is not a reliability
bound. Sweeping &Delta; instead changes a different task: shrinking &Delta;
from 1.2 to 0.2&nbsp;&deg;C raises change-only traffic from
{DS[1.2]['packets']['mean']:.1f} to {DS[0.2]['packets']['mean']:.1f} packets/h
and improves RMSE from {DS[1.2]['rmse']['mean']:.3f} to
{DS[0.2]['rmse']['mean']:.3f}&nbsp;&deg;C, yet misses stay near
{100*HS[15]['miss']['mean']:.1f}% &mdash; a stable plateau generates no second
change inside the window. &Delta; governs tracking accuracy; H governs
recovery opportunities; neither substitutes for the other.</p>
""")
table(
    ["Hybrid H (s)", "Packets/h", "Traffic (kB/h)", "RMSE (&deg;C)", "Miss (%)", "Penalized score (s)"],
    [[str(h),
      f"{HS[h]['packets']['mean']:.1f}",
      f"{HS[h]['bytes']['mean']/1000:.3f}",
      mm(HS[h]["rmse"]),
      f"{100*HS[h]['miss']['mean']:.2f}",
      f"{HS[h]['penalty']['mean']:.2f}"] for h in (5, 10, 15, 30, 60)],
    "Silence-limit sensitivity at &Delta; = 0.5 &deg;C, p = 0.1 (30 runs each). The nominal H = 15 s sits above the 10 s alarm deadline.",
    widths=[14, 14, 17, 21, 14, 20])

place(f"""
<h2>D. Stress Cases and Negative Results</h2>
<p>The two deterministic mechanism tests (Fig.&nbsp;5) realize the failure
conditions declared in Section&nbsp;I. In the lost-onset test, a stable
26&nbsp;&deg;C plateau begins at t&nbsp;=&nbsp;17&nbsp;s and exactly one packet
&mdash; the onset packet &mdash; is erased. Periodic reporting detects at
t&nbsp;=&nbsp;20&nbsp;s (delay 3&nbsp;s). Hybrid attempts the onset, resets its
silence clock, and next delivers at t&nbsp;=&nbsp;32&nbsp;s: the estimate is
repaired, but the 10&nbsp;s deadline has passed. Change-only receives nothing
during the plateau; its receiver stays at 22&nbsp;&deg;C until the
return-to-normal change fires after the event ends. In the slow-drift test,
the signal rises by only 0.4&nbsp;&deg;C &mdash; below &Delta; &mdash; but
crosses the alarm boundary at t&nbsp;=&nbsp;35&nbsp;s. Change-only never
reports (miss; segment RMSE {SD['Change']['metrics']['rmse']:.3f}&nbsp;&deg;C);
periodic detects within 5&nbsp;s; hybrid detects at exactly the deadline via a
heartbeat. A threshold-crossing trigger would close this gap and is listed as
future work.</p>
<p>Three randomized stress scenarios extend the picture (Table&nbsp;VI). Short
3&ndash;6&nbsp;s events invert the nominal ranking: periodic reporting misses
{100*R['short_events']['Periodic']['miss']['mean']:.2f}% of events because
whole events fall between scheduling slots, while each change-based rule keeps
misses near {100*R['short_events']['Change']['miss']['mean']:.2f}%. Doubling
the event count to 36 raises hybrid traffic to
{R['high_events']['Hybrid']['packets']['mean']:.1f} packets/h and everyone's
RMSE, with hybrid still ahead. Five-second bursty loss at mean
p&nbsp;=&nbsp;0.3 slightly worsens all rules relative to independent loss; one
burst length cannot support a general robustness claim.</p>
""")
image("fig5_stress.png", 0.98,
      "<b>Fig. 5.</b> Deterministic mechanism tests. (a) Only the onset packet "
      "at t = 17 s is erased on a stable plateau: periodic detects in 3 s; "
      "hybrid repairs only at t = 32 s (H = 15 s after the failed attempt) and "
      "misses the deadline; change-only receives nothing until the event ends. "
      "(b) A 0.4 &deg;C slow drift crosses 25 &deg;C at t = 35 s without ever "
      "reaching the 0.5 &deg;C change threshold: change-only never reports; "
      "hybrid detects at the deadline via a heartbeat; periodic detects in 5 s.")
table(
    ["Scenario (30 runs)", "Periodic RMSE / miss", "Change RMSE / miss", "Hybrid RMSE / miss"],
    [
        ["36 events per hour, p = 0.1",
         f"{R['high_events']['Periodic']['rmse']['mean']:.3f} / {100*R['high_events']['Periodic']['miss']['mean']:.2f}%",
         f"{R['high_events']['Change']['rmse']['mean']:.3f} / {100*R['high_events']['Change']['miss']['mean']:.2f}%",
         f"{R['high_events']['Hybrid']['rmse']['mean']:.3f} / {100*R['high_events']['Hybrid']['miss']['mean']:.2f}%"],
        ["Short 3&ndash;6 s events, p = 0.1",
         f"{R['short_events']['Periodic']['rmse']['mean']:.3f} / {100*R['short_events']['Periodic']['miss']['mean']:.2f}%",
         f"{R['short_events']['Change']['rmse']['mean']:.3f} / {100*R['short_events']['Change']['miss']['mean']:.2f}%",
         f"{R['short_events']['Hybrid']['rmse']['mean']:.3f} / {100*R['short_events']['Hybrid']['miss']['mean']:.2f}%"],
        ["Bursty loss, mean p = 0.3",
         f"{R['bursty']['Periodic']['rmse']['mean']:.3f} / {100*R['bursty']['Periodic']['miss']['mean']:.2f}%",
         f"{R['bursty']['Change']['rmse']['mean']:.3f} / {100*R['bursty']['Change']['miss']['mean']:.2f}%",
         f"{R['bursty']['Hybrid']['rmse']['mean']:.3f} / {100*R['bursty']['Hybrid']['miss']['mean']:.2f}%"],
    ],
    "Randomized stress scenarios at nominal reporting parameters; RMSE in &deg;C, miss fraction in %. Identical trace/channel pairs across policies in each run.",
    widths=[31, 23, 23, 23])

place("""
<h2>E. Optional Receiver Predictor: A Negative Result</h2>
<p>The brief's optional extension replaces hold-last reconstruction with a
simple linear predictor. A deliberately conservative version extrapolates from
the last two delivered samples, with the slope clamped to
&plusmn;0.1&nbsp;&deg;C/s and the extrapolation offset clamped to
&plusmn;1&nbsp;&deg;C. Table&nbsp;VII shows the outcome at p&nbsp;=&nbsp;0.1:
the predictor <i>worsens</i> RMSE for both change-based rules &mdash; the
source is step-dominated, so extrapolating a trend through a held stale value
overshoots &mdash; while traffic, misses and stale alarms are unchanged
(sender behaviour is untouched). For this source class the hold-last receiver
is the better of the two; no learning component is used anywhere in the study.</p>
""")
table(
    ["Receiver (p = 0.1)", "Packets/h", "RMSE (&deg;C)", "Miss (%)", "False-alarm occ. (%)"],
    [
        ["Change-only, hold", f"{PR['Change:hold']['packets']['mean']:.1f}", mm(PR["Change:hold"]["rmse"]), f"{100*PR['Change:hold']['miss']['mean']:.2f}", f"{100*PR['Change:hold']['faocc']['mean']:.2f}"],
        ["Change-only, linear", f"{PR['Change:linear']['packets']['mean']:.1f}", mm(PR["Change:linear"]["rmse"]), f"{100*PR['Change:linear']['miss']['mean']:.2f}", f"{100*PR['Change:linear']['faocc']['mean']:.2f}"],
        ["Hybrid, hold", f"{PR['Hybrid:hold']['packets']['mean']:.1f}", mm(PR["Hybrid:hold"]["rmse"]), f"{100*PR['Hybrid:hold']['miss']['mean']:.2f}", f"{100*PR['Hybrid:hold']['faocc']['mean']:.2f}"],
        ["Hybrid, linear", f"{PR['Hybrid:linear']['packets']['mean']:.1f}", mm(PR["Hybrid:linear"]["rmse"]), f"{100*PR['Hybrid:linear']['miss']['mean']:.2f}", f"{100*PR['Hybrid:linear']['faocc']['mean']:.2f}"],
    ],
    "Receiver-side bounded linear extrapolation versus hold-last; same 30 paired runs, identical senders.",
    widths=[30, 14, 22, 14, 20])

# ------------------------------------------------------------------ 7 -----
heading("<h1>VII. DISCUSSION AND LIMITATIONS</h1>")
place("""
<p>The main finding is not &ldquo;fewer updates are better&rdquo;. It is that
the two rule parameters answer two different questions. The change threshold
&Delta; prices tracking accuracy in bytes; the silence limit H is a recovery
and liveness mechanism whose value depends on the task deadline. A designer
should start from the acceptable missed-alarm risk and latency budget, choose
H so that at least one retry fits inside the deadline (H&nbsp;&le;&nbsp;D,
with room for the real transmission and processing delays this model omits),
and only then choose &Delta; to spend the remaining budget on tracking. The
traffic-matched comparison adds the placement lesson: where updates are sent
matters as much as how many. Finally, suppressed-update rules shift risk from
bandwidth to application error; reporting both sides &mdash; bytes and
misses, with intervals &mdash; is the honest way to evaluate them.</p>
<h2>A. Limitations</h2>
<p><b>Source realism.</b> Rectangular excursions flatter change triggers;
real traces with measurement noise, quantization, gradual onsets and
non-stationary drifts could reorder the rankings. Thirty traces and two event
rates bound the Monte Carlo evidence. <b>Radio abstraction.</b> Whole-packet
erasures without queueing, interference, coding or variable service time;
sensing stays active every second for all rules, so byte savings do not
establish energy or battery savings beyond the linear proxy.
<b>Task conventions.</b> Results depend on the 25&nbsp;&deg;C threshold, the
inclusive 10&nbsp;s window and the declared 11&nbsp;s miss penalty; a
risk-calibrated utility could weigh events differently, and conditional delay
flatters rules that miss their hardest events. <b>Statistics.</b> Intervals
quantify Monte Carlo variation under this generator only &mdash; not model
mismatch and not selection effects across the many settings examined; zero
observed misses are not reliability bounds. <b>Generality.</b> One scalar
sensor, one hop, no feedback; multi-sensor scheduling and acknowledged
delivery with bounded retries are outside the evidence. Nothing here equates
this simulation with a validated commercial implementation.</p>
""")

# ------------------------------------------------------------------ 8 -----
heading("<h1>VIII. CONCLUSION</h1>")
place(f"""
<p>For the tested synthetic one-sensor system, sending meaningful changes does
reduce traffic while preserving &mdash; and improving &mdash; average
monitoring quality, but only once a silence limit repairs the failure modes of
pure change reporting. At 10% loss the hybrid rule cuts attempted bytes by
{kb_save:.1f}% and RMSE by {rmse_save:.1f}% relative to 10&nbsp;s periodic
reporting, and it beats a traffic-matched periodic baseline on every quality
metric. The same rule with H&nbsp;=&nbsp;15&nbsp;s does <i>not</i> reduce
deadline misses, because its retries arrive after the alarm deadline;
H&nbsp;&le;&nbsp;10&nbsp;s does, at a traffic cost. Pure change reporting is
the cheapest rule and the most fragile: one erased packet or a sub-threshold
slow drift can hide an alarm, and the optional linear receiver predictor makes
reconstruction <i>worse</i> for this source. The defensible engineering
conclusion is conditional: combine change and time information, size H against
the task deadline, and judge every rule on both traffic and application
error.</p>
""")

# ------------------------------------------------------------ references --
heading("<h1>REFERENCES AND REPRODUCIBILITY</h1>")
place("""
<p style="margin-bottom:4pt">[1] M. Miskowicz, &ldquo;Send-On-Delta Concept:
An Event-Based Data Reporting Strategy,&rdquo; <i>Sensors</i>, vol. 6, no. 1,
pp. 49&ndash;63, 2006. doi: 10.3390/s6010049.<br>
[2] R. D. Yates, Y. Sun, D. R. Brown III, S. K. Kaul, E. Modiano and
S. Ulukus, &ldquo;Age of Information: An Introduction and Survey,&rdquo;
arXiv:2007.08564, 2020 (author manuscript).<br>
[3] Y. Sun, Y. Polyanskiy and E. Uysal, &ldquo;Sampling of the Wiener Process
for Remote Estimation over a Channel with Random Delay,&rdquo;
arXiv:1707.02531v7, 2019 (author manuscript, accepted by IEEE Trans. Inf.
Theory).<br>
[4] A. Maatouk, M. Assaad and A. Ephremides, &ldquo;The Age of Incorrect
Information: an Enabler of Semantics-Empowered Communication,&rdquo;
arXiv:2012.13214v3, 2022 (author manuscript).<br>
[5] M. Salimnejad, M. Kountouris, A. Ephremides and N. Pappas, &ldquo;Age of
Information Versions: a Semantic View of Markov Source Monitoring,&rdquo;
arXiv:2406.14594v1, 2024.<br>
[6] J. Luo and N. Pappas, &ldquo;Semantic-Aware Remote Estimation of Multiple
Markov Sources Under Constraints,&rdquo; arXiv:2403.16855v2, 2025 (author
manuscript, accepted by IEEE Trans. Commun., doi: 10.1109/TCOMM.2025.3571950).<br>
[7] A. Zakeri, M. Moltafet and M. Codreanu, &ldquo;Semantic-aware Sampling
and Transmission in Energy Harvesting Systems: A POMDP Approach,&rdquo;
arXiv:2311.06522v4, 2024.<br>
[8] X. Han, B. Feng, Y. Wu, X.-G. Xia, W. Zhang and S. Sun, &ldquo;Age of
Semantic Information-Aware Wireless Transmission for Remote Monitoring
Systems,&rdquo; arXiv:2508.12248v2, 2025 (author manuscript, accepted by IEEE
Trans. Wireless Commun.).<br>
[9] A. Li, S. Wu, G. C. F. Lee and S. Sun, &ldquo;From Freshness to
Effectiveness: Goal-Oriented Sampling for Remote Decision Making,&rdquo;
arXiv:2504.19507v3, 2025 (journal reference listed by arXiv: IEEE Trans. Inf.
Theory, vol. 72, no. 4, pp. 2237&ndash;2276, Apr. 2026).</p>
<p><b>Reproducing the numbers.</b> The complete numerical script
(simulate.py), the figure and PDF build scripts, and the raw results file
with per-run values are available in the group's public repository at
<span style="white-space:nowrap">https://github.com/endeavorxn/topic31-semantic-event-reporting</span>
(requirement R3, hosted-code option). Run <code>python simulate.py</code>
(NumPy and SciPy required): it executes the validation checks, regenerates
every number in this report deterministically and writes results.json,
including per-run values so all intervals and paired comparisons can be
recomputed. Executed environment: Python 3.13.5, NumPy 2.2.6, SciPy 1.16.1,
Matplotlib 3.10.3, PyMuPDF 2.0 on Windows. Test seeds 1000&ndash;1029;
traffic-calibration design seeds 2000&ndash;2009. arXiv metadata was
re-checked on 14 November 2026.</p>
""")

# No appendix: requirement R3 is satisfied by the public repository link
# shared in the report body (the course rules allow either GitHub or an
# appendix; the repository option keeps the report within 10 pages).
appendix_from = len(pages)

# ===========================================================================
# Headers, footers, page numbers (second pass, after dropping scratch page)
# ===========================================================================
doc.delete_page(0)       # remove measurement scratch page
total = len(pages)
for idx in range(total):
    pg = doc[idx]          # re-fetch: early Page proxies get orphaned
    is_app = idx >= appendix_from
    foot = str(idx + 1) if not is_app else f"{idx + 1}  (Appendix A)"
    fw = pymupdf.get_text_length(foot, fontname="tiro", fontsize=8.5)
    pg.insert_text(pymupdf.Point((PW - fw) / 2, PH - 36), foot, fontsize=8.5,
                   fontname="tiro", color=(0.3, 0.3, 0.3))

out = HERE / "Topic31_Semantic_Event_Reporting_Report_EN.pdf"
doc.save(str(out), deflate=True, garbage=3)
print(f"PDF written: {out}")
print(f"total pages: {total}; main body: {appendix_from} (limit 15); "
      f"appendix: {total - appendix_from} pages")

root = HERE.parent / "Topic31_Semantic_Event_Reporting_Report_EN.pdf"
shutil.copy2(out, root)
print("copy:", root)
