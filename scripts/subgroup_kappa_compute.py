"""
subgroup_kappa_compute.py -- language-stratified human inter-rater reliability
for R8 preprint v1.9.

Purpose. The OSF registration (49qrd) states that the primary kappa population
excludes English-language documents and that 10 English-language documents are
analysed as a separate sub-group for supplementary reporting. The implemented
exclusion filter selects on CMI > 0 rather than on language. Three English
documents scored exactly 0.00 and were excluded; ten scored a floor value near
14 and were retained. The primary population of 196 therefore consists of 187
Japanese documents and 9 English documents. This script measures all three
populations so that the size of that deviation can be stated numerically.

This script does NOT modify scripts/human_kappa_compute.py. It imports the
canonical estimators from it, so that every figure reported here is produced by
the same code path that produced the recorded values.

Usage:
    python scripts/subgroup_kappa_compute.py --frozen_dir data/frozen/v1_9 \
        --population all --log audit_subgroup_all.txt

    --population all : CMI>0, n=196 (187 JA + 9 EN). Gated against the ledger.
    --population ja  : CMI>0 and is_english=0, n=187. No recorded values exist.
    --population en  : CMI>0 and is_english=1, n=9.   No recorded values exist.

Constraints on the en population, fixed before measurement:
  - n=9 is too small for the point estimate to be interpreted. It is reported
    with a bootstrap interval and is not to be characterised in the manuscript
    as evidence for or against agreement in English.
  - Bootstrap replicates in which a resample yields a degenerate label
    distribution produce an undefined kappa. The count of undefined replicates
    is reported alongside the interval; an interval computed from a small
    fraction of successful replicates is not a percentile interval of the
    intended sampling distribution and is labelled accordingly.
  - The en population is a SUBSET of the all population, not an independent
    additional sample. Its estimate is not statistically independent of the
    primary estimate.
"""
import argparse
import csv
import sys
import warnings
from collections import Counter

import numpy as np
from sklearn.metrics import cohen_kappa_score, confusion_matrix

# At n=9 a large fraction of bootstrap resamples are degenerate, and sklearn
# emits a RuntimeWarning for each undefined kappa. Left unsuppressed these
# warnings flood the log and make the report unreadable. The undefined cases are
# not discarded silently: they are counted and reported by bootstrap_ci_counted.
warnings.filterwarnings('ignore', category=RuntimeWarning,
                        module='sklearn.metrics._classification')
np.seterr(invalid='ignore', divide='ignore')

import human_kappa_compute as canon
from human_kappa_compute import (LABELS, half_up, krippendorff_alpha,
                                 fleiss_kappa, load_sheet_labels,
                                 load_csv_labels, resolve_rater_source, pabak)

EXPECTED_N = {'all': 196, 'ja': 187, 'en': 9}


