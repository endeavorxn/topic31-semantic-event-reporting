"""Build the report figures from results.json (and one live re-run for the
illustrative trace/mechanism panels).  Writes figs/*.png."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import simulate as S

HERE = Path(__file__).parent
FIGS = HERE / "figs"
FIGS.mkdir(exist_ok=True)
R = json.loads((HERE / "results.json").read_text())

plt.rcParams.update({
    "font.size": 8.2, "axes.titlesize": 8.6, "axes.labelsize": 8.2,
    "legend.fontsize": 7.2, "xtick.labelsize": 7.4, "ytick.labelsize": 7.4,
    "axes.grid": True, "grid.alpha": 0.28, "grid.linewidth": 0.4,
    "axes.edgecolor": "#666666", "figure.dpi": 200,
    "axes.spines.top": False, "axes.spines.right": False,
})
C = {"Periodic": "#1f77b4", "Change": "#d62728", "Hybrid": "#2ca02c"}


# ---------------------------------------------------------------- model ---
def fig_model():
    fig, ax = plt.subplots(figsize=(6.9, 2.0))
    ax.axis("off"); ax.grid(False)
    BW, BH, Y0 = 0.155, 0.52, 0.30
    gap = 0.052
    x0 = 0.010
    labels = [
        "Sensor process\n$x[k]$: baseline + sine\n+ AR(1) + events",
        "Sender rule $a[k]$\nperiodic / change /\nhybrid ($\\Delta$, $H$)",
        "Erasure channel\nper-slot delivery\nprob. $1-p$ (shared)",
        "Receiver\nhold last value\n($\\pm$ extrapolator)",
        "Offline metrics\nRMSE, misses,\ndelay, bytes",
    ]
    box_texts = []
    centers = []
    for i, txt in enumerate(labels):
        bx = x0 + i * (BW + gap)
        ax.add_patch(plt.Rectangle((bx, Y0), BW, BH, fill=False,
                                   ec="#111111", lw=1.0))
        box_texts.append(ax.text(bx + BW / 2, Y0 + BH / 2, txt,
                                 ha="center", va="center", fontsize=6.6,
                                 color="#111111"))
        centers.append(bx + BW / 2)
    # arrows only inside the inter-box gaps
    for i in range(4):
        gx0 = x0 + i * (BW + gap) + BW + 0.010
        gx1 = x0 + (i + 1) * (BW + gap) - 0.010
        ax.annotate("", xy=(gx1, Y0 + BH / 2), xytext=(gx0, Y0 + BH / 2),
                    arrowprops=dict(arrowstyle="-|>,head_width=0.22,"
                                    "head_length=0.5", color="#111111",
                                    lw=1.2, shrinkA=0, shrinkB=0))
    # dashed no-feedback arc fully below the box row
    ax.annotate("", xy=(centers[1], Y0 - 0.02), xytext=(centers[3], Y0 - 0.02),
                arrowprops=dict(arrowstyle="-|>", color="#8a6d1a", lw=0.9,
                                ls="--", connectionstyle="arc3,rad=0.34"))
    ax.text((centers[1] + centers[3]) / 2, 0.025,
            "no feedback: sender state $(v,\\ \\tau)$ tracks its own attempts only",
            ha="center", va="bottom", fontsize=6.5, color="#8a6d1a")
    ax.text(1 - 0.010, 0.985, "truth labels used only by offline evaluation",
            ha="right", va="top", fontsize=6.2, color="#777777")
    ax.set_xlim(0, 1); ax.set_ylim(-0.02, 1.02)
    fig.tight_layout(pad=0.25)

    # validation: every box label must fit inside its rectangle
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    ok = True
    for i, t in enumerate(box_texts):
        bx = x0 + i * (BW + gap)
        (px0, py0) = ax.transData.transform((bx, Y0))
        (px1, py1) = ax.transData.transform((bx + BW, Y0 + BH))
        tb = t.get_window_extent(renderer)
        if (tb.x0 < px0 - 1 or tb.x1 > px1 + 1
                or tb.y0 < py0 - 1 or tb.y1 > py1 + 1):
            ok = False
            print(f"WARN fig1: label {i} overflows its box "
                  f"(text x[{tb.x0:.0f},{tb.x1:.0f}] y[{tb.y0:.0f},{tb.y1:.0f}]"
                  f" vs box x[{px0:.0f},{px1:.0f}] y[{py0:.0f},{py1:.0f}])")
    print("fig1 box-fit validation:", "PASS" if ok else "FAIL")
    fig.savefig(FIGS / "fig1_model.png", bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------- trace window ----
def fig_trace():
    seed = 1000
    x, spans = S.make_trace(seed)
    good = S.make_channel(seed, 0.1)
    a, b = spans[3][0] - 90, spans[3][1] + 70     # window around 4th event
    k = np.arange(a, b)
    fig, axes = plt.subplots(3, 1, figsize=(6.9, 3.8), sharex=True,
                             gridspec_kw=dict(hspace=0.13))
    handles = labels = None
    for ax, pol in zip(axes, ("Periodic", "Change", "Hybrid")):
        m, est, sent, rec = S.run_policy(x, good, spans, pol)
        h1, = ax.plot(k, x[k], color="#444", lw=0.9, label="true $x[k]$")
        h2, = ax.step(k, est[k], where="post", color=C[pol], lw=1.1,
                      label="receiver estimate")
        att = k[sent[k]]
        ok = rec[k][sent[k]]
        h3, = ax.plot(att[ok], x[att][ok], "o", ms=3.0, mfc=C[pol],
                      mec="none", label="delivered")
        h4, = ax.plot(att[~ok], x[att][~ok], "o", ms=3.4, mfc="none",
                      mec=C[pol], mew=0.9, label="erased")
        if handles is None:
            handles, labels = [h1, h2, h3, h4], [h.get_label() for h in (h1, h2, h3, h4)]
        ax.axhline(S.ALARM, color="#b0721a", ls=":", lw=0.9)
        ax.axvspan(spans[3][0], spans[3][1], color="#f2c979", alpha=0.25, lw=0)
        ax.set_ylabel({"Periodic": "periodic\n$T{=}10$ s",
                       "Change": "change-only\n$\\Delta{=}0.5$ C",
                       "Hybrid": "hybrid\n$\\Delta{=}0.5$ C, $H{=}15$ s"}[pol])
        ax.set_ylim(21.2, 27.4)
    # figure-level legend in the top margin, never over the data
    fig.legend(handles, labels, loc="upper center", ncol=4, frameon=True,
               framealpha=0.95, edgecolor="#cccccc",
               bbox_to_anchor=(0.55, 0.995))
    fig.subplots_adjust(left=0.105, right=0.985, top=0.905, bottom=0.105)
    axes[2].set_xlabel(f"slot $k$ (s); shaded band = event window; seed {seed}, p = 0.1")
    fig.savefig(FIGS / "fig2_trace.png", bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------ loss -------
def fig_loss():
    fig, axes = plt.subplots(1, 2, figsize=(6.7, 2.35))
    ps = [0.0, 0.1, 0.3]
    for pol in ("Periodic", "Change", "Hybrid"):
        rm = [R["loss"][str(p)]["summary"][pol]["rmse"] for p in ps]
        ms = [R["loss"][str(p)]["summary"][pol]["miss"] for p in ps]
        axes[0].errorbar(ps, [v["mean"] for v in rm],
                         yerr=[v["half"] for v in rm], color=C[pol],
                         marker="o", ms=3.5, capsize=2.4, lw=1.2, label=pol)
        axes[1].errorbar([100 * p for p in ps], [100 * v["mean"] for v in ms],
                         yerr=[100 * v["half"] for v in ms], color=C[pol],
                         marker="o", ms=3.5, capsize=2.4, lw=1.2, label=pol)
    axes[0].set_xlabel("independent loss probability $p$")
    axes[0].set_ylabel("reconstruction RMSE (C)")
    axes[1].set_xlabel("independent loss probability $p$ (%)")
    axes[1].set_ylabel("deadline-miss fraction (%)")
    axes[1].set_ylim(-3, 44)
    axes[0].legend(frameon=False)
    fig.tight_layout(pad=0.4)
    fig.savefig(FIGS / "fig3_loss.png", bbox_inches="tight")
    plt.close(fig)


# -------------------------------------------------------- trade-off -----
def fig_tradeoff():
    fig, ax = plt.subplots(figsize=(6.7, 2.75))
    groups = {
        "Periodic (sweep $T$)": ("Periodic:", C["Periodic"], "o", "T"),
        "Change-only (sweep $\\Delta$)": ("Change:", C["Change"], "s", "D"),
        "Hybrid (sweep $H$)": ("Hybrid:", C["Hybrid"], "^", "H"),
    }
    for label, (prefix, col, mk, tag) in groups.items():
        xs, ys, xe, ye, ann = [], [], [], [], []
        for name, s in R["sweep"].items():
            if not name.startswith(prefix):
                continue
            xs.append(s["bytes"]["mean"] / 1000)
            ys.append(s["rmse"]["mean"])
            xe.append(s["bytes"]["half"] / 1000)
            ye.append(s["rmse"]["half"])
            ann.append(name.split(":")[1])
        ax.errorbar(xs, ys, xerr=xe, yerr=ye, color=col, marker=mk, ms=4,
                    lw=1.1, capsize=1.6, elinewidth=0.7, label=label)
        for xv, yv, t in zip(xs, ys, ann):
            if t in ("10", "0.5", "15"):
                ax.annotate(f"{tag}={t}", (xv, yv), textcoords="offset points",
                            xytext=(4, 4), fontsize=6.6, color=col)
    mm = R["matched"]["summary"]
    ax.plot([mm["Periodic"]["bytes"]["mean"] / 1000],
            [mm["Periodic"]["rmse"]["mean"]], "d", color="#000",
            ms=4.5, label="periodic $T{=}14$s (traffic-matched)")
    ax.set_xlabel("mean attempted traffic (kB per hour, incl. headers and erasures)")
    ax.set_ylabel("mean RMSE (C)")
    ax.set_xlim(0, 26)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout(pad=0.4)
    fig.savefig(FIGS / "fig4_tradeoff.png", bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------- deterministic tests ---
def fig_stress():
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 2.6))

    ax = axes[0]
    x = np.full(80, 22.0); x[17:57] = 26.0
    good = np.ones(80, dtype=bool); good[17] = False
    h0, = ax.plot(x, color="#444", lw=0.9, label="true $x[k]$")
    hs = []
    for pol in ("Periodic", "Change", "Hybrid"):
        m, est, sent, rec = S.run_policy(x, good, [(17, 57)], pol)
        h, = ax.step(np.arange(80), est, where="post", color=C[pol], lw=1.0,
                     label=pol)
        hs.append(h)
    ax.plot([17], [26.0], "x", color="#000", ms=6, mew=1.4)
    ax.annotate("erased onset packet", (17, 26.0), xycoords="data",
                xytext=(0.44, 0.92), textcoords="axes fraction",
                fontsize=6.6, arrowprops=dict(arrowstyle="->", lw=0.7,
                                              color="#555"))
    ax.axvspan(17, 28, color="#f2c979", alpha=0.25, lw=0)
    ax.text(22.5, 20.5, "10 s deadline", fontsize=6.6, ha="center",
            color="#8a6d1a")
    ax.set_title("(a) lost onset packet, stable plateau", fontsize=8.0)
    ax.set_xlabel("slot $k$ (s)"); ax.set_ylabel("value (C)")
    ax.set_ylim(20.2, 27.9)
    ax.legend(handles=[h0] + hs, frameon=False, fontsize=6.4, loc="upper left")
    ax.grid(False, axis="x")

    ax = axes[1]
    x = np.full(80, 24.8); x[20:51] = np.linspace(24.8, 25.2, 31); x[51:] = 25.2
    good = np.ones(80, dtype=bool)
    ax.plot(x, color="#444", lw=0.9)
    for pol in ("Periodic", "Change", "Hybrid"):
        m, est, sent, rec = S.run_policy(x, good, [(35, 80)], pol)
        ax.step(np.arange(80), est, where="post", color=C[pol], lw=1.0, label=pol)
    ax.axhline(25.0, color="#b0721a", ls=":", lw=0.9)
    ax.axvline(35, color="#b0721a", ls=":", lw=0.7)
    ax.annotate("alarm crossed,\ntotal rise 0.4 C < $\\Delta$", (36, 25.0),
                xycoords="data", xytext=(0.50, 0.97),
                textcoords="axes fraction", fontsize=6.6,
                arrowprops=dict(arrowstyle="->", lw=0.7, color="#555"))
    ax.set_title("(b) slow drift below the change threshold", fontsize=8.0)
    ax.set_xlabel("slot $k$ (s)"); ax.set_ylabel("value (C)")
    ax.set_ylim(24.76, 25.28)
    ax.legend(frameon=False, fontsize=6.4, loc="upper left")
    ax.grid(False, axis="x")

    fig.tight_layout(pad=0.4)
    fig.savefig(FIGS / "fig5_stress.png", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    fig_model(); fig_trace(); fig_loss(); fig_tradeoff(); fig_stress()
    print("figures written to", FIGS)
