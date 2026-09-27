"""plos_figures.py -- producer of PLOS ONE Fig 1-3 for R8 (design: docs/design/plos_figure_set.md).

Reads data/frozen/v1_9r/corpus_master.csv and r8.py (WEIGHTS, by ast), both hash-gated.
Before drawing anything it reproduces the values docs/design/plos_figure_set.md section 2
lists; any mismatch exits 2 and writes no figure.

Writes Fig1.tif, Fig2.tif, Fig3.tif into --outdir (default docs/figures/plos under the
repository root): RGB 8-bit, no alpha, LZW, single page, 300 dpi, width within 789-2250 px,
height at most 2625 px, font Arial, every visible text 8-12 pt (PLOS figure envelope,
Pending 95). Text sizes are checked on the drawn figure before the file is written, and each
file is re-opened and checked after writing.

stdout carries every value a figure displays (RESULT lines): the Fig 2B operating points, one
per distinct CMI value among the 196, and the Fig 3 distributions. The log of a production
run is the source a ledger row cites (Pending 113).

Font: Arial is required. --font-substitute NAME exists only for an environment without Arial;
a run using it ends RESULT: FAIL and is never a production run.

Run from anywhere; the repository root is the parent of this file's directory.
"""
import argparse
import ast
import csv
import hashlib
import io
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "data", "frozen", "v1_9r", "corpus_master.csv")
R8 = os.path.join(ROOT, "r8.py")
CORPUS_SHA = "57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b"
R8_SHA = "53553ce13a815a4bcc30f448cbb3ed2808a6ce3fedb61a26059fc949b3fd09b5"
FONT = "Arial"
HIGH_T = 41.0
MED_T = 35.0
STRICT_T = 60.0
RECALL_DEN = 118            # 117 HIGH in the 196 + 1 HIGH with CMI = 0
GEMINI_ABSENT = ("WEB_043", "Web_089", "note112", "note_096")   # EV-r196-069
# Counts from the run files, not from corpus_master (EV-r196-069): stated, not computed.
RUN_SET = 217               # rows per Claude run file
OUT_OF_CORPUS = 12          # run-file targets absent from corpus_master
DPI = 300
FULL_W_CM = 19.05           # 2250 px at 300 dpi
COL_W_CM = 13.2             # PLOS text-column alignment
FONT_MIN_PT = 8             # PLOS figure text 8-12 pt (Pending 95)
FONT_MAX_PT = 12
OKABE = {"HIGH": "#D55E00", "MEDIUM": "#E69F00", "LOW": "#0072B2",
         "tp": "#009E73", "reach": "#CC79A7", "bound": "#56B4E9", "grey": "#666666"}


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fail(msg):
    print("GATE FAIL:", msg)
    print("RESULT: FAIL (%s)" % msg)
    sys.exit(2)


