"""recount_corpus_r196.py -- corpus_master-level recounts for the Pending 97
recomputation, gated at n=202 before any n=196 value is emitted.

CANONICAL PRODUCER for: EV-cmi0-001, EV-sn-004, EV-fnwidth-001, EV-prf-001,
EV-perf-001, EV-perf-002, the Section 4.x specificity figure, and the genre
half of EV-kappa-004.

WHY THIS SCRIPT EXISTS. Each of the above was computed by an in-session inline
script that was never saved (Pending 106). The values are recorded in the
evidence ledger, so a reconstruction can be GATED rather than trusted: this
script asserts every recorded n=202 value before it prints a single n=196
value, and exits non-zero if any assertion fails.

verify_public_bundle.py L131-138 computes the same exact-match / within-one
quantity. That code is a VERIFICATION layer over a released bundle, not the
producer of the figure; its expected values are constants to be re-set when the
r4 bundle is generated. This script is the producer. The two are expected to
agree, and disagreement is a defect in the bundle, not in this script.

Usage:
    python scripts/recount_corpus_r196.py \
        --gate_master data/frozen/v1_9/corpus_master.csv \
        --new_master  data/frozen/v1_9r/corpus_master.csv \
        --xlsm        <rater 1 annotation workbook .xlsm> \
        --log         data/frozen/v1_9r/audit_recount_corpus_v1_9r.txt

Reader mode, the only mode that runs on the released data:
    python scripts/recount_corpus_r196.py --public_master corpus_master.csv \\
        --rater1 rater1_labels.csv

Exit 0 only when every GATE assertion passes.
"""
import argparse
import csv
import hashlib
import io
import sys
from collections import Counter

from scipy.stats import mannwhitneyu

LS = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}

# The 13 scored columns named by EV-fnwidth-001. beauty_diet is excluded there
# and is excluded here; the exclusion is the ledger's, not this script's.
CATS13 = ['authority', 'emotional', 'logical', 'statistical', 'hype', 'clickbait',
          'propaganda', 'fear', 'enemy_frame', 'disclaimer_exploit',
          'anonymous_authority', 'naked_number', 'sexual_induction']

# Recorded n=202 values. Sources, per key:
#   cmi0_*        EV-cmi0-001
#   sn004_*       EV-sn-004
#   fnw_*         EV-fnwidth-001
#   prf_*         EV-prf-001 and verify_public_bundle.py L101-138
#   perf_*        EV-perf-001, EV-perf-002
#   spec_*        manuscript "high-specificity (98.8%)"
#   k004_*        EV-kappa-004
GATE = {
    'cmi0_n': 9,
    'cmi0_targets': ['AD_045', 'AD_046', 'SN_011', 'SN_014', 'sn230', 'sn233',
                     'web134', 'web141', 'web194'],
    'cmi0_english': ['AD_045', 'AD_046', 'web194'],
    'cmi0_error_nonempty': [],
    'sn004_n': 6,
    'sn004_targets': ['note126', 'note128', 'sn231', 'sn232', 'web144', 'web207'],
    'sn004_cmi_lo': 12.0, 'sn004_cmi_hi': 45.7,
    'fnw_high': 120, 'fnw_tp': 42, 'fnw_fn': 78,
    'fnw_cat_tp': 7.31, 'fnw_cat_fn': 5.13,
    'fnw_cat_u': 2707, 'fnw_cat_rb': 0.653,
    'fnw_den_tp': 0.756, 'fnw_den_fn': 0.699,
    'fnw_den_u': 1972, 'fnw_den_rb': 0.204,
    'fnw_min_tp': 4,
    'prf_tp': 42, 'prf_fp': 1, 'prf_fp_id': ['note223'],
    'prf_fn_valid': 78, 'prf_fn_all': 79,
    'prf_precision': 97.7, 'prf_recall_all': 34.7, 'prf_f1_all': 51.2,
    'prf_recall_valid': 35.0, 'prf_f1_valid': 51.5,
    'perf_exact_n': 59, 'perf_exact_pct': 29.2,
    'perf_w1_n': 151, 'perf_w1_pct': 74.8,
    'spec_tn': 81, 'spec_pct': 98.8,
    'hml_all': (121, 76, 14), 'hml_valid': (120, 70, 12),
    'k004_polar': 31, 'k004_hl': 29, 'k004_lh': 2,
    'k004_lh_targets': ['AD_052', 'web154'],
    'k004_top_genre_n': 17, 'k004_top_genre_pct': 54.8,
    'k004_cult_n': 5,
}


