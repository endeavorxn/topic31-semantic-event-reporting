"""Topic 31 - Semantic Event Reporting for Remote Monitoring.

Reproducible numerical study: periodic vs change-only (send-on-delta) vs
hybrid (change threshold + maximum silence interval) reporting over a
packet-erasure link, with a hold-last-value receiver.

Run:  python simulate.py   ->  writes results.json next to this file.

All numerical parameters are illustrative experimental assumptions; none is
a measured device property or a safety limit.  Statistics are run-level:
one value per one-hour trace; 95% Student-t intervals; paired comparisons
use the same trace and channel realization within each run.

Group research report draft, 14 November 2026.
"""
import json
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t

# --------------------------------------------------------------------------
# Global settings (all illustrative)
# --------------------------------------------------------------------------
N = 3600                    # samples per trace, 1 s slots (one hour)
RUNS = 30                   # independent test runs per configuration
SEEDS = list(range(1000, 1000 + RUNS))          # 1000-1029
DESIGN_SEEDS = list(range(2000, 2010))          # 2000-2009, calibration only
PKT_BYTES = 32.0           # bytes charged per attempted packet, incl. header
AIRTIME_MS = 1.0           # illustrative airtime per attempt (ms)
ENERGY_UJ = 30.0           # illustrative transmit energy per attempt (uJ)
ALARM = 25.0               # alarm threshold (degrees C)
DEADLINE = 10              # detection deadline from onset, inclusive (s)
DELTA0 = 0.5               # nominal change threshold (degrees C)
H0 = 15                    # nominal maximum silence interval (s)
T0 = 10                    # nominal periodic interval (s)


# --------------------------------------------------------------------------
# Source process and channel (Section 3 of the report)
# --------------------------------------------------------------------------
def make_trace(seed, n_events=12, short=False):
    """One-hour temperature-like trace with separated rectangular events.

    x[k] = 22 + 0.15 sin(2 pi k/600 + phase) + z[k] + event[k],
    z = AR(1) with phi = 0.95, innovations N(0, 0.04^2).
    Returns (x, spans) where spans is a list of (start, end) event windows.
    """
    rng = np.random.default_rng(seed)
    z = np.zeros(N)
    innov = rng.normal(0.0, 0.04, N)
    for k in range(1, N):
        z[k] = 0.95 * z[k - 1] + innov[k]
    phase = rng.uniform(0.0, 2.0 * np.pi)
    x = 22.0 + 0.15 * np.sin(2.0 * np.pi * np.arange(N) / 600.0 + phase) + z

    spans = []
    width = (N - 120) // n_events
    for j in range(n_events):
        start = 60 + j * width + int(rng.integers(0, width - 45))
        duration = int(rng.integers(3, 7) if short else rng.integers(20, 41))
        end = start + duration
        x[start:end] += rng.uniform(3.5, 4.5)
        spans.append((start, end))

    # Sanity of the generator itself: events are above the alarm threshold,
    # non-event samples below it, and event windows never overlap.
    mask = np.zeros(N, dtype=bool)
    for a, b in spans:
        assert np.all(x[a:b] >= ALARM), "event below alarm threshold"
        mask[a:b] = True
    assert np.all(x[~mask] < ALARM), "non-event above alarm threshold"
    for (a1, b1), (a2, b2) in zip(spans, spans[1:]):
        assert a2 >= b1, "overlapping events"
    return x, spans


def make_channel(seed, p, burst=False, n=N):
    """Per-slot delivery outcomes, shared by every policy in a run.

    Independent erasure with probability p, or a stationary two-state outage
    process with the same mean loss p (mean bad run 5 s when burst=True).
    """
    rng = np.random.default_rng(seed + 100000)
    u = rng.random(n + 1)
    if not burst:
        good = u[:n] >= p
        return good
    q_bg = 0.2                       # bad -> good
    q_gb = p * q_bg / (1.0 - p)      # good -> bad, stationary loss = p
    good = np.empty(n, dtype=bool)
    bad = bool(u[0] < p)
    for k in range(n):
        good[k] = not bad
        if bad:
            bad = (u[k + 1] >= q_bg)     # stays bad with prob 0.8
        else:
            bad = (u[k + 1] < q_gb)
    return good


