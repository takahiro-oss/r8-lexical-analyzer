"""permutation_pairs_compute.py -- permutation tests against a random-guessing
null, for one rater pair in full and for all ten pairs on the polar rate.

CANONICAL PRODUCER for: EV-kappa-006 and EV-p1-001.

WHY THIS SCRIPT EXISTS. EV-p1-001's ten p-values were produced by an in-session
inline script that was never saved (Pending 106). scripts/permutation_test_kappa.py
covers ONE pair only: it fixes one side to corpus_master's human_label and loads
the other from a single xlsm workbook, so it can neither pair the two raters with
each other nor use an LLM majority vote. This script covers all ten.

THE CONVENTION IS NOT A CHOICE MADE HERE; IT WAS RECOVERED BY MEASUREMENT.
Permuting the SECOND-named rater with numpy's default_rng(42) reproduces every
recorded p-value; permuting the first does not (measured S299-J: 0.0008 / 0.1001
/ 0.0018 against the recorded 0.0011 / 0.097 / 0.0019). The convention is
therefore gated, not assumed.

Usage:
    python scripts/permutation_pairs_compute.py \
        --gate_dir data/frozen/v1_9 --new_dir data/frozen/v1_9r \
        --rater1_file <rater 1 workbook .xlsm> --rater2_file <rater 2 workbook .xlsm> \
        --log data/frozen/v1_9r/audit_permutation_pairs_v1_9r.txt

Reader mode, the only mode that runs on the released data:
    python scripts/permutation_pairs_compute.py --public_dir <bundle dir>

Exit 0 only when every GATE assertion passes.
"""
import argparse
import csv
import hashlib
import io
import sys
from collections import Counter

import numpy as np
from decimal import Decimal, ROUND_HALF_UP


def half_up(x, places):
    """Round half away from zero, matching human_kappa_compute.py and the
    FROZEN_MANIFEST convention."""
    return float(Decimal(repr(float(x))).quantize(Decimal('1.' + '0' * places),
                                                  rounding=ROUND_HALF_UP))


def agrees(computed, recorded, places):
    """THE GATE DOES NOT ADJUDICATE A DISPLAY CONVENTION, AND THIS IS DELIBERATE.
    Measured S299-J: five of this script's recorded targets land EXACTLY on a
    half at their recorded precision (0.1535, 0.2125, 0.7525, 0.0435, 0.0725),
    and a sixth, p = 23/20000 = 0.00115, does so at four places. Python's round()
    and a half-up rounding disagree on every one of them, and the ledger itself
    mixes conventions -- three-digit percentages recorded one way, four-digit
    p-values another (Pending 105). The recorded convention is therefore NOT
    recoverable from the recorded values.
    So the gate asserts that the computed value lies within half a unit of the
    last recorded place. That is exactly the set of raw values that could have
    produced the recorded string under ANY rounding rule, and it excludes every
    genuine value difference. The raw value is logged beside it, so a later
    session that fixes the convention can re-decide without re-running."""
    return abs(float(computed) - float(recorded)) <= 0.5 * 10 ** (-places) + 1e-12


LS = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}
N_SIM = 20000
SEED = 42

CLAUDE_RUNS = ['results_claude.csv', 'results_claude_v2.csv', 'results_claude_v3.csv',
               'results_claude_v4.csv', 'results_claude_v5.csv']
GEMINI_RUNS = ['results_gemini_v2.csv', 'results_gemini_v3.csv', 'results_gemini_v4.csv',
               'results_gemini_v5.csv', 'results_gemini_v6.csv']

# Pair order is load-bearing: the SECOND element is the one permuted.
PAIRS = [('author', 'rater1'), ('author', 'rater2'), ('rater1', 'rater2'),
         ('author', 'claude'), ('author', 'gemini'),
         ('rater1', 'claude'), ('rater1', 'gemini'),
         ('rater2', 'claude'), ('rater2', 'gemini'),
         ('claude', 'gemini')]