def weights():
    tree = ast.parse(open(R8, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "WEIGHTS" for t in node.targets):
            return ast.literal_eval(node.value)
    fail("WEIGHTS not found in r8.py")


def measure():
    for path, want in ((CORPUS, CORPUS_SHA), (R8, R8_SHA)):
        got = sha(path)
        print("INPUT %s %s" % (os.path.relpath(path, ROOT).replace(os.sep, "/"), got))
        if got != want:
            fail("%s hash mismatch" % os.path.basename(path))
    w = weights()
    comps = [c for c in w if w[c] > 0]
    rows = list(csv.DictReader(open(CORPUS, encoding="utf-8-sig")))
    cmi = lambda r: float(r["cmi"])
    valid = [r for r in rows if cmi(r) > 0]
    act = lambda r: [c for c in comps if float(r[c]) > 0]
    lvl = lambda r: statistics.mean(float(r[c]) for c in act(r))
    high = [r for r in valid if r["human_label"] == "HIGH"]
    tp = [r for r in high if cmi(r) >= HIGH_T]
    fn = [r for r in high if cmi(r) < HIGH_T]
    cap = lambda r: round(100 * sum(w[c] for c in act(r)), 1)
    reach = [r for r in fn if cap(r) >= HIGH_T]
    bound = [r for r in fn if cap(r) < HIGH_T]
    zero_high = [r for r in rows if cmi(r) == 0 and r["human_label"] == "HIGH"]
    gem_absent = [r for r in valid if r["target"] in GEMINI_ABSENT]
    lab = {k: [r for r in valid if r["human_label"] == k] for k in ("HIGH", "MEDIUM", "LOW")}
    cells = {(h, l): sum(1 for r in valid if r["human_label"] == h and r["level"] == l)
             for h in ("HIGH", "MEDIUM", "LOW") for l in ("HIGH", "MEDIUM", "LOW")}

    def pr(t):
        pos = [r for r in valid if cmi(r) >= t]
        k = sum(r["human_label"] == "HIGH" for r in pos)
        return k, len(pos) - k, (k / len(pos) if pos else float("nan")), k / RECALL_DEN

    tp41, fp41, p41, r41 = pr(HIGH_T)
    tp60, fp60, p60, r60 = pr(STRICT_T)
    got = {
        "rows": len(rows), "valid": len(valid), "cmi0": len(rows) - len(valid),
        "zero_high": len(zero_high), "gemini_common": len(valid) - len(gem_absent),
        "n_high": len(high), "n_med": len(lab["MEDIUM"]), "n_low": len(lab["LOW"]),
        "tp": len(tp), "fn": len(fn),
        "mean_act_tp": round(statistics.mean(len(act(r)) for r in tp), 2),
        "mean_act_fn": round(statistics.mean(len(act(r)) for r in fn), 2),
        "min_act_tp": min(len(act(r)) for r in tp),
        "lvl_tp": round(statistics.mean(lvl(r) for r in tp), 3),
        "lvl_fn": round(statistics.mean(lvl(r) for r in fn), 3),
        "table4": tuple(cells[(h, l)] for h in ("HIGH", "MEDIUM", "LOW") for l in ("HIGH", "MEDIUM", "LOW")),
        "pr41": (round(p41, 3), round(r41, 3)), "pr60": (round(p60, 3), round(r60, 3)),
        "reach": len(reach), "bound": len(bound), "n_comps": len(comps),
    }
    want = {
        "rows": 205, "valid": 196, "cmi0": 9, "zero_high": 1, "gemini_common": 192,
        "n_high": 117, "n_med": 67, "n_low": 12, "tp": 41, "fn": 76,
        "mean_act_tp": 7.29, "mean_act_fn": 5.12, "min_act_tp": 4,
        "lvl_tp": 0.755, "lvl_fn": 0.699,
        "table4": (41, 27, 49, 0, 7, 60, 1, 1, 10),
        "pr41": (0.976, 0.347), "pr60": (1.0, 0.051),
        "reach": 47, "bound": 29, "n_comps": 13,
    }
    for k in want:
        ok = got[k] == want[k]
        print("GATE %-14s %-28s %s" % (k, got[k], "OK" if ok else "EXPECTED %s" % (want[k],)))
        if not ok:
            fail("gate %s" % k)
    if RUN_SET - OUT_OF_CORPUS != len(rows):
        fail("run set arithmetic")
    print("GATE PASS")
    return dict(valid=valid, lab=lab, tp=tp, reach=reach, bound=bound, act=act, lvl=lvl,
                pr=pr, cmi=cmi, rows=rows, gem_absent=len(gem_absent), zero_high=len(zero_high))


def report(d):
    ts = sorted({d["cmi"](r) for r in d["valid"]}, reverse=True)
    print("RESULT fig2b operating_points=%d recall_denominator=%d" % (len(ts), RECALL_DEN))
    for t in ts:
        k, f, p, r = d["pr"](t)
        print("RESULT fig2b t=%.1f tp=%d fp=%d precision=%.4f recall=%.4f" % (t, k, f, p, r))
    print("RESULT fig2b baseline=%.4f (117/196)" % (117 / 196))
    groups = (("tp", d["tp"]), ("fn_reach", d["reach"]), ("fn_bound", d["bound"]))
    for name, g in groups:
        dist = {}
        for r in g:
            n = len(d["act"](r))
            dist[n] = dist.get(n, 0) + 1
        print("RESULT fig3a %s n=%d active_count %s" % (name, len(g),
              " ".join("%d:%d" % kv for kv in sorted(dist.items()))))
    for name, g in groups:
        v = sorted(d["lvl"](r) for r in g)
        print("RESULT fig3b %s n=%d mean=%.3f median=%.3f min=%.3f max=%.3f" % (
            name, len(g), statistics.mean(v), statistics.median(v), v[0], v[-1]))


def setup_plt(font_name):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import font_manager
    try:
        path = font_manager.findfont(font_manager.FontProperties(family=font_name),
                                     fallback_to_default=False)
    except ValueError:
        fail("font %s not available" % font_name)
    print("FONT %s -> %s" % (font_name, path))
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": font_name, "font.size": 9, "axes.titlesize": 9,
                         "axes.labelsize": 9, "xtick.labelsize": 8, "ytick.labelsize": 8,
                         "legend.fontsize": 8, "svg.fonttype": "none"})
    return plt


