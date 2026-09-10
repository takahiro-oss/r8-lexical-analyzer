"""
run_stability_compute.py -- canonical computation of LLM run-to-run stability
for R8 preprint v1.9.

Scope: the five-run internal stability figures recorded as EV-stability-001
(Claude) and EV-stability-002 (Gemini), including the two figures the manuscript
prints at L324 (91.3 per cent and 81.2 per cent five-of-five support). Those
entries record "script: not canonicalised"; the computation ran inline in a
judgment-session sandbox on 2026-07-11 and never entered git. This script is that
computation, canonicalised under S294-J spec_02.

Usage:
    <venv>/python.exe scripts/run_stability_compute.py \
        --frozen_dir data/frozen/v1_9r --expect_n 196

Inputs are read exclusively from a frozen directory (Frozen Dataset Principle);
no working-copy path is consulted. Standard library only.

Design notes:
  - Ordinal category order is LOW < MEDIUM < HIGH throughout.
  - A model's population is the intersection of the valid (CMI>0) master targets
    with all five of that model's run files. A target carrying a label outside
    {LOW, MEDIUM, HIGH} in any run is not in that model's population.
  - Krippendorff's alpha is reported for BOTH the ordinal and the interval
    distance functions. S294-J Finding 2: the ledger records the Gemini value as
    "alpha (ordinal) = 0.7059", but 0.7059 is the INTERVAL value; the ordinal
    value is 0.5985 and does not exceed the 0.667 acceptance criterion. The two
    agree for Claude (0.9639 both) because its pooled marginals are near-uniform
    and diverge for Gemini because its marginals are degenerate. Both metrics are
    therefore computed, reported and gated.
  - GATE A validates the estimator before any stability value is computed, by
    reproducing the recorded three-rater values (alpha ordinal 0.1496, alpha
    nominal 0.0785) from --frozen_dir itself. S294-J Finding 1: an earlier draft
    of the alpha implementation was wrong and was caught by exactly this gate, so
    a reproduction of the stability values by an ungated estimator proves nothing.
    The gate reads the human labels; the stability values are computed from the
    LLM run files, so the two do not share an input.
  - GATE C halts on a missing or empty run file rather than silently reducing the
    population. S293-J recorded a join that silently dropped 24 documents and
    produced a plausible n=178 with every downstream value still computing.
"""
import argparse
import csv
import hashlib
import os
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from itertools import combinations

LABELS = ['LOW', 'MEDIUM', 'HIGH']
LABEL_SET = set(LABELS)
INTERVAL_VALUE = {'LOW': 0.0, 'MEDIUM': 1.0, 'HIGH': 2.0}

CLAUDE_RUNS = ['results_claude.csv', 'results_claude_v2.csv', 'results_claude_v3.csv',
               'results_claude_v4.csv', 'results_claude_v5.csv']
GEMINI_RUNS = ['results_gemini_v2.csv', 'results_gemini_v3.csv', 'results_gemini_v4.csv',
               'results_gemini_v5.csv', 'results_gemini_v6.csv']