# PUBLIC MODE expectations at the deduplicated population (n_total 205, n_valid
# 196), transcribed from the ledger BEFORE any public-mode run existed so that the
# check is not fitted to its own output. Same keys as GATE. Sources, per key:
#   cmi0_*        EV-r196-054        sn004_*   EV-r196-066
#   fnw_*         EV-r196-055        prf_*     EV-r196-065
#   perf_*        EV-r196-063, -064  spec_*    EV-perf-003
#   hml_*         EV-r196-029, -064  k004_*    EV-r196-058
PUBLIC_EXPECT = {
    'cmi0_n': 9,
    'cmi0_targets': ['AD_045', 'AD_046', 'SN_011', 'SN_014', 'sn230', 'sn233',
                     'web134', 'web141', 'web194'],
    'cmi0_english': ['AD_045', 'AD_046', 'web194'],
    'cmi0_error_nonempty': [],
    'sn004_n': 6,
    'sn004_targets': ['note126', 'note128', 'sn231', 'sn232', 'web144', 'web207'],
    'sn004_cmi_lo': 12.0, 'sn004_cmi_hi': 45.7,
    'fnw_high': 117, 'fnw_tp': 41, 'fnw_fn': 76,
    'fnw_cat_tp': 7.29, 'fnw_cat_fn': 5.12,
    'fnw_cat_u': 2569.5, 'fnw_cat_rb': 0.649,
    'fnw_den_tp': 0.755, 'fnw_den_fn': 0.699,
    'fnw_den_u': 1862.0, 'fnw_den_rb': 0.195,
    'fnw_min_tp': 4,
    'prf_tp': 41, 'prf_fp': 1, 'prf_fp_id': ['note223'],
    'prf_fn_valid': 76, 'prf_fn_all': 77,
    'prf_precision': 97.6, 'prf_recall_all': 34.7, 'prf_f1_all': 51.2,
    'prf_recall_valid': 35.0, 'prf_f1_valid': 51.6,
    'perf_exact_n': 58, 'perf_exact_pct': 29.6,
    'perf_w1_n': 146, 'perf_w1_pct': 74.5,
    'spec_tn': 78, 'spec_pct': 98.7,
    'hml_all': (118, 73, 14), 'hml_valid': (117, 67, 12),
    'k004_polar': 29, 'k004_hl': 27, 'k004_lh': 2,
    'k004_lh_targets': ['AD_052', 'web154'],
    'k004_top_genre_n': 17, 'k004_top_genre_pct': 58.6,
    'k004_cult_n': 5,
}


def load_rater_csv(path):
    """Released rater label file (target, rater_label, ...) -> {target: label}."""
    out = {}
    for r in csv.DictReader(io.StringIO(open(path, 'rb').read().decode('utf-8-sig'))):
        lab = (r.get('rater_label') or '').strip()
        if lab:
            out[r['target'].strip()] = lab.upper()
    return out


def public_mode(master, rater1_csv):
    """Reader mode. Recompute every owned value from the released corpus_master.csv
    and rater1_labels.csv and compare with the recorded values. Writes nothing.
    Exit 0 only when every value matches."""
    print('=== recount_corpus_r196.py -- public mode ===')
    print('corpus_master : %s' % master)
    print('  sha256      : %s' % sha256_of(master))
    print('rater1 labels : %s' % rater1_csv)
    print('  sha256      : %s' % sha256_of(rater1_csv))
    m = measure(load_master(master), load_rater_csv(rater1_csv))
    fails = 0
    for key in sorted(PUBLIC_EXPECT):
        got, exp = m[key], PUBLIC_EXPECT[key]
        if isinstance(exp, list):
            got = list(got)
        ok = got == exp
        fails += (not ok)
        print('  %-22s computed=%-34s recorded=%-24s [%s]'
              % (key, got, exp, 'OK' if ok else 'FAIL'))
    print('RESULT: %d checks, %d FAIL' % (len(PUBLIC_EXPECT), fails))
    return 0 if fails == 0 else 1


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def load_master(path):
    text = open(path, 'rb').read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(text)))