def save_tiff(plt, fig, path):
    from PIL import Image
    from matplotlib.text import Text
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white")
    sizes = sorted({round(t.get_fontsize(), 2) for t in fig.findobj(Text)
                    if t.get_visible() and t.get_text().strip()})
    ok_size = bool(sizes) and FONT_MIN_PT <= sizes[0] and sizes[-1] <= FONT_MAX_PT
    print("FONTSIZE %s pt=%s %s" % (os.path.basename(path), sizes,
                                    "OK" if ok_size else "OUT OF ENVELOPE"))
    plt.close(fig)
    if not ok_size:
        fail("%s text outside %s-%s pt" % (os.path.basename(path), FONT_MIN_PT, FONT_MAX_PT))
    buf.seek(0)
    im = Image.open(buf).convert("RGB")
    im.save(path, format="TIFF", compression="tiff_lzw", dpi=(DPI, DPI))
    chk = Image.open(path)
    info = (chk.mode, chk.info.get("compression"), tuple(round(x) for x in chk.info.get("dpi", (0, 0))),
            chk.size, getattr(chk, "n_frames", 1), os.path.getsize(path))
    ok = (info[0] == "RGB" and info[1] == "tiff_lzw" and info[2] == (DPI, DPI)
          and 789 <= info[3][0] <= 2250 and info[3][1] <= 2625 and info[4] == 1
          and info[5] < 10 * 1024 * 1024)
    print("FILE %s mode=%s compression=%s dpi=%s size=%sx%s frames=%d bytes=%d sha256=%s %s" % (
        os.path.basename(path), info[0], info[1], info[2], info[3][0], info[3][1], info[4],
        info[5], sha(path), "OK" if ok else "OUT OF ENVELOPE"))
    if not ok:
        fail("%s outside the PLOS envelope" % os.path.basename(path))


def cm(x):
    return x / 2.54