MODELS = (('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS))

# GATE A. The estimator-validation inputs are the human-label files of the
# directory under test, read read-only. They were the r3 bundle until S384-J;
# that dependency required a second bundle on disk and made the script
# unrunnable for anyone holding only the released one.
GATE_A_CORPUS = 'corpus_master.csv'
GATE_A_RATERS = ['rater1_labels.csv', 'rater2_labels.csv']
GATE_A_LABEL_COL = 'rater_label'
GATE_A_EXPECTED = {'alpha_ordinal': 0.1496, 'alpha_nominal': 0.0785}
GATE_A_TOL = 5e-05

# GATE C. Model population sizes as recorded, keyed by --expect_n. The Claude
# population is expect_n itself; the Gemini population is expect_n less the
# targets absent from every Gemini run (four at both recorded populations).
GEMINI_N_BY_EXPECT = {202: 198, 196: 192}


def half_up(x, places):
    return float(Decimal(repr(float(x))).quantize(Decimal('1.' + '0' * places),
                                                  rounding=ROUND_HALF_UP))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def krippendorff_alpha(units, level, order=LABELS):
    """Krippendorff's alpha over units, each unit a list of that unit's values.

    Do = ( sum_u ( sum over ordered within-unit pairs of delta(a,b) ) / (m_u - 1) ) / n
    De = ( sum_{c,k} n_c n_k delta(c,k) ) / ( n (n-1) )
    alpha = 1 - Do/De

    Units with fewer than two values contribute nothing, as in the reference
    definition. Missing values are simply absent from a unit.
    """
    idx = {v: i for i, v in enumerate(order)}
    K = len(order)
    o = [[0.0] * K for _ in range(K)]
    n_c = [0] * K
    for u in units:
        for v in u:
            n_c[idx[v]] += 1
        m = len(u)
        if m < 2:
            continue
        cnt = Counter(u)
        for c, nc in cnt.items():
            for k, nk in cnt.items():
                o[idx[c]][idx[k]] += (nc * nk - (nc if c == k else 0)) / (m - 1)
    n = sum(n_c)
    if n <= 1:
        return float('nan')

    def delta2(c, k):
        if level == 'nominal':
            return 0.0 if c == k else 1.0
        if level == 'interval':
            d = INTERVAL_VALUE[order[c]] - INTERVAL_VALUE[order[k]]
            return d * d
        lo, hi = (c, k) if c <= k else (k, c)
        s = sum(n_c[g] for g in range(lo, hi + 1)) - (n_c[c] + n_c[k]) / 2.0
        return s * s

    Do = sum(o[c][k] * delta2(c, k) for c in range(K) for k in range(K)) / n
    De = sum(n_c[c] * n_c[k] * delta2(c, k)
             for c in range(K) for k in range(K)) / (n * (n - 1))
    if De == 0:
        return float('nan')
    return 1.0 - Do / De


def read_csv_rows(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def load_run(path):
    """Return (target -> label, stats) for one run file. Labels outside
    {LOW, MEDIUM, HIGH} are dropped; the count of dropped rows is reported."""
    rows = read_csv_rows(path)
    out = {}
    dropped = 0
    dupes = 0
    for r in rows:
        tid = (r.get('target') or '').strip()
        if not tid:
            continue
        lab = (r.get('ai_label') or '').strip().upper()
        if lab not in LABEL_SET:
            dropped += 1
            continue
        if tid in out:
            dupes += 1
            continue
        out[tid] = lab
    return out, {'rows': len(rows), 'usable': len(out), 'dropped': dropped, 'dupes': dupes}


def valid_targets(corpus_path):
    """Row order of the frozen corpus_master, restricted to CMI>0."""
    out = []
    for r in read_csv_rows(corpus_path):
        tid = (r.get('target') or '').strip()
        try:
            cmi = float(r.get('cmi', '0') or 0)
        except ValueError:
            cmi = 0.0
        if tid and cmi > 0:
            out.append(tid)
    return out


def gate_a(fd, emit):
    """Estimator validation against the recorded three-rater values. Runs first
    and halts on failure; nothing else is computed if it fails."""
    emit('=== GATE A -- ESTIMATOR VALIDATION ===')
    corpus_path = os.path.join(fd, GATE_A_CORPUS)
    rater_paths = [os.path.join(fd, n) for n in GATE_A_RATERS]
    for p in [corpus_path] + rater_paths:
        if not os.path.exists(p):
            emit('[HALT] GATE A input missing: %s' % p)
            return False
        emit('  input %-20s sha256=%s' % (os.path.basename(p), sha256_of(p)))

    author = {}
    for r in read_csv_rows(corpus_path):
        tid = (r.get('target') or '').strip()
        lab = (r.get('human_label') or '').strip().upper()
        if tid and lab in LABEL_SET:
            author[tid] = lab
    raters = []
    for p in rater_paths:
        m = {}
        for r in read_csv_rows(p):
            tid = (r.get('target') or '').strip()
            lab = (r.get(GATE_A_LABEL_COL) or '').strip().upper()
            if tid and lab in LABEL_SET:
                m[tid] = lab
        raters.append(m)

    shared = [t for t in author if all(t in m for m in raters)]
    units = [[author[t]] + [m[t] for m in raters] for t in shared]
    emit('  shared targets (author + 2 raters): %d' % len(units))
    if not units:
        emit('[HALT] GATE A has no shared targets')
        return False

    got = {'alpha_ordinal': krippendorff_alpha(units, 'ordinal'),
           'alpha_nominal': krippendorff_alpha(units, 'nominal')}
    ok_all = True
    for key, exp in GATE_A_EXPECTED.items():
        g = got[key]
        ok = abs(half_up(g, 4) - exp) <= GATE_A_TOL
        ok_all = ok_all and ok
        emit('  %-14s computed=%.6f  recorded=%.4f  %s'
             % (key, g, exp, '[OK]' if ok else '[FAIL]'))
    emit('GATE A: %s' % ('PASS' if ok_all else 'FAIL'))
    emit()
    return ok_all


def model_stats(pop, runs):
    """All per-model quantities. runs is a list of five target->label maps."""
    st = {'n': len(pop)}
    polar = 0
    support = Counter()
    pair_polar_cells = 0
    for t in pop:
        labs = [r[t] for r in runs]
        if 'HIGH' in labs and 'LOW' in labs:
            polar += 1
        support[max(Counter(labs).values())] += 1
        c = Counter(labs)
        pair_polar_cells += c['HIGH'] * c['LOW']
    st['polar'] = polar
    st['support'] = support

    pair_agree = []
    for i, j in combinations(range(len(runs)), 2):
        agree = sum(1 for t in pop if runs[i][t] == runs[j][t])
        pair_agree.append(agree / len(pop))
    st['pair_agree'] = pair_agree
    st['pair_mean'] = sum(pair_agree) / len(pair_agree)
    st['pair_min'] = min(pair_agree)
    st['pair_max'] = max(pair_agree)
    # Ordered run-pair cells carrying HIGH and LOW, over all ordered pairs and
    # documents. Both numerator and denominator are ordered, so the rate equals
    # the unordered one.
    n_ordered = len(pair_agree) * 2 * len(pop)
    st['pair_polar'] = (2 * pair_polar_cells) / n_ordered

    units = [[r[t] for r in runs] for t in pop]
    st['alpha_ordinal'] = krippendorff_alpha(units, 'ordinal')
    st['alpha_interval'] = krippendorff_alpha(units, 'interval')
    st['label_dist'] = [Counter(r[t] for t in pop) for r in runs]
    st['pooled_dist'] = Counter(l for u in units for l in u)
    return st


def pct(x):
    return 100.0 * x


class GateB:
    """Recorded-value reproduction. Twenty-one checks.

    The expectations are the n=196 (Claude) and n=192 (Gemini) values recorded in
    EV-r196-067 and EV-r196-068, both VERIFIED, and are transcribed from those
    rows rather than from any run of this script (DEC-083 rule 3).

    The Claude alphas are TWO checks at this population, where they were one at
    n=202. The superseded table gated both metrics against a single recorded
    value (0.9639) because both equalled it; at n=196 the ledger records
    0.965349 (ordinal) and 0.965088 (interval), which differ at the fourth
    decimal the comparison uses, so a single-value check is no longer available.
    The Gemini alphas remain two checks, their metrics having diverged at both
    populations (S294-J Finding 2).
    """

    def __init__(self, emit):
        self.emit = emit
        self.checks = 0
        self.failures = 0

    def _mark(self, ok):
        self.checks += 1
        if not ok:
            self.failures += 1
        return '[OK]' if ok else '[FAIL]'

    def count_pct(self, label, got_count, got_pct, exp_count, exp_pct):
        ok = (got_count == exp_count) and (half_up(got_pct, 1) == half_up(exp_pct, 1))
        self.emit('  %-22s computed=%d (%.4f%%)  recorded=%d (%.1f%%)  %s'
                  % (label, got_count, got_pct, exp_count, exp_pct, self._mark(ok)))

    def value(self, label, got, exp, places, unit=''):
        ok = half_up(got, places) == half_up(exp, places)
        self.emit('  %-22s computed=%.6f%s  recorded=%.*f%s  %s'
                  % (label, got, unit, places, exp, unit, self._mark(ok)))

    def rng(self, label, lo, hi, exp_lo, exp_hi):
        ok = (half_up(lo, 1) == half_up(exp_lo, 1)) and (half_up(hi, 1) == half_up(exp_hi, 1))
        self.emit('  %-22s computed=%.4f%% to %.4f%%  recorded=%.1f%% to %.1f%%  %s'
                  % (label, lo, hi, exp_lo, exp_hi, self._mark(ok)))

    def n(self, label, got, exp):
        ok = got == exp
        self.emit('  %-22s computed=%d  recorded=%d  %s' % (label, got, exp, self._mark(ok)))

    def alpha_pair(self, label, ordinal, interval, exp):
        """One check over both metrics -- used where the ledger records one value
        and both metrics equal it."""
        ok = (half_up(ordinal, 4) == half_up(exp, 4)
              and half_up(interval, 4) == half_up(exp, 4))
        self.emit('  %-22s ordinal=%.6f interval=%.6f  recorded=%.4f  %s'
                  % (label, ordinal, interval, exp, self._mark(ok)))


def run_gate_b(stats, emit):
    g = GateB(emit)
    emit('=== GATE B -- RECORDED VALUE REPRODUCTION (n=196 tables) ===')
    c = stats['Claude']
    emit(' Claude:')
    g.n('n', c['n'], 196)
    g.count_pct('polar', c['polar'], pct(c['polar'] / c['n']), 1, 0.5102)
    for k, ec, ep in ((5, 179, 91.3265), (4, 8, 4.0816), (3, 9, 4.5918)):
        g.count_pct('support %d/5' % k, c['support'].get(k, 0),
                    pct(c['support'].get(k, 0) / c['n']), ec, ep)
    g.value('pair mean', pct(c['pair_mean']), 95.5612, 1, '%')
    g.rng('pair range', pct(c['pair_min']), pct(c['pair_max']), 93.8776, 97.4490)
    g.value('pair polar', pct(c['pair_polar']), 0.1531, 1, '%')
    g.value('alpha ordinal', c['alpha_ordinal'], 0.965349, 4)
    g.value('alpha interval', c['alpha_interval'], 0.965088, 4)

    m = stats['Gemini']
    emit(' Gemini:')
    g.n('n', m['n'], 192)
    g.count_pct('polar', m['polar'], pct(m['polar'] / m['n']), 3, 1.5625)
    for k, ec, ep in ((5, 156, 81.2500), (4, 19, 9.8958), (3, 15, 7.8125), (2, 2, 1.0417)):
        g.count_pct('support %d/5' % k, m['support'].get(k, 0),
                    pct(m['support'].get(k, 0) / m['n']), ec, ep)
    g.value('pair mean', pct(m['pair_mean']), 90.5208, 1, '%')
    g.rng('pair range', pct(m['pair_min']), pct(m['pair_max']), 88.0208, 92.1875)
    g.value('pair polar', pct(m['pair_polar']), 0.5208, 1, '%')
    g.value('alpha ordinal', m['alpha_ordinal'], 0.597619, 4)
    g.value('alpha interval', m['alpha_interval'], 0.704959, 4)

    emit('GATE B: %d checks, %d FAIL' % (g.checks, g.failures))
    emit()
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frozen_dir', required=True)
    ap.add_argument('--expect_n', type=int, default=202,
                    help='expected size of the CMI>0 population; 202 is the '
                         'pre-deduplication frozen set, 196 the deduplicated one')
    args = ap.parse_args()

    fd = args.frozen_dir.rstrip('/\\')
    dirname = os.path.basename(fd)
    log_path = os.path.join(fd, 'audit_run_stability_%s.txt' % dirname)

    lines = []

    def emit(s=''):
        print(s)
        lines.append(s)

    def finish(code):
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        print('audit log: %s' % log_path)
        sys.exit(code)

    emit('=== run_stability_compute.py ===')
    emit('frozen_dir: %s' % fd)
    emit('expect_n:   %d' % args.expect_n)
    emit()

    if not gate_a(fd, emit):
        emit('[HALT] GATE A failed; nothing further computed.')
        finish(1)

    # --- GATE C part 1: declared inputs present and usable ---
    emit('=== GATE C -- DECLARED-INPUT PRESENCE ===')
    corpus_path = os.path.join(fd, 'corpus_master.csv')
    if not os.path.exists(corpus_path):
        emit('[HALT] missing input: %s' % corpus_path)
        finish(1)
    emit('  input %-24s sha256=%s' % ('corpus_master.csv', sha256_of(corpus_path)))

    runs_by_model = {}
    gate_c_ok = True
    for model, names in MODELS:
        loaded = []
        for name in names:
            p = os.path.join(fd, name)
            if not os.path.exists(p):
                emit('[HALT] declared run file missing: %s' % p)
                finish(1)
            labels, st = load_run(p)
            emit('  input %-24s sha256=%s  rows=%d usable=%d dropped=%d dupes=%d'
                 % (name, sha256_of(p), st['rows'], st['usable'], st['dropped'], st['dupes']))
            if st['usable'] < 1:
                emit('[HALT] declared run file yields no usable label: %s' % p)
                finish(1)
            loaded.append(labels)
        runs_by_model[model] = loaded

    valid = valid_targets(corpus_path)
    emit('  valid master targets (CMI>0): %d' % len(valid))
    if len(valid) != args.expect_n:
        emit('[HALT] valid n != %d' % args.expect_n)
        gate_c_ok = False
        emit('GATE C: FAIL')
        finish(1)

    pops = {}
    for model, _ in MODELS:
        runs = runs_by_model[model]
        pops[model] = [t for t in valid if all(t in r for r in runs)]
        missing = len(valid) - len(pops[model])
        emit('  %-7s population = %d  (valid targets absent from at least one run: %d)'
             % (model, len(pops[model]), missing))

    exp_claude = args.expect_n
    exp_gemini = GEMINI_N_BY_EXPECT.get(args.expect_n)
    ok = len(pops['Claude']) == exp_claude
    emit('  Claude population check: computed=%d expected=%d %s'
         % (len(pops['Claude']), exp_claude, '[OK]' if ok else '[FAIL]'))
    gate_c_ok = gate_c_ok and ok
    if exp_gemini is None:
        emit('  Gemini population check: no recorded expectation for --expect_n %d [INFO]'
             % args.expect_n)
    else:
        okg = len(pops['Gemini']) == exp_gemini
        emit('  Gemini population check: computed=%d expected=%d %s'
             % (len(pops['Gemini']), exp_gemini, '[OK]' if okg else '[FAIL]'))
        gate_c_ok = gate_c_ok and okg
    emit('GATE C: %s' % ('PASS' if gate_c_ok else 'FAIL'))
    emit()

    # --- quantities ---
    stats = {}
    for model, _ in MODELS:
        stats[model] = model_stats(pops[model], runs_by_model[model])

    emit('=== QUANTITIES ===')
    for model, names in MODELS:
        s = stats[model]
        emit(' %s (n=%d), runs: %s' % (model, s['n'], ', '.join(names)))
        emit('   polar (HIGH and LOW within the five runs): %d (%.4f%%)'
             % (s['polar'], pct(s['polar'] / s['n'])))
        emit('   support distribution over k:')
        for k in (5, 4, 3, 2, 1):
            if s['support'].get(k, 0) or k >= 2:
                emit('     %d/5  %4d  (%.4f%%)' % (k, s['support'].get(k, 0),
                                                   pct(s['support'].get(k, 0) / s['n'])))
        emit('   pair agreement mean: %.4f%%  range: %.4f%% to %.4f%%'
             % (pct(s['pair_mean']), pct(s['pair_min']), pct(s['pair_max'])))
        emit('     per pair: %s' % ', '.join('%.4f%%' % pct(v) for v in s['pair_agree']))
        emit('   pair polar rate: %.4f%%' % pct(s['pair_polar']))
        emit('   alpha ordinal:  %.6f' % s['alpha_ordinal'])
        emit('   alpha interval: %.6f' % s['alpha_interval'])
        pooled = s['pooled_dist']
        tot = sum(pooled.values())
        emit('   pooled label distribution: %s'
             % ', '.join('%s=%d (%.1f%%)' % (l, pooled.get(l, 0), pct(pooled.get(l, 0) / tot))
                         for l in ('HIGH', 'MEDIUM', 'LOW')))
        emit('   per-run label distribution: %s'
             % ' | '.join('/'.join('%s=%d' % (l, d.get(l, 0)) for l in ('HIGH', 'MEDIUM', 'LOW'))
                          for d in s['label_dist']))
        emit()

    g = run_gate_b(stats, emit)

    emit('=== RESULT ===')
    emit('GATE A: PASS')
    emit('GATE B: %d checks, %d FAIL' % (g.checks, g.failures))
    emit('GATE C: %s' % ('PASS' if gate_c_ok else 'FAIL'))
    emit('ALL PASS' if (g.failures == 0 and gate_c_ok) else 'FAILURES PRESENT')
    finish(0 if (g.failures == 0 and gate_c_ok) else 1)


if __name__ == '__main__':
    main()