# --------------------------------------------------------------------------
# Reporting policies and receiver (Sections 3-4 of the report)
# --------------------------------------------------------------------------
def run_policy(x, good, spans, policy, period=T0, delta=DELTA0, h=H0,
               receiver="hold"):
    """Simulate one policy on one trace/channel pair.

    policy: 'Periodic' | 'Change' | 'Hybrid'
    receiver: 'hold' (last delivered value) | 'linear' (bounded extrapolation)

    The sender knows only its own local samples and its own last attempt.
    There is no feedback: v and tau are updated after every ATTEMPT, whether
    or not the packet is delivered.
    """
    n = len(x)
    sent = np.zeros(n, dtype=bool)
    received = np.zeros(n, dtype=bool)
    estimate = np.empty(n)

    # Common reliable initialization at k = 0, charged like any packet.
    sent[0] = received[0] = True
    estimate[0] = x[0]
    last_value = x[0]     # value in the sender's last attempted packet
    last_time = 0         # time of the sender's last attempt
    # Anchors for the optional linear receiver predictor.
    t1, v1 = 0, x[0]      # second-to-last delivery
    t2, v2 = 0, x[0]      # last delivery

    def extrapolate(k):
        if receiver == "hold" or t1 == t2:
            return v2
        slope = (v2 - v1) / (t2 - t1)
        slope = float(np.clip(slope, -0.1, 0.1))     # degrees C per s
        off = float(np.clip(slope * (k - t2), -1.0, 1.0))  # bounded offset
        return v2 + off

    for k in range(1, n):
        changed = abs(x[k] - last_value) >= delta
        if policy == "Periodic":
            due = (k % period == 0)
        elif policy == "Change":
            due = changed
        elif policy == "Hybrid":
            due = changed or (k - last_time >= h)
        else:
            raise ValueError(policy)

        estimate[k] = extrapolate(k)
        if due:
            sent[k] = True
            last_value, last_time = x[k], k
            if good[k]:
                received[k] = True
                estimate[k] = x[k]
                t1, v1 = t2, v2
                t2, v2 = k, x[k]

    # ---------------- metrics over the whole run ----------------
    err = x - estimate
    delays, scores = [], []
    for start, end in spans:
        stop = min(end, start + DEADLINE + 1)   # inclusive 10 s window
        # A detection needs a NEW delivered above-alarm sample in the window;
        # a stale alarm held from an earlier event does not count.
        hits = np.flatnonzero(received[start:stop] & (x[start:stop] >= ALARM))
        if len(hits):
            delays.append(float(hits[0]))
            scores.append(float(hits[0]))
        else:
            scores.append(float(DEADLINE + 1))  # declared miss penalty

    packets = int(sent.sum())
    normal = x < ALARM
    metrics = dict(
        packets=packets,
        bytes=int(PKT_BYTES * packets),                 # decimal bytes
        delivered=int(received.sum()),
        airtime_ms=float(AIRTIME_MS * packets),
        energy_uj=float(ENERGY_UJ * packets),
        rmse=float(np.sqrt(np.mean(err ** 2))),
        miss=float((len(spans) - len(delays)) / len(spans)) if spans else 0.0,
        delay=float(np.mean(delays)) if delays else None,   # conditional
        penalty=float(np.mean(scores)) if scores else 0.0,
        faocc=float(np.mean(estimate[normal] >= ALARM)) if normal.any() else 0.0,
    )

    # ---------------- conservation checks (gate 4) ----------------
    assert metrics["bytes"] == PKT_BYTES * packets
    assert metrics["airtime_ms"] == AIRTIME_MS * packets
    assert metrics["energy_uj"] == ENERGY_UJ * packets
    assert 0 < metrics["delivered"] <= packets <= n
    return metrics, estimate, sent, received


# --------------------------------------------------------------------------
# Run-level statistics (gate 7)
# --------------------------------------------------------------------------
def ci95(values):
    """Mean and half-width of a 95% Student-t interval over runs."""
    a = np.asarray([v for v in values if v is not None], dtype=float)
    mean = float(a.mean())
    half = float(student_t.ppf(0.975, len(a) - 1) * a.std(ddof=1)
                 / np.sqrt(len(a)))
    return dict(mean=mean, half=half, n=int(len(a)))