# Recorded n=202 values.
#   k006_*  EV-kappa-006 (author x rater1, three rates with null and CI)
#   p1_*    EV-p1-001 (ten pairs, polar-rate p only) and its 180/198 statement
# RATES ARE RECORDED AS PERCENTAGES REACHED BY TWO-STAGE ROUNDING, measured
# S299-J and not assumed: the proportion is rounded to four places, multiplied
# by 100, then rounded to one. A single-stage rounding of the raw proportion
# disagrees with three of the ten (15.4 / 21.3 / 75.3 would print 15.3 / 21.2 /
# 75.2). This is the percentage form of the FROZEN_MANIFEST convention and the
# same double-rounding path Pending 105 records for pabak_rater2.
GATE_K006_PCT = {
    'k006_obs_exact': 38.1, 'k006_obs_adjacent': 84.7, 'k006_obs_opposite': 15.4,
    'k006_null_exact': 32.9, 'k006_null_adjacent': 78.8, 'k006_null_opposite': 21.3,
    'k006_adj_ci_lo': 75.3, 'k006_adj_ci_hi': 82.7,
    'k006_opp_ci_lo': 17.3, 'k006_opp_ci_hi': 24.8,
}
# p-values are recorded by a printf-style path and 23/20000 = 0.00115 sits
# exactly on a half at four places, so these are gated by tolerance, not by
# reproducing a convention the record does not fix.
GATE_K006_P = {
    'k006_p_exact': (0.044, 3), 'k006_p_adjacent': (0.0011, 4),
    'k006_p_opposite': (0.0011, 4),
}
GATE_P1 = {
    ('author', 'rater1'): 0.0011, ('author', 'rater2'): 0.097,
    ('rater1', 'rater2'): 0.0019, ('author', 'claude'): 0.0011,
    ('author', 'gemini'): 0.0039, ('rater1', 'claude'): 0.0003,
    ('rater1', 'gemini'): 0.059, ('rater2', 'claude'): 0.035,
    ('rater2', 'gemini'): 0.073, ('claude', 'gemini'): 0.0000,
}
GATE_MISC = {'gemini_n': 198, 'gemini_high': 180}

# PUBLIC MODE expectations at the deduplicated population, transcribed from the
# ledger BEFORE any public-mode run existed so that the check is not fitted to its
# own output. Recorded as proportions to four places and compared with agrees().
#   k006_*  EV-r196-059     p1 / n / gemini_*  EV-r196-062
PUBLIC_K006 = {
    'k006_obs_exact': 0.3929, 'k006_obs_adjacent': 0.8520, 'k006_obs_opposite': 0.1480,
    'k006_null_exact': 0.3298, 'k006_null_adjacent': 0.7894, 'k006_null_opposite': 0.2106,
    'k006_adj_ci_lo': 0.7500, 'k006_adj_ci_hi': 0.8265,
    'k006_opp_ci_lo': 0.1735, 'k006_opp_ci_hi': 0.2500,
    'k006_p_exact': 0.0214, 'k006_p_adjacent': 0.0006, 'k006_p_opposite': 0.0006,
}
PUBLIC_P1 = {
    ('author', 'rater1'): 0.0006, ('author', 'rater2'): 0.0908,
    ('rater1', 'rater2'): 0.0012, ('author', 'claude'): 0.0006,
    ('author', 'gemini'): 0.0037, ('rater1', 'claude'): 0.0001,
    ('rater1', 'gemini'): 0.0537, ('rater2', 'claude'): 0.0302,
    ('rater2', 'gemini'): 0.0747, ('claude', 'gemini'): 0.0000,
}
PUBLIC_N = {('author', 'rater1'): 196, ('author', 'rater2'): 196,
            ('rater1', 'rater2'): 196, ('author', 'gemini'): 192}
PUBLIC_MISC = {'gemini_n': 192, 'gemini_high': 174}
RELEASED_RATER_FILES = ('rater1_labels.csv', 'rater2_labels.csv')


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def load_master(path):
    return list(csv.DictReader(io.StringIO(open(path, 'rb').read().decode('utf-8-sig'))))


def load_xlsm(path):
    # openpyxl is imported here rather than at module level: it is needed only by
    # this branch, which requires the annotation workbooks. Those are not part of
    # the public data bundle, so a reader working from the bundle takes the CSV
    # branch and must not be made to install a package this run never uses.
    import openpyxl
    wb = openpyxl.load_workbook(path, keep_vba=True, data_only=True)
    ws = wb['\u5224\u5b9a\u30b7\u30fc\u30c8']
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[1] is None:
            break
        tid = str(row[1]).strip()
        lab = row[6]
        if lab and str(lab).strip():
            out[tid] = str(lab).strip().upper()
    return out


def load_run(path):
    rows = load_master(path)
    return {r['target']: str(r['ai_label']).strip().upper()
            for r in rows if r['ai_label'] and str(r['ai_label']).strip()}