def bootstrap_ci_counted(a, b, weights, seed, n_boot):
    """As canon.bootstrap_ci, but also returns how many replicates were usable.

    A replicate is unusable when the resampled pair yields an undefined kappa
    (NaN), which occurs when the resample is degenerate. canon.bootstrap_ci
    silently drops raised exceptions but retains NaN values; at n=9 the NaN
    case dominates, so it is counted explicitly here.
    """
    rng = np.random.default_rng(seed)
    A, B = np.array(a), np.array(b)
    idx = np.arange(len(A))
    vals = []
    undefined = 0
    for _ in range(n_boot):
        s = rng.choice(idx, size=len(idx), replace=True)
        try:
            v = cohen_kappa_score(A[s], B[s], labels=LABELS, weights=weights)
        except Exception:
            undefined += 1
            continue
        if np.isnan(v):
            undefined += 1
            continue
        vals.append(v)
    if not vals:
        return float('nan'), float('nan'), 0, undefined
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return lo, hi, len(vals), undefined


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frozen_dir', required=True)
    ap.add_argument('--population', choices=['all', 'ja', 'en'], default='all')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--n_boot', type=int, default=10000)
    ap.add_argument('--log', default=None)
    args = ap.parse_args()

    lines = []

    def emit(s=''):
        print(s)
        lines.append(s)

    fd = args.frozen_dir.rstrip('/\\')
    with open(fd + '/corpus_master.csv', encoding='utf-8-sig') as f:
        corpus = {r['target']: r for r in csv.DictReader(f)}

    def cmi_of(r):
        try:
            return float(r.get('cmi', '0') or 0)
        except ValueError:
            return 0.0

    def is_en(r):
        return str(r.get('is_english', '')).strip() == '1'

    valid = [t for t, r in corpus.items() if cmi_of(r) > 0]
    if len(valid) != 196:
        emit('[HALT] CMI>0 population is %d, expected 196' % len(valid))
        sys.exit(1)

    if args.population == 'all':
        pop = valid
    elif args.population == 'ja':
        pop = [t for t in valid if not is_en(corpus[t])]
    else:
        pop = [t for t in valid if is_en(corpus[t])]

    want = EXPECTED_N[args.population]
    if len(pop) != want:
        emit('[HALT] population %s is %d, expected %d' % (args.population, len(pop), want))
        sys.exit(1)

    source, rater_paths = resolve_rater_source(fd)
    loader = load_sheet_labels if source == 'workbook' else load_csv_labels
    r1 = loader(rater_paths['rater1'])
    r2 = loader(rater_paths['rater2'])
    missing = [t for t in pop if t not in r1 or t not in r2]
    if missing:
        emit('[HALT] targets absent from a rater sheet: %d %s' % (len(missing), missing[:20]))
        sys.exit(1)

    author = [corpus[t]['human_label'].strip().upper() for t in pop]
    lab1 = [r1[t] for t in pop]
    lab2 = [r2[t] for t in pop]

    bad = sorted({v for v in author + lab1 + lab2} - set(LABELS))
    if bad:
        emit('[HALT] unexpected label values present: %s' % bad)
        sys.exit(1)

    emit('=== Population: %s ===' % args.population)
    emit('frozen_dir: %s' % fd)
    emit('rater label source: %s' % source)
    emit('n = %d  (of the CMI>0 valid set of %d)' % (len(pop), len(valid)))
    if args.population == 'en':
        emit('NOTE: this population is a SUBSET of the primary population, not an')
        emit('      independent additional sample. n=%d; the point estimate is' % len(pop))
        emit('      reported but is not to be interpreted.')
    emit('targets: %s' % (sorted(pop) if len(pop) <= 20 else '(%d targets, not listed)' % len(pop)))
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
        emit('  observed agreement %.6f   kappa(unw) %.6f   kappa(lin) %.6f   PABAK %.6f'
             % (po, results['kappa_unweighted_' + tag],
                results['kappa_linear_' + tag], results['pabak_' + tag]))
        emit()

    units = [[author[i], lab1[i], lab2[i]] for i in range(len(author))]
    results['alpha_ordinal'] = krippendorff_alpha(units, 'ordinal', LABELS)
    results['alpha_nominal'] = krippendorff_alpha(units, 'nominal', LABELS)
    results['fleiss_kappa'] = fleiss_kappa(units, LABELS)
    emit('=== three-rater (author + rater1 + rater2), n=%d ===' % len(units))
    emit('  alpha_ordinal %.6f   alpha_nominal %.6f   fleiss_kappa %.6f'
         % (results['alpha_ordinal'], results['alpha_nominal'], results['fleiss_kappa']))
    emit()

    emit('=== Bootstrap intervals ===')
    emit('seed=%d n_boot=%d; percentile method, resampling documents with replacement'
         % (args.seed, args.n_boot))
    for tag in ('rater1', 'rater2'):
        lab = lab1 if tag == 'rater1' else lab2
        for weights, key in ((None, 'kappa_unweighted_' + tag),
                             ('linear', 'kappa_linear_' + tag)):
            lo, hi, nok, nbad = bootstrap_ci_counted(author, lab, weights,
                                                     args.seed, args.n_boot)
            flag = ''
            if nbad > 0:
                frac = 100.0 * nok / args.n_boot
                flag = '  [%d/%d usable, %.1f%%; %d undefined]' % (nok, args.n_boot, frac, nbad)
            emit('  %-26s point=%.6f  CI=[%.4f, %.4f]%s'
                 % (key, results[key], lo, hi, flag))
    emit()

    gate_fail = 0
    if args.population == 'all':
        emit('=== Regression gate against LEDGER_EXPECTED ===')
        emit('(population "all" must reproduce the recorded values exactly)')
        for key, (exp, places) in canon.LEDGER_EXPECTED.items():
            got = results[key]
            ok = half_up(got, places) == half_up(exp, places)
            gate_fail += 0 if ok else 1
            emit('  %-26s computed=%.6f  recorded=%.4f  %s'
                 % (key, got, exp, '[OK]' if ok else '[FAIL]'))
        emit('regression: %d checks, %d FAIL' % (len(canon.LEDGER_EXPECTED), gate_fail))
    else:
        emit('=== Regression gate ===')
        emit('Not applicable: no recorded values exist for population "%s".'
             % args.population)
    emit()

    emit('=== RESULT ===')
    emit('population %s  n=%d  regression FAIL=%d' % (args.population, len(pop), gate_fail))
    emit('ALL PASS' if gate_fail == 0 else 'FAILURES PRESENT')

    if args.log:
        with open(args.log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')

    sys.exit(0 if gate_fail == 0 else 1)


if __name__ == '__main__':
    main()