def summarize(records):
    keys = [k for k in records[0] if k != "delay"] + ["delay"]
    out = {}
    for k in keys:
        if k in records[0]:
            out[k] = ci95([r[k] for r in records])
    return out


def experiment(configs=None, p=0.1, n_events=12, short=False, burst=False,
               seeds=SEEDS):
    """Run each (name, kwargs) config on identical trace/channel pairs."""
    if configs is None:
        configs = [(name, {}) for name in ("Periodic", "Change", "Hybrid")]
    raw = {name: [] for name, _ in configs}
    for seed in seeds:
        x, spans = make_trace(seed, n_events=n_events, short=short)
        good = make_channel(seed, p, burst=burst)
        for name, kw in configs:
            m, _, _, _ = run_policy(x, good, spans, name.split(":")[0], **kw)
            raw[name].append(m)
    return {name: summarize(rows) for name, rows in raw.items()}, raw


def paired_diffs(raw_a, raw_b, keys=("bytes", "rmse", "miss", "penalty")):
    """CI of run-level b - a on identical traces/channels."""
    return {k: ci95([rb[k] - ra[k] for ra, rb in zip(raw_a, raw_b)])
            for k in keys}


# --------------------------------------------------------------------------
# Known-answer validation and conservation checks (gate 4)
# --------------------------------------------------------------------------
def validation():
    # 1. Constant signal, no loss: change-only sends only the init packet;
    #    hybrid with H=15 sends init + heartbeats at 15,30,...,90.
    x = np.full(100, 22.0)
    ok = np.ones(100, dtype=bool)
    m = run_policy(x, ok, [], "Change")[0]
    assert m["packets"] == 1 and m["rmse"] == 0.0 and m["bytes"] == 32
    m = run_policy(x, ok, [], "Hybrid", h=15)[0]
    assert m["packets"] == 7 and m["rmse"] == 0.0
    assert m["airtime_ms"] == 7.0 and m["energy_uj"] == 210.0

    # 2. Send every sample, no loss: perfect reconstruction.
    xr = np.linspace(22.0, 28.0, 100)
    m, est, _, _ = run_policy(xr, ok, [], "Periodic", period=1)
    assert m["packets"] == 100 and m["rmse"] == 0.0

    # 3. Total loss: only the reliable init is delivered; estimate frozen.
    bad = np.zeros(100, dtype=bool)
    m, est, _, _ = run_policy(xr, bad, [], "Periodic", period=10)
    assert m["delivered"] == 1 and np.all(est == xr[0])

    # 4. Loss-free change-based reporting keeps error strictly below delta.
    for pol in ("Change", "Hybrid"):
        m, est, _, _ = run_policy(xr, ok, [], pol)
        assert np.max(np.abs(xr - est)) < DELTA0 + 1e-12

    # 5. Known-answer conservation at the nominal operating point:
    #    T=10 s over one hour without loss sends exactly 360 packets.
    xh, spans = make_trace(1000)
    okh = np.ones(N, dtype=bool)
    m = run_policy(xh, okh, spans, "Periodic", period=T0)[0]
    assert m["packets"] == 360
    assert m["bytes"] == 360 * PKT_BYTES
    assert m["airtime_ms"] == 360 * AIRTIME_MS
    assert m["energy_uj"] == 360 * ENERGY_UJ
    assert m["delivered"] == 360

    print("PASS: constant-signal, heartbeat count, full sampling, total loss,"
          " error bound, 360-packet conservation (bytes/airtime/energy).")


# --------------------------------------------------------------------------
# Deterministic mechanism tests (gate 8 stress cases)
# --------------------------------------------------------------------------
def stress_lost_onset():
    """Stable 40 s plateau; the single onset packet at t=17 is erased."""
    x = np.full(80, 22.0)
    x[17:57] = 26.0
    good = np.ones(80, dtype=bool)
    good[17] = False
    out = {}
    for pol in ("Periodic", "Change", "Hybrid"):
        m, est, sent, rec = run_policy(x, good, [(17, 57)], pol)
        det = int(np.flatnonzero(rec & (x >= ALARM))[0]) if np.any(rec & (x >= ALARM)) else None
        out[pol] = dict(metrics=m, first_above_alarm_delivery=det)
    return out