def fig1(plt, d, path):
    from matplotlib.patches import FancyBboxPatch
    fig = plt.figure(figsize=(cm(FULL_W_CM), cm(11.5)))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 190.5)
    ax.set_ylim(0, 115)
    ax.axis("off")
    n = len(d["rows"])
    v = len(d["valid"])
    g = v - d["gem_absent"]
    ng = len(GEMINI_ABSENT)
    grey = OKABE["grey"]

    def box(x, y, w, h, main, sub=None, side=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.5",
                                    fc="#F2F2F2" if side else "white", ec="black", lw=0.8))
        if sub:
            ax.text(x + w / 2, y + h - 4.5, main, ha="center", va="center", fontsize=8.5)
            ax.text(x + w / 2, y + (h - 7) / 2, sub, ha="center", va="center", fontsize=8,
                    color=grey)
        else:
            ax.text(x + w / 2, y + h / 2, main, ha="center", va="center", fontsize=8.5)

    def arrow(x0, y0, x1, y1):
        ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                    arrowprops=dict(arrowstyle="-|>", lw=0.8, color="black"))

    ax.text(34, 111, "Corpus branch", ha="center", va="center", fontsize=9, fontweight="bold")
    ax.text(151.5, 111, "Run branch", ha="center", va="center", fontsize=9, fontweight="bold")
    box(4, 92, 60, 13, "Phase 1 set\n%d documents" % RUN_SET)
    box(4, 64, 60, 15, "Corpus, n = %d" % n, "Table 2")
    box(4, 30, 60, 21, "CMI > 0, n = %d" % v,
        "Tables 3-4, Precision, Specificity,\nhuman and Claude kappa, Table 6 (Claude);\n"
        "Recall denominator %d, incl. %d with CMI = 0" % (RECALL_DEN, d["zero_high"]))
    box(4, 4, 60, 15, "n = %d" % g, "Gemini kappa, Table 6 (Gemini)")
    box(72, 81, 50, 8, "Corpus quality control: \u2212%d" % OUT_OF_CORPUS, side=True)
    box(72, 53, 50, 8, "CMI = 0: \u2212%d" % (n - v), side=True)
    box(72, 20.5, 50, 8, "Absent from every\nGemini run: \u2212%d" % ng, side=True)
    for y0, y1 in ((92, 79), (64, 51), (30, 19)):
        arrow(34, y0 - 0.8, 34, y1 + 0.8)
        ym = (y0 + y1) / 2
        arrow(34, ym, 71.2, ym)
    box(124, 62, 55, 17, "Claude runs", "%d documents per run\nTable 5: the %d corpus documents" % (RUN_SET, n))
    box(124, 34, 55, 17, "Gemini runs", "%d documents per run\nTable 5: %d (the %d less %d)" % (RUN_SET - ng, n - ng, n, ng))
    arrow(64.8, 98.5, 151.5, 98.5)
    arrow(151.5, 98.5, 151.5, 79.8)
    arrow(151.5, 62 - 0.8, 151.5, 51 + 0.8)
    ax.text(153.5, 56.5, "\u2212%d targets absent\nfrom every Gemini run" % ng, ha="left",
            va="center", fontsize=8, color=grey)
    save_tiff(plt, fig, path)


def fig2(plt, d, path):
    fig, (a, b) = plt.subplots(1, 2, figsize=(cm(FULL_W_CM), cm(8.5)),
                               gridspec_kw={"width_ratios": [1, 1.1]})
    rnd = random.Random(20260922)
    order = ("HIGH", "MEDIUM", "LOW")
    data = [[d["cmi"](r) for r in d["lab"][k]] for k in order]
    for i, (k, vals) in enumerate(zip(order, data)):
        a.scatter([i + rnd.uniform(-0.18, 0.18) for _ in vals], vals, s=7,
                  color=OKABE[k], alpha=0.8, lw=0, zorder=3)
    for t in (MED_T, HIGH_T, STRICT_T):
        a.axhline(t, color=OKABE["grey"], lw=0.8, ls="--")
        a.text(2.65, t, "%d" % t, va="center", ha="left", fontsize=8, color=OKABE["grey"],
               clip_on=False)
    a.set_xticks(range(3))
    a.set_xticklabels(["%s\n(n = %d)" % (k, len(v)) for k, v in zip(order, data)])
    a.set_xlim(-0.6, 2.6)
    a.set_ylabel("CMI")
    a.set_xlabel("human_label")
    ts = sorted({d["cmi"](r) for r in d["valid"]}, reverse=True)
    pts = [d["pr"](t) for t in ts]
    b.step([p[3] for p in pts], [p[2] for p in pts], where="post", color="black", lw=1.0)
    b.axhline(117 / 196, color=OKABE["grey"], lw=0.8, ls=":")
    for t in (HIGH_T, STRICT_T):
        _, _, p, r = d["pr"](t)
        b.plot([r], [p], "o", color=OKABE["HIGH"], ms=5, zorder=3)
        b.annotate("CMI \u2265 %d" % t, (r, p), xytext=(4, 8), textcoords="offset points",
                   fontsize=8)
    b.set_xlim(0, 1.0)
    b.set_ylim(0.5, 1.05)
    b.set_xlabel("Recall (denominator %d)" % RECALL_DEN)
    b.set_ylabel("Precision")
    for ax, letter in ((a, "A"), (b, "B")):
        ax.spines[["top", "right"]].set_visible(False)
        ax.text(-0.16, 1.03, letter, transform=ax.transAxes, fontsize=11, fontweight="bold")
    fig.tight_layout()
    save_tiff(plt, fig, path)


