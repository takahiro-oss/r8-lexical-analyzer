"""
human_kappa_compute.py -- canonical computation of human inter-rater reliability
for R8 preprint v1.9.

Scope: author x Rater 1 and author x Rater 2 pairwise agreement,
plus three-rater reliability. Inputs are read exclusively from a frozen directory
(Frozen Dataset Principle); no working-copy path is consulted.

Usage:
    python scripts/human_kappa_compute.py --frozen_dir data/frozen/v1_9 --log audit_human_kappa.txt

Design notes:
  - Population is the CMI>0 valid subset of the frozen corpus_master (n=196).
  - Ordinal category order is LOW < MEDIUM < HIGH throughout.
  - Comparison targets are the evidence-ledger values, not the manuscript's printed
    values. The project records reliability figures to four decimal places in the
    ledger and reports three in the manuscript body; the ledger is the authoritative
    source for any figure that appears in the manuscript.
  - Bootstrap intervals are gated only when seed and iteration count match the
    configuration under which the reported intervals were produced (seed 42,
    10000 iterations, percentile method, documents resampled with replacement).
    Under any other configuration they are printed for information only.
    Interval reproduction additionally depends on the order in which documents are
    presented to the resampler, because the random draw is over positional indices.
    The order used here is the row order of the frozen corpus_master file, which is
    the order under which the recorded intervals were produced. Sorting or otherwise
    reordering the population will change the intervals in the third decimal place
    without any change to the point estimates.
  - Rater labels are read from one of two interchangeable sources, selected by
    what the frozen directory contains: the annotation workbooks where present,
    otherwise the rater label CSVs that the public bundle carries. The CSVs are
    extracted from those same workbooks by scripts/make_rater_csv.py. Both paths
    reproduce all fifteen recorded values, intervals included; because the
    resampler draws on positional indices, interval agreement establishes that
    the two are order-equivalent and not merely value-equivalent.
  - Krippendorff's alpha implementation was validated against the reference
    implementation (PyPI 'krippendorff') on randomised 3-rater data, agreeing to
    floating-point precision for both nominal and ordinal levels. Fleiss' kappa was
    validated against a published worked example.
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix

LABELS = ['LOW', 'MEDIUM', 'HIGH']
SHEET_NAME = '判定シート'
COL_TARGET = 1   # zero-based column index of 対象ID
COL_LABEL = 6    # zero-based column index of あなたの判定

# Rater labels exist in two interchangeable forms. The workbooks are the origin;
# the CSVs are what the public bundle carries, extracted from those same workbooks
# by scripts/make_rater_csv.py. The workbook form is preferred where present, so a
# run inside the project keeps reading the origin rather than a derived copy.
# The workbook filenames carry the raters' names, and the reporting convention for
# this study is the anonymous role designation Rater 1 / Rater 2 throughout. The
# filenames therefore live in an unpublished local configuration file, read when
# present, under their own key. In any clone of the public repository that file is
# absent, WORKBOOK_FILES is None, and the CSV form is the only source.
WORKBOOK_CONFIG_ENV = 'R8_LOCAL_CONFIG'
WORKBOOK_CONFIG_DEFAULT = 'config/publication_safety.local.json'


def load_workbook_files():
    """Return {tag: filename}, or None when no local configuration is available."""
    path = os.environ.get(WORKBOOK_CONFIG_ENV) or WORKBOOK_CONFIG_DEFAULT
    if not os.path.exists(path):
        return None
    raw = open(path, 'rb').read().decode('utf-8-sig')
    files = json.loads(raw).get('rater_workbook_files')
    if not files:
        return None
    return {str(k): str(v) for k, v in files.items()}


WORKBOOK_FILES = load_workbook_files()
CSV_FILES = {'rater1': 'rater1_labels.csv', 'rater2': 'rater2_labels.csv'}
CSV_LABEL_COL = 'rater_label'

# Recorded values. Key -> (expected, decimal places at which it is recorded).
# UPDATED S365-J to the DEC-072 deduplicated population, n=196. Source, and the
# only source: evidence_ledger.md row EV-r196-056, which supersedes
# EV-humankappa-001 and records all eleven at six decimal places -- hence
# places=6, where the superseded n=202 table used 4 and 3.
# The n=202 values this table held were:
#   0.0782 / 0.2197 / 0.1260 / 0.2165 / 0.381 / 0.564 / 0.0718 / 0.3465 /
#   0.1390 / 0.0743 / 0.0727
# They are NOT wrong; they are the correct values for a population the
# manuscript no longer reports. Leaving them in place made this script report
# 11 FAIL against its own correct output, measured S365-J.
LEDGER_EXPECTED = {
    'kappa_unweighted_rater1': (0.094178, 6),
    'kappa_unweighted_rater2': (0.196609, 6),
    'kappa_linear_rater1':     (0.142790, 6),
    'kappa_linear_rater2':     (0.197838, 6),
    'agreement_rater1':        (0.392857, 6),
    'agreement_rater2':        (0.551020, 6),
    'pabak_rater1':            (0.089286, 6),
    'pabak_rater2':            (0.326531, 6),
    'alpha_ordinal':           (0.149642, 6),
    'alpha_nominal':           (0.078536, 6),
    'fleiss_kappa':            (0.076966, 6),
}

# Intervals as recorded. Gated when the bootstrap configuration matches -- see design notes.
CI_REFERENCE_SEED = 42
CI_REFERENCE_NBOOT = 10000

# Key -> (lower, upper, decimal places at which the ledger records them).
# The precision field mirrors LEDGER_EXPECTED. It is required, not cosmetic: the
# rounding convention in data/frozen/v1_9/FROZEN_MANIFEST.md computes to four
# digits before rounding to three for reporting, so a value recorded at four
# digits must be compared at four. Comparing a four-digit record at three digits
# rounds it a second time and can shift the last digit.
LEDGER_CI_REFERENCE = {
    # UPDATED S365-J to n=196. Source, and the only source: evidence_ledger.md
    # row EV-r196-057, which supersedes EV-humankappa-002 and records all eight
    # endpoints at four decimal places -- hence places=4 throughout, where the
    # first four keys previously used 3. The last four also appear individually
    # at EV-r196-004, -007, -008 and -009, which agree with EV-r196-057.
    # The n=202 intervals this table held were:
    #   unweighted R1 [-0.006, 0.166]; unweighted R2 [0.107, 0.329];
    #   linear R1 [0.043, 0.210]; linear R2 [0.103, 0.328];
    #   PABAK R1 [-0.0248, 0.1757]; PABAK R2 [0.2426, 0.4505];
    #   alpha ordinal [0.0497, 0.2255]; Fleiss [0.0091, 0.1353]
    # ONE SUBSTANTIVE CHANGE BEYOND THE DIGITS: the Rater 1 unweighted interval
    # no longer crosses zero at n=196 (EV-r196-057).
    'kappa_unweighted_rater1': (0.0070, 0.1835, 4),
    'kappa_unweighted_rater2': (0.0833, 0.3099, 4),
    'kappa_linear_rater1':     (0.0584, 0.2267, 4),
    'kappa_linear_rater2':     (0.0824, 0.3128, 4),
    'pabak_rater1':            (-0.0102, 0.1964, 4),
    'pabak_rater2':            (0.2194, 0.4337, 4),
    'alpha_ordinal':           (0.0574, 0.2383, 4),
    'fleiss_kappa':            (0.0102, 0.1428, 4),
}


def half_up(x, places):
    return float(Decimal(repr(float(x))).quantize(Decimal('1.' + '0' * places),
                                                  rounding=ROUND_HALF_UP))


def krippendorff_alpha(units, level, order):
    """units: sequence of per-unit label lists. Missing values are simply absent."""
    idx = {v: i for i, v in enumerate(order)}
    K = len(order)
    o = [[0.0] * K for _ in range(K)]
    for u in units:
        m = len(u)
        if m < 2:
            continue
        cnt = Counter(u)
        for c, nc in cnt.items():
            for k, nk in cnt.items():
                o[idx[c]][idx[k]] += (nc * nk - (nc if c == k else 0)) / (m - 1)
    n_c = [sum(row) for row in o]
    n = sum(n_c)
    if n <= 1:
        return float('nan')
    e = [[(n_c[c] * n_c[k] - (n_c[c] if c == k else 0)) / (n - 1)
          for k in range(K)] for c in range(K)]

    def delta2(c, k):
        if level == 'nominal':
            return 0.0 if c == k else 1.0
        lo, hi = (c, k) if c <= k else (k, c)
        s = sum(n_c[g] for g in range(lo, hi + 1)) - (n_c[c] + n_c[k]) / 2.0
        return s * s

    Do = sum(o[c][k] * delta2(c, k) for c in range(K) for k in range(K))
    De = sum(e[c][k] * delta2(c, k) for c in range(K) for k in range(K))
    if De == 0:
        return float('nan')
    return 1.0 - Do / De


def fleiss_kappa(units, categories):
    N = len(units)
    n = len(units[0])
    idx = {c: i for i, c in enumerate(categories)}
    col = [0] * len(categories)
    P = []
    for u in units:
        if len(u) != n:
            raise ValueError('fleiss_kappa requires an equal number of raters per unit')
        cnt = [0] * len(categories)
        for v in u:
            cnt[idx[v]] += 1
        for i, c in enumerate(cnt):
            col[i] += c
        P.append((sum(c * c for c in cnt) - n) / (n * (n - 1)))
    Pbar = sum(P) / N
    pj = [c / (N * n) for c in col]
    Pe = sum(p * p for p in pj)
    return (Pbar - Pe) / (1 - Pe)


def load_sheet_labels(path):
    # openpyxl is imported here rather than at module level: it is needed only by
    # this branch, which requires the annotation workbooks. Those are not part of
    # the public data bundle, so a reader working from the bundle takes the CSV
    # branch and must not be made to install a package this run never uses.
    import openpyxl
    wb = openpyxl.load_workbook(path, keep_vba=True, data_only=True)
    ws = wb[SHEET_NAME]
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[COL_TARGET] is None:
            break
        tid = str(row[COL_TARGET]).strip()
        val = row[COL_LABEL]
        val = '' if val is None else str(val).strip().upper()
        out[tid] = val
    wb.close()
    return out


def load_csv_labels(path):
    """Return target -> label from a rater CSV, in the shape load_sheet_labels returns."""
    out = {}
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if CSV_LABEL_COL not in (reader.fieldnames or []):
            raise SystemExit('[HALT] %s lacks column %s (found: %s)'
                             % (path, CSV_LABEL_COL, reader.fieldnames))
        for row in reader:
            tid = (row['target'] or '').strip()
            if not tid:
                continue
            val = row[CSV_LABEL_COL]
            out[tid] = '' if val is None else str(val).strip().upper()
    return out


def resolve_rater_source(fd):
    """Return (source_name, {tag: path}) or halt.

    A source counts only when BOTH of its files are present; a half-present set
    falls through rather than loading one rater from each form.
    """
    wb = {t: fd + '/' + n for t, n in WORKBOOK_FILES.items()} if WORKBOOK_FILES else {}
    cs = {t: fd + '/' + n for t, n in CSV_FILES.items()}
    if wb and all(os.path.exists(p) for p in wb.values()):
        return 'workbook', wb
    if all(os.path.exists(p) for p in cs.values()):
        return 'csv', cs
    wb_desc = sorted(WORKBOOK_FILES.values()) if WORKBOOK_FILES else 'unconfigured'
    raise SystemExit('[HALT] no complete rater label source in %s; expected either %s or %s'
                     % (fd, wb_desc, sorted(CSV_FILES.values())))


def pabak(po, k=3):
    return (k * po - 1) / (k - 1)


def bootstrap_ci(a, b, weights, seed, n_boot):
    rng = np.random.default_rng(seed)
    A, B = np.array(a), np.array(b)
    idx = np.arange(len(A))
    vals = []
    for _ in range(n_boot):
        s = rng.choice(idx, size=len(idx), replace=True)
        try:
            vals.append(cohen_kappa_score(A[s], B[s], labels=LABELS, weights=weights))
        except Exception:
            continue
    if not vals:
        return float('nan'), float('nan')
    return tuple(np.percentile(vals, [2.5, 97.5]))


def bootstrap_ci_stat(n, statfn, seed, n_boot):
    """Percentile bootstrap over positional indices, for statistics that are not
    a two-argument Cohen's kappa.

    statfn receives the resampled index array and returns a float. Undefined
    replicates are NOT discarded: they enter as NaN and are counted, so that a
    degenerate population produces a visibly undefined interval instead of a
    narrower one computed from whichever replicates happened to be defined.

    The resampling stream is identical to bootstrap_ci: the generator is seeded
    per call and draws size-n index arrays, so intervals produced here are drawn
    from the same resamples as the intervals produced there.
    """
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    vals = []
    n_nan = 0
    for _ in range(n_boot):
        s = rng.choice(idx, size=n, replace=True)
        try:
            v = float(statfn(s))
        except Exception:
            v = float('nan')
        if np.isnan(v):
            n_nan += 1
        vals.append(v)
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return float(lo), float(hi), n_nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frozen_dir', required=True)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--n_boot', type=int, default=10000)
    ap.add_argument('--expect_n', type=int, default=196,
                    help='expected size of the CMI>0 population; 196 is the '
                         'deduplicated frozen set, 202 the pre-deduplication one')
    ap.add_argument('--log', default=None)
    args = ap.parse_args()

    lines = []

    def emit(s=''):
        print(s)
        lines.append(s)

    fd = args.frozen_dir.rstrip('/\\')
    corpus_path = fd + '/corpus_master.csv'
    source, rater_paths = resolve_rater_source(fd)
    loader = load_sheet_labels if source == 'workbook' else load_csv_labels

    with open(corpus_path, encoding='utf-8-sig') as f:
        corpus = {r['target']: r for r in csv.DictReader(f)}

    valid = []
    for tid, r in corpus.items():
        try:
            cmi = float(r.get('cmi', '0') or 0)
        except ValueError:
            cmi = 0.0
        if cmi > 0:
            valid.append(tid)

    r1 = loader(rater_paths['rater1'])
    r2 = loader(rater_paths['rater2'])

    emit('=== Population ===')
    emit('frozen_dir: %s' % fd)
    emit('rater label source: %s' % source)
    for tag in ('rater1', 'rater2'):
        emit('  %s <- %s' % (tag, rater_paths[tag]))
    emit('valid (CMI>0) n = %d' % len(valid))
    if len(valid) != args.expect_n:
        emit('[HALT] valid n != %d' % args.expect_n)
        sys.exit(1)

    missing = [t for t in valid if t not in r1 or t not in r2]
    if missing:
        emit('[HALT] targets absent from a rater sheet: %d %s' % (len(missing), missing[:20]))
        sys.exit(1)

    author = [corpus[t]['human_label'].strip().upper() for t in valid]
    lab1 = [r1[t] for t in valid]
    lab2 = [r2[t] for t in valid]

    bad = sorted({v for v in author + lab1 + lab2} - set(LABELS))
    if bad:
        emit('[HALT] unexpected label values present: %s' % bad)
        sys.exit(1)
    emit('label value set: %s (as expected)' % sorted(set(author + lab1 + lab2)))
    emit('author  distribution: %s' % dict(Counter(author)))
    emit('rater1  distribution: %s' % dict(Counter(lab1)))
    emit('rater2  distribution: %s' % dict(Counter(lab2)))
    emit()

    results = {}
    for tag, lab in (('rater1', lab1), ('rater2', lab2)):
        po = sum(x == y for x, y in zip(author, lab)) / len(author)
        results['agreement_' + tag] = po
        results['kappa_unweighted_' + tag] = cohen_kappa_score(author, lab, labels=LABELS)
        results['kappa_linear_' + tag] = cohen_kappa_score(author, lab, labels=LABELS,
                                                           weights='linear')
        results['pabak_' + tag] = pabak(po)
        cm = confusion_matrix(author, lab, labels=LABELS)
        emit('=== author x %s (n=%d) ===' % (tag, len(author)))
        emit('confusion matrix (rows=author, cols=%s, order=%s):' % (tag, LABELS))
        for name, row in zip(LABELS, cm):
            emit('  %-7s %s' % (name, [int(v) for v in row]))
        emit()

    units = [[author[i], lab1[i], lab2[i]] for i in range(len(author))]
    results['alpha_ordinal'] = krippendorff_alpha(units, 'ordinal', LABELS)
    results['alpha_nominal'] = krippendorff_alpha(units, 'nominal', LABELS)
    results['fleiss_kappa'] = fleiss_kappa(units, LABELS)

    emit('=== LEDGER_EXPECTED verification (round-half-up at recorded precision) ===')
    failures = 0
    ci_failures = 0
    for key in LEDGER_EXPECTED:
        exp, places = LEDGER_EXPECTED[key]
        got = results[key]
        ok = half_up(got, places) == half_up(exp, places)
        failures += 0 if ok else 1
        emit('  %-26s computed=%.6f  recorded=%.4f  %s'
             % (key, got, exp, '[OK]' if ok else '[FAIL]'))
    emit()

    ci_gated = (args.seed == CI_REFERENCE_SEED and args.n_boot == CI_REFERENCE_NBOOT)
    emit('=== Bootstrap intervals (%s) ===' % ('GATED' if ci_gated else 'INFORMATIONAL'))
    emit('seed=%d n_boot=%d; percentile method, resampling documents with replacement'
         % (args.seed, args.n_boot))
    if not ci_gated:
        emit('Configuration differs from the reference (seed=%d, n_boot=%d); intervals are'
             % (CI_REFERENCE_SEED, CI_REFERENCE_NBOOT))
        emit('printed for information only and do not contribute to the result.')
    for tag in ('rater1', 'rater2'):
        for weights, key in ((None, 'kappa_unweighted_' + tag), ('linear', 'kappa_linear_' + tag)):
            lo, hi = bootstrap_ci(author, lab1 if tag == 'rater1' else lab2,
                                  weights, args.seed, args.n_boot)
            ref = LEDGER_CI_REFERENCE[key]
            pl = ref[2]
            ok = (half_up(lo, pl) == half_up(ref[0], pl)
                  and half_up(hi, pl) == half_up(ref[1], pl))
            if ci_gated:
                ci_failures += 0 if ok else 1
                mark = '[OK]' if ok else '[FAIL]'
            else:
                mark = '[INFO]'
            emit('  %-26s computed=[%.4f, %.4f]  recorded=[%.*f, %.*f]  %s'
                 % (key, lo, hi, pl, ref[0], pl, ref[1], mark))

    # Added S290-J. Second loop, for the statistics that are not a pairwise
    # Cohen's kappa. The loop above is untouched; these calls cannot perturb it
    # because bootstrap_ci seeds its generator per call.
    def _po_stat(lab):
        arr_a = np.array(author)
        arr_b = np.array(lab)

        def f(s):
            return pabak(float(np.mean(arr_a[s] == arr_b[s])))
        return f

    def _alpha_stat(s):
        return krippendorff_alpha([units[i] for i in s], 'ordinal', LABELS)

    def _fleiss_stat(s):
        return fleiss_kappa([units[i] for i in s], LABELS)

    n_pop = len(author)
    added = (('pabak_rater1', _po_stat(lab1)),
             ('pabak_rater2', _po_stat(lab2)),
             ('alpha_ordinal', _alpha_stat),
             ('fleiss_kappa', _fleiss_stat))
    for key, fn in added:
        lo, hi, n_nan = bootstrap_ci_stat(n_pop, fn, args.seed, args.n_boot)
        ref = LEDGER_CI_REFERENCE[key]
        pl = ref[2]
        ok = (half_up(lo, pl) == half_up(ref[0], pl)
              and half_up(hi, pl) == half_up(ref[1], pl))
        if ci_gated:
            ci_failures += 0 if ok else 1
            mark = '[OK]' if ok else '[FAIL]'
        else:
            mark = '[INFO]'
        emit('  %-26s computed=[%.4f, %.4f]  recorded=[%.*f, %.*f]  %s  undefined=%d'
             % (key, lo, hi, pl, ref[0], pl, ref[1], mark, n_nan))
    emit()

    total_checks = len(LEDGER_EXPECTED) + (len(LEDGER_CI_REFERENCE) if ci_gated else 0)
    total_failures = failures + ci_failures
    emit('=== RESULT ===')
    emit('point estimates: %d checks, %d FAIL' % (len(LEDGER_EXPECTED), failures))
    if ci_gated:
        emit('intervals:       %d checks, %d FAIL' % (len(LEDGER_CI_REFERENCE), ci_failures))
    else:
        emit('intervals:       not gated under this configuration')
    emit('TOTAL: %d checks, %d FAIL' % (total_checks, total_failures))
    emit('ALL PASS' if total_failures == 0 else 'FAILURES PRESENT')

    if args.log:
        with open(args.log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    sys.exit(0 if total_failures == 0 else 1)


if __name__ == '__main__':
    main()