def stress_slow_drift():
    """0.4 C ramp crosses 25 C; total rise is below delta = 0.5 C."""
    x = np.full(80, 24.8)
    x[20:51] = np.linspace(24.8, 25.2, 31)
    x[51:] = 25.2
    onset = int(np.flatnonzero(x >= ALARM)[0])
    good = np.ones(80, dtype=bool)
    out = {}
    for pol in ("Periodic", "Change", "Hybrid"):
        m, est, sent, rec = run_policy(x, good, [(onset, 80)], pol)
        hits = np.flatnonzero(rec[onset:onset + DEADLINE + 1]
                              & (x[onset:onset + DEADLINE + 1] >= ALARM))
        out[pol] = dict(metrics=m,
                        detected=bool(len(hits)),
                        delay=int(hits[0]) if len(hits) else None)
    out["onset"] = onset
    return out


# --------------------------------------------------------------------------
# Main experiment program
# --------------------------------------------------------------------------
def main():
    validation()
    results = {"settings": dict(
        N=N, runs=RUNS, seeds=SEEDS, design_seeds=DESIGN_SEEDS,
        pkt_bytes=PKT_BYTES, airtime_ms=AIRTIME_MS, energy_uj=ENERGY_UJ,
        alarm=ALARM, deadline=DEADLINE, delta=DELTA0, h=H0, t=T0)}

    # Nominal three-policy comparison across three loss levels (paired).
    results["loss"] = {}
    for p in (0.0, 0.1, 0.3):
        summary, raw = experiment(p=p)
        results["loss"][str(p)] = dict(summary=summary, raw=raw)
    results["paired_p0.1"] = paired_diffs(
        results["loss"]["0.1"]["raw"]["Periodic"],
        results["loss"]["0.1"]["raw"]["Hybrid"])

    # Parameter sweeps at p = 0.1 (gate 6: one main factor + one stress
    # factor; here each knob is swept separately for sensitivity).
    configs = [(f"Periodic:{t}", dict(period=t)) for t in (2, 5, 10, 15, 20, 30, 60)]
    configs += [(f"Change:{d}", dict(delta=d)) for d in (0.2, 0.4, 0.5, 0.6, 0.8, 1.2)]
    configs += [(f"Hybrid:{h}", dict(h=h)) for h in (5, 10, 15, 30, 60)]
    results["sweep"], _ = experiment(configs=configs)

    # Stress scenarios (gate 8 / Section 5 of the brief).
    results["high_events"], _ = experiment(n_events=36)
    results["short_events"], _ = experiment(short=True)
    results["bursty"], _ = experiment(p=0.3, burst=True)

    # Optional receiver-side linear predictor, same senders, p = 0.1.
    pred = {}
    for pol in ("Change", "Hybrid"):
        for rec in ("hold", "linear"):
            summary, _ = experiment(configs=[(f"{pol}:{rec}",
                                              dict(receiver=rec))])
            pred[f"{pol}:{rec}"] = summary[f"{pol}:{rec}"]
    results["predictor"] = pred

    # Traffic-matched periodic baseline: interval chosen on DESIGN seeds only.
    cal, _ = experiment(configs=[("Hybrid", {})], seeds=DESIGN_SEEDS)
    avg = cal["Hybrid"]["packets"]["mean"]
    t_match = max(1, int(round(N / avg)))
    summary, _ = experiment(configs=[("Periodic", dict(period=t_match)),
                                     ("Hybrid", {})])
    results["matched"] = dict(period=t_match, summary=summary,
                              design_mean_packets=avg)

    # Deterministic mechanism tests.
    results["stress_lost_onset"] = stress_lost_onset()
    results["stress_slow_drift"] = stress_slow_drift()

    dest = Path(__file__).with_name("results.json")
    dest.write_text(json.dumps(results, indent=1))
    print("Wrote", dest)

    print("\nNominal p=0.1 means:")
    for name, s in results["loss"]["0.1"]["summary"].items():
        print(" ", name, {k: round(v["mean"], 4) for k, v in s.items()})
    print("\nPaired hybrid - periodic:", {
        k: (round(v["mean"], 4), round(v["half"], 4))
        for k, v in results["paired_p0.1"].items()})
    print("Matched period:", t_match, "(design mean packets", round(avg, 2), ")")


if __name__ == "__main__":
    main()