def load_rater1_xlsm(xlsm_path):
    # openpyxl is imported here rather than at module level: it is needed only by
    # this branch, which requires the annotation workbooks. Those are not part of
    # the public data bundle, so a reader working from the bundle takes the CSV
    # branch and must not be made to install a package this run never uses.
    import openpyxl
    wb = openpyxl.load_workbook(xlsm_path, keep_vba=True, data_only=True)
    ws = wb['\u5224\u5b9a\u30b7\u30fc\u30c8']  # sheet name, ASCII-safe form
    out = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[1] is None:
            break
        tid = str(row[1]).strip()
        lab = row[6]
        if lab and str(lab).strip():
            out[tid] = str(lab).strip().upper()
    return out


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def measure(rows, rater1):
    """Return every quantity this script owns, as a flat dict."""
    H = lambda r: r['human_label'].strip().upper()
    L = lambda r: r['level'].strip().upper()
    valid = [r for r in rows if fnum(r['cmi']) > 0]
    m = {'n_total': len(rows), 'n_valid': len(valid)}

    zero = [r for r in rows if fnum(r['cmi']) == 0]
    m['cmi0_n'] = len(zero)
    m['cmi0_targets'] = sorted(r['target'] for r in zero)
    m['cmi0_english'] = sorted(r['target'] for r in zero if str(r['is_english']).strip() == '1')
    m['cmi0_error_nonempty'] = sorted(r['target'] for r in zero if r['error'].strip())

    sat = [r for r in rows if fnum(r['enemy_frame']) == 1.0 and fnum(r['propaganda']) == 1.0]
    m['sn004_n'] = len(sat)
    m['sn004_targets'] = sorted(r['target'] for r in sat)
    cm = sorted(fnum(r['cmi']) for r in sat)
    m['sn004_cmi_lo'], m['sn004_cmi_hi'] = (cm[0], cm[-1]) if cm else (0.0, 0.0)
    m['sn004_detail'] = sorted((r['target'], fnum(r['cmi']), H(r)) for r in sat)
    m['sn230_233'] = sorted((r['target'], H(r)) for r in rows
                            if r['target'] in ('sn230', 'sn231', 'sn232', 'sn233'))

    high = [r for r in valid if H(r) == 'HIGH']
    tp_r = [r for r in high if fnum(r['cmi']) >= 41]
    fn_r = [r for r in high if fnum(r['cmi']) < 41]
    ncat = lambda r: sum(1 for c in CATS13 if fnum(r[c]) > 0)
    def mdens(r):
        v = [fnum(r[c]) for c in CATS13 if fnum(r[c]) > 0]
        return sum(v) / len(v) if v else 0.0
    tpc = [ncat(r) for r in tp_r]; fnc = [ncat(r) for r in fn_r]
    tpd = [mdens(r) for r in tp_r]; fnd = [mdens(r) for r in fn_r]
    m['fnw_high'], m['fnw_tp'], m['fnw_fn'] = len(high), len(tp_r), len(fn_r)
    m['fnw_cat_tp'] = round(sum(tpc) / len(tpc), 2)
    m['fnw_cat_fn'] = round(sum(fnc) / len(fnc), 2)
    u1, p1 = mannwhitneyu(tpc, fnc, alternative='two-sided')
    m['fnw_cat_u'] = float(u1)   # NOT int(): U is a half-integer under ties
    m['fnw_cat_p'] = float(p1)
    m['fnw_cat_rb'] = round(2 * u1 / (len(tpc) * len(fnc)) - 1, 3)
    m['fnw_den_tp'] = round(sum(tpd) / len(tpd), 3)
    m['fnw_den_fn'] = round(sum(fnd) / len(fnd), 3)
    u2, p2 = mannwhitneyu(tpd, fnd, alternative='two-sided')
    m['fnw_den_u'] = float(u2)   # NOT int(): U is a half-integer under ties
    m['fnw_den_p'] = float(p2)
    m['fnw_den_rb'] = round(2 * u2 / (len(tpd) * len(fnd)) - 1, 3)
    m['fnw_min_tp'] = min(tpc)

    tp = sum(1 for r in valid if L(r) == 'HIGH' and H(r) == 'HIGH')
    fp = sum(1 for r in valid if L(r) == 'HIGH' and H(r) != 'HIGH')
    fn_v = sum(1 for r in valid if L(r) != 'HIGH' and H(r) == 'HIGH')
    fn_a = sum(1 for r in rows if L(r) != 'HIGH' and H(r) == 'HIGH')
    tn = sum(1 for r in valid if L(r) != 'HIGH' and H(r) != 'HIGH')
    prec = tp / float(tp + fp)
    rec_a = tp / float(tp + fn_a)
    rec_v = tp / float(tp + fn_v)
    m['prf_tp'], m['prf_fp'], m['prf_fn_valid'], m['prf_fn_all'] = tp, fp, fn_v, fn_a
    m['prf_fp_id'] = sorted(r['target'] for r in valid if L(r) == 'HIGH' and H(r) != 'HIGH')
    m['prf_precision'] = round(prec * 100, 1)
    m['prf_recall_all'] = round(rec_a * 100, 1)
    m['prf_f1_all'] = round(2 * prec * rec_a / (prec + rec_a) * 100, 1)
    m['prf_recall_valid'] = round(rec_v * 100, 1)
    m['prf_f1_valid'] = round(2 * prec * rec_v / (prec + rec_v) * 100, 1)
    m['spec_tn'] = tn
    m['spec_pct'] = round(100.0 * tn / (tn + fp), 1)

    ex = sum(1 for r in valid if L(r) == H(r))
    w1 = sum(1 for r in valid if abs(LS[L(r)] - LS[H(r)]) <= 1)
    m['perf_exact_n'] = ex
    m['perf_exact_pct'] = round(100.0 * ex / len(valid), 1)
    m['perf_w1_n'] = w1
    m['perf_w1_pct'] = round(100.0 * w1 / len(valid), 1)

    m['hml_all'] = tuple(sum(1 for r in rows if H(r) == k) for k in ('HIGH', 'MEDIUM', 'LOW'))
    m['hml_valid'] = tuple(sum(1 for r in valid if H(r) == k) for k in ('HIGH', 'MEDIUM', 'LOW'))

    by_id = {r['target']: r for r in valid}
    pol = [t for t in by_id if t in rater1
           and {H(by_id[t]), rater1[t]} == {'HIGH', 'LOW'}]
    m['k004_polar'] = len(pol)
    m['k004_hl'] = sum(1 for t in pol if H(by_id[t]) == 'HIGH')
    m['k004_lh'] = sum(1 for t in pol if H(by_id[t]) == 'LOW')
    m['k004_lh_targets'] = sorted(t for t in pol if H(by_id[t]) == 'LOW')
    genres = Counter(by_id[t]['genre_label'] for t in pol)
    m['k004_genres'] = genres.most_common()
    top = genres.most_common(1)[0] if genres else ('', 0)
    m['k004_top_genre_n'] = top[1]
    m['k004_top_genre_pct'] = round(100.0 * top[1] / len(pol), 1) if pol else 0.0
    m['k004_cult_n'] = next((v for k, v in genres.items() if k.startswith('2')), 0)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public_master',
                    help='released corpus_master.csv; runs the reader check only')
    ap.add_argument('--rater1', help='released rater1_labels.csv (reader check)')
    ap.add_argument('--gate_master')
    ap.add_argument('--new_master')
    ap.add_argument('--xlsm')
    ap.add_argument('--log')
    args = ap.parse_args()
    if args.public_master:
        if not args.rater1:
            ap.error('--rater1 is required with --public_master')
        sys.exit(public_mode(args.public_master, args.rater1))
    for k in ('gate_master', 'new_master', 'xlsm', 'log'):
        if getattr(args, k) is None:
            ap.error('--%s is required unless --public_master is given' % k)

    lines = []
    def out(s=''):
        print(s)
        lines.append(s)

    rater1 = load_rater1_xlsm(args.xlsm)
    out('=== recount_corpus_r196.py ===')
    out('gate_master : %s' % args.gate_master)
    out('  sha256    : %s' % sha256_of(args.gate_master))
    out('new_master  : %s' % args.new_master)
    out('  sha256    : %s' % sha256_of(args.new_master))
    out('xlsm        : %s' % args.xlsm)
    out('  sha256    : %s' % sha256_of(args.xlsm))
    out('rater1 labels loaded: %d' % len(rater1))
    out()

    g = measure(load_master(args.gate_master), rater1)
    out('=== GATE -- recorded n=202 value reproduction ===')
    fails = 0
    for key in sorted(GATE):
        got, exp = g[key], GATE[key]
        if isinstance(exp, list):
            got = list(got)
        ok = got == exp
        if not ok:
            fails += 1
        out('  %-22s computed=%-34s recorded=%-24s [%s]'
            % (key, got, exp, 'OK' if ok else 'FAIL'))
    out('GATE: %d checks, %d FAIL' % (len(GATE), fails))
    out()
    if fails:
        out('=== RESULT ===')
        out('GATE FAILED. No n=196 value is emitted.')
        open(args.log, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
        sys.exit(1)

    n = measure(load_master(args.new_master), rater1)
    out('=== NEW POPULATION -- measured values ===')
    for key in sorted(n):
        out('  %-22s %s' % (key, n[key]))
    out()
    out('=== CHANGED vs n=202 ===')
    for key in sorted(GATE):
        if n[key] != GATE[key]:
            out('  %-22s %s  ->  %s' % (key, GATE[key], n[key]))
    out()
    out('=== RESULT ===')
    out('GATE: %d checks, 0 FAIL. New population emitted.' % len(GATE))
    open(args.log, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    sys.exit(0)


if __name__ == '__main__':
    main()