def fig3(plt, d, path):
    fig, (a, b) = plt.subplots(1, 2, figsize=(cm(FULL_W_CM), cm(8.0)),
                               gridspec_kw={"width_ratios": [1.35, 1]})
    act = d["act"]
    xs = list(range(1, 14))
    ntp, nfn = len(d["tp"]), len(d["reach"]) + len(d["bound"])
    cnt = lambda g, k: sum(1 for r in g if len(act(r)) == k)
    wbar = 0.38
    a.bar([x - wbar / 2 for x in xs], [100 * cnt(d["tp"], k) / ntp for k in xs], wbar,
          color=OKABE["tp"], label="Detected, CMI \u2265 41 (n = %d)" % ntp)
    bound = [100 * cnt(d["bound"], k) / nfn for k in xs]
    reach = [100 * cnt(d["reach"], k) / nfn for k in xs]
    a.bar([x + wbar / 2 for x in xs], bound, wbar, color=OKABE["bound"],
          label="FN, below 41 at saturation (n = %d)" % len(d["bound"]))
    a.bar([x + wbar / 2 for x in xs], reach, wbar, bottom=bound, color=OKABE["reach"],
          label="FN, reaches 41 at saturation (n = %d)" % len(d["reach"]))
    a.axvline(3.5, color=OKABE["grey"], lw=0.8, ls="--")
    a.set_xticks(xs)
    a.set_xlabel("Activated categories")
    a.set_ylabel("Percent of group")
    a.set_ylim(0, 42)
    h, l = a.get_legend_handles_labels()
    a.legend([h[0], h[2], h[1]], [l[0], l[2], l[1]], frameon=False, loc="upper right")
    groups = (d["tp"], d["reach"], d["bound"])
    names = ("Detected", "FN, reaches\n41 at sat.", "FN, below\n41 at sat.")
    cols = (OKABE["tp"], OKABE["reach"], OKABE["bound"])
    rnd = random.Random(20260923)
    vals = [[d["lvl"](r) for r in g] for g in groups]
    for i, v in enumerate(vals):
        b.hlines(statistics.mean(v), i - 0.3, i + 0.3, color="black", lw=1.2, zorder=4)
    for i, (v, c) in enumerate(zip(vals, cols)):
        b.scatter([i + rnd.uniform(-0.18, 0.18) for _ in v], v, s=7, color=c, lw=0, zorder=3)
    b.set_xticks(range(3))
    b.set_xticklabels(["%s\n(n = %d)" % (n, len(v)) for n, v in zip(names, vals)])
    b.set_ylabel("Mean activation of activated categories")
    b.set_ylim(0, 1.05)
    for ax, letter in ((a, "A"), (b, "B")):
        ax.spines[["top", "right"]].set_visible(False)
        ax.text(-0.14, 1.03, letter, transform=ax.transAxes, fontsize=11, fontweight="bold")
    fig.tight_layout()
    save_tiff(plt, fig, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=os.path.join(ROOT, "docs", "figures", "plos"))
    ap.add_argument("--font-substitute", default=None)
    args = ap.parse_args()
    print("PRODUCER scripts/plos_figures.py argv=%s" % sys.argv[1:])
    d = measure()
    report(d)
    font = args.font_substitute or FONT
    plt = setup_plt(font)
    import matplotlib
    print("MATPLOTLIB %s" % matplotlib.__version__)
    os.makedirs(args.outdir, exist_ok=True)
    fig1(plt, d, os.path.join(args.outdir, "Fig1.tif"))
    fig2(plt, d, os.path.join(args.outdir, "Fig2.tif"))
    fig3(plt, d, os.path.join(args.outdir, "Fig3.tif"))
    if args.font_substitute:
        print("RESULT: FAIL (font substitute %s in use; not a production run)" % font)
        sys.exit(1)
    print("RESULT: PASS")


if __name__ == "__main__":
    main()