def majority(runs, ids):
    """Majority label over the five runs. A target absent from ANY run is
    excluded, which is what produces the Gemini population of 198 at n=202."""
    out = {}
    for t in ids:
        vals = [r[t] for r in runs if t in r]
        if len(vals) < len(runs):
            continue
        out[t] = Counter(vals).most_common(1)[0][0]
    return out


def three_rates(a_scores, b_labels):
    b = np.array([LS[x] for x in b_labels])
    d = np.abs(a_scores - b)
    return float(np.mean(d == 0)), float(np.mean(d <= 1)), float(np.mean(d == 2))


def permute_second(a_lab, b_lab, ids):
    """Returns (observed triple, null triples array). The SECOND rater's label
    sequence is permuted, preserving its marginal counts."""
    A = np.array([LS[a_lab[t]] for t in ids])
    arr = np.array([b_lab[t] for t in ids])
    obs = three_rates(A, arr)
    rng = np.random.default_rng(SEED)
    sim = np.empty((N_SIM, 3))
    for i in range(N_SIM):
        sim[i] = three_rates(A, rng.permutation(arr))
    return obs, sim


def load_rater_csv(path):
    """Released rater label file (target, rater_label, ...) -> {target: label}."""
    out = {}
    for r in load_master(path):
        lab = (r.get('rater_label') or '').strip()
        if lab:
            out[r['target'].strip()] = lab.upper()
    return out


def build(frozen_dir, sep, rater_files, loader=None):
    """rater_files: (rater1 file name, rater2 file name) inside frozen_dir.
    loader: reads one rater file; the annotation-workbook reader by default."""
    loader = loader or load_xlsm
    master = load_master(sep.join([frozen_dir, 'corpus_master.csv']))
    valid = [r['target'] for r in master if float(r['cmi'] or 0) > 0]
    lab = {
        'author': {r['target']: r['human_label'].strip().upper()
                   for r in master if r['target'] in set(valid)},
        'rater1': loader(sep.join([frozen_dir, rater_files[0]])),
        'rater2': loader(sep.join([frozen_dir, rater_files[1]])),
    }
    lab['claude'] = majority([load_run(sep.join([frozen_dir, f])) for f in CLAUDE_RUNS], valid)
    lab['gemini'] = majority([load_run(sep.join([frozen_dir, f])) for f in GEMINI_RUNS], valid)
    return valid, lab


def k006_values(r):
    sim = r['sim']
    return {
        'k006_obs_exact': r['obs'][0], 'k006_obs_adjacent': r['obs'][1],
        'k006_obs_opposite': r['obs'][2],
        'k006_null_exact': float(sim[:, 0].mean()),
        'k006_null_adjacent': float(sim[:, 1].mean()),
        'k006_null_opposite': float(sim[:, 2].mean()),
        'k006_adj_ci_lo': float(np.percentile(sim[:, 1], 2.5)),
        'k006_adj_ci_hi': float(np.percentile(sim[:, 1], 97.5)),
        'k006_opp_ci_lo': float(np.percentile(sim[:, 2], 2.5)),
        'k006_opp_ci_hi': float(np.percentile(sim[:, 2], 97.5)),
        'k006_p_exact': r['p_exact'], 'k006_p_adjacent': r['p_adj'],
        'k006_p_opposite': r['p_opp'],
    }


def public_mode(bundle_dir, sep):
    """Reader mode. Recompute every owned value from the released bundle
    (corpus_master.csv, rater1_labels.csv, rater2_labels.csv, the ten run files)
    and compare with the recorded values. Writes nothing. Exit 0 only when every
    value matches."""
    print('=== permutation_pairs_compute.py -- public mode ===')
    print('n_sim=%d seed=%d; the SECOND rater of each pair is permuted' % (N_SIM, SEED))
    print('bundle_dir: %s' % bundle_dir)
    valid, lab = build(bundle_dir, sep, RELEASED_RATER_FILES, load_rater_csv)
    fails = checks = 0

    def check(name, ok, detail):
        nonlocal fails, checks
        fails += (not ok)
        checks += 1
        print('  %-30s %s [%s]' % (name, detail, 'OK' if ok else 'FAIL'))

    res = {}
    for a, b in PAIRS:
        ids = [t for t in valid if t in lab[a] and t in lab[b]]
        obs, sim = permute_second(lab[a], lab[b], ids)
        res[(a, b)] = dict(n=len(ids), obs=obs, sim=sim,
                           p_exact=float(np.mean(sim[:, 0] >= obs[0])),
                           p_adj=float(np.mean(sim[:, 1] >= obs[1])),
                           p_opp=float(np.mean(sim[:, 2] <= obs[2])))
    got = k006_values(res[('author', 'rater1')])
    for k in sorted(PUBLIC_K006):
        check(k, agrees(got[k], PUBLIC_K006[k], 4),
              'raw=%-10.6f recorded=%s' % (got[k], PUBLIC_K006[k]))
    for pair in PAIRS:
        check('%s x %s p_polar' % pair, agrees(res[pair]['p_opp'], PUBLIC_P1[pair], 4),
              'raw=%-10.6f recorded=%s' % (res[pair]['p_opp'], PUBLIC_P1[pair]))
    for pair, n in sorted(PUBLIC_N.items()):
        check('%s x %s n' % pair, res[pair]['n'] == n,
              'computed=%d recorded=%d' % (res[pair]['n'], n))
    gm = {'gemini_n': len([t for t in valid if t in lab['gemini']]),
          'gemini_high': sum(1 for t in valid if t in lab['gemini']
                             and lab['gemini'][t] == 'HIGH')}
    for k in sorted(PUBLIC_MISC):
        check(k, gm[k] == PUBLIC_MISC[k],
              'computed=%d recorded=%d' % (gm[k], PUBLIC_MISC[k]))
    print('RESULT: %d checks, %d FAIL' % (checks, fails))
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public_dir',
                    help='released bundle directory; runs the reader check only')
    ap.add_argument('--gate_dir')
    ap.add_argument('--new_dir')
    ap.add_argument('--rater1_file',
                    help='rater 1 annotation workbook file name inside each dir')
    ap.add_argument('--rater2_file',
                    help='rater 2 annotation workbook file name inside each dir')
    ap.add_argument('--log')
    ap.add_argument('--sep', default='/')
    args = ap.parse_args()
    if args.public_dir:
        sys.exit(public_mode(args.public_dir, args.sep))
    for k in ('gate_dir', 'new_dir', 'rater1_file', 'rater2_file', 'log'):
        if getattr(args, k) is None:
            ap.error('--%s is required unless --public_dir is given' % k)
    rater_files = (args.rater1_file, args.rater2_file)

    lines = []
    def out(s=''):
        print(s)
        lines.append(s)

    out('=== permutation_pairs_compute.py ===')
    out('n_sim=%d seed=%d; the SECOND rater of each pair is permuted' % (N_SIM, SEED))
    out('gate_dir: %s' % args.gate_dir)
    out('new_dir : %s' % args.new_dir)
    out()

    def run(frozen_dir, label):
        valid, lab = build(frozen_dir, args.sep, rater_files)
        out('--- %s: valid targets = %d ---' % (label, len(valid)))
        for k in ('author', 'rater1', 'rater2', 'claude', 'gemini'):
            n = len([t for t in valid if t in lab[k]])
            out('  %-8s covers %d of the valid targets' % (k, n))
        res = {}
        for a, b in PAIRS:
            ids = [t for t in valid if t in lab[a] and t in lab[b]]
            obs, sim = permute_second(lab[a], lab[b], ids)
            p_exact = float(np.mean(sim[:, 0] >= obs[0]))
            p_adj = float(np.mean(sim[:, 1] >= obs[1]))
            p_opp = float(np.mean(sim[:, 2] <= obs[2]))
            res[(a, b)] = dict(n=len(ids), obs=obs, sim=sim,
                               p_exact=p_exact, p_adj=p_adj, p_opp=p_opp)
            out('  %-8s x %-8s n=%3d  polar_obs=%.4f  p_polar=%.4f'
                % (a, b, len(ids), obs[2], p_opp))
        gm = {'gemini_n': len([t for t in valid if t in lab['gemini']]),
              'gemini_high': sum(1 for t in valid if t in lab['gemini']
                                 and lab['gemini'][t] == 'HIGH')}
        out('  gemini majority: n=%d HIGH=%d' % (gm['gemini_n'], gm['gemini_high']))
        out()
        return res, gm

    gres, ggm = run(args.gate_dir, 'GATE population')

    r = gres[('author', 'rater1')]
    sim = r['sim']
    got = {
        'k006_obs_exact': (r['obs'][0], 3),
        'k006_obs_adjacent': (r['obs'][1], 3),
        'k006_obs_opposite': (r['obs'][2], 3),
        'k006_null_exact': (float(sim[:, 0].mean()), 3),
        'k006_null_adjacent': (float(sim[:, 1].mean()), 3),
        'k006_null_opposite': (float(sim[:, 2].mean()), 3),
        'k006_adj_ci_lo': (float(np.percentile(sim[:, 1], 2.5)), 3),
        'k006_adj_ci_hi': (float(np.percentile(sim[:, 1], 97.5)), 3),
        'k006_opp_ci_lo': (float(np.percentile(sim[:, 2], 2.5)), 3),
        'k006_opp_ci_hi': (float(np.percentile(sim[:, 2], 97.5)), 3),
        'k006_p_exact': (r['p_exact'], 3),
        'k006_p_adjacent': (r['p_adj'], 4),
        'k006_p_opposite': (r['p_opp'], 4),
    }
    out('=== GATE -- EV-kappa-006 ===')
    fails = 0
    for k in sorted(GATE_K006_PCT):
        raw = got[k][0]
        pct = half_up(half_up(raw, 4) * 100, 1)
        ok = pct == GATE_K006_PCT[k]
        fails += 0 if ok else 1
        out('  %-20s raw=%-12.6f two_stage_pct=%-7s recorded=%-7s [%s]'
            % (k, raw, pct, GATE_K006_PCT[k], 'OK' if ok else 'FAIL'))
    for k in sorted(GATE_K006_P):
        raw = got[k][0]
        exp, places = GATE_K006_P[k]
        ok = agrees(raw, exp, places)
        fails += 0 if ok else 1
        out('  %-20s raw=%-12.6f half_up=%-13s recorded=%-7s [%s]'
            % (k, raw, half_up(raw, places), exp, 'OK' if ok else 'FAIL'))

    out('=== GATE -- EV-p1-001 (polar p per pair) ===')
    for pair in PAIRS:
        exp = GATE_P1[pair]
        places = 4 if exp < 0.01 else 3
        raw = gres[pair]['p_opp']
        ok = agrees(raw, exp, places)
        fails += 0 if ok else 1
        out('  %-8s x %-8s raw=%-12.6f half_up=%-8s recorded=%-8s [%s]'
            % (pair[0], pair[1], raw, half_up(raw, places), exp, 'OK' if ok else 'FAIL'))
    for k in sorted(GATE_MISC):
        ok = ggm[k] == GATE_MISC[k]
        fails += 0 if ok else 1
        out('  %-20s computed=%-9s recorded=%-9s [%s]'
            % (k, ggm[k], GATE_MISC[k], 'OK' if ok else 'FAIL'))

    total = len(GATE_K006_PCT) + len(GATE_K006_P) + len(PAIRS) + len(GATE_MISC)
    out('GATE: %d checks, %d FAIL' % (total, fails))
    out()
    if fails:
        out('=== RESULT ===')
        out('GATE FAILED. No new-population value is emitted.')
        open(args.log, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        sys.exit(1)

    nres, ngm = run(args.new_dir, 'NEW population')
    out('=== NEW POPULATION -- EV-kappa-006 ===')
    r = nres[('author', 'rater1')]
    sim = r['sim']
    out('  observed  exact=%.4f adjacent=%.4f opposite=%.4f' % r['obs'])
    out('  null mean exact=%.4f adjacent=%.4f opposite=%.4f'
        % (sim[:, 0].mean(), sim[:, 1].mean(), sim[:, 2].mean()))
    out('  adjacent CI [%.4f, %.4f]   opposite CI [%.4f, %.4f]'
        % (np.percentile(sim[:, 1], 2.5), np.percentile(sim[:, 1], 97.5),
           np.percentile(sim[:, 2], 2.5), np.percentile(sim[:, 2], 97.5)))
    out('  p_exact=%.4f p_adjacent=%.4f p_opposite=%.4f'
        % (r['p_exact'], r['p_adj'], r['p_opp']))
    out()
    out('=== NEW POPULATION -- EV-p1-001 ===')
    for pair in PAIRS:
        d = nres[pair]
        out('  %-8s x %-8s n=%3d polar=%.4f p=%.4f   (n=202 recorded p=%s)'
            % (pair[0], pair[1], d['n'], d['obs'][2], d['p_opp'], GATE_P1[pair]))
    out('  gemini majority: n=%d HIGH=%d' % (ngm['gemini_n'], ngm['gemini_high']))
    out()
    out('=== RESULT ===')
    out('GATE: %d checks, 0 FAIL. New population emitted.' % total)
    open(args.log, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    sys.exit(0)


if __name__ == '__main__':
    main()
