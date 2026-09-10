"""reason_code_mcnemar.py -- reason-code usage rates and McNemar exact tests,
author against each rater, at a specified frozen population.

WHY THIS SCRIPT EXISTS. Section 5.3 of the manuscript prints six usage rates and two
p-values from this analysis, and the evidence ledger records them as EV-kappa-015 and
EV-kappa-016. NO CODE IN THE REPOSITORY COMPUTED THEM: measured S293-J, a recursive
search of scripts/ and of the publish-side repository for mcnemar, binomtest,
binom_test, discordant, stats.binom and spearman returned one hit, a comment line in
verify_public_bundle.py. The computation was performed in a session and not saved,
which is the mechanism Pending 106 records. This script restores it.

THE RESTORATION IS VERIFIED, NOT ASSERTED. Run at the 202-document population it
reproduces six independently recorded values, including two p-values and two q-values
at four decimal places. Those assertions are gates: the script halts if any fails, so a
run that completes has demonstrated that the reconstructed method is the original one.
Three properties had to be right simultaneously for the four-digit agreement to occur --
the two-sided exact binomial test on discordant pairs, Benjamini-Hochberg correction
over m = 7, and the code mapping in which the rater options for fear and for urgency
are one code.

THE JOIN KEY IS THE PSEUDONYMISED MASTER, AND THAT IS NOT COSMETIC. The rater label
files carry the 24 book-format chapters under book001_ch01-style identifiers, while
data/frozen/v1_9/corpus_master.csv carries the original ones. Joining against the latter
silently drops those 24 and yields n = 178, with every rate and every test still
computing and still looking plausible. That happened once during reconstruction and was
caught only because the population size is printed. STEP 2 gates the substitution: the
187 shared identifiers must agree on every field this script reads, so the remapping is
proven to carry no value change rather than assumed to.

Usage:
    python scripts/reason_code_mcnemar.py \
        --master data/frozen/v1_9_public_r3/corpus_master.csv \
        --canonical_master data/frozen/v1_9/corpus_master.csv \
        --rater1 data/frozen/v1_9_public_r3/rater1_labels.csv \
        --rater2 data/frozen/v1_9_public_r3/rater2_labels.csv \
        --log data/frozen/v1_9r/audit_reason_code_mcnemar_v1_9r.txt \
        --rows docs/drafts/pending_edits/S293-J_r196_mcnemar_rows.md \
        --session S293-J

Reader mode, the only mode that runs on the released data:
    python scripts/reason_code_mcnemar.py --public_dir <bundle dir>

Exit 0 only if every gate passes. Any failure raises before anything is written.
"""
import argparse
import csv
import hashlib
import io
import math
import os
import sys

INPUTS = {
    'master': '125fec3229cb972ab6818d05e6a488c007da8634d6e6de92eeb622fb49539005',
    'canonical_master': 'b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362',
    'rater1': '88a2f64ecb3c65afe9e796517c9c2142f7d3c8009a13fd20ca56c7dc2cb72d21',
    'rater2': '9da2465c34017318a66356e02be9e7a72022bd8290b92bade0e123dfdb5736c2',
}

# Author codes are free-standing values in riskfactor_1..3. Rater codes are the closed
# option set of reason_1. THE FEAR AND URGENCY OPTIONS MAP TO ONE AUTHOR CODE: the
# manuscript names it "fear/urgency induction", and the mapping is what reproduces the
# recorded 38.1 per cent for Rater 2; the fear option alone gives 34.7 per cent.
CODES = {
    'Emotional Induction': [
        '感情に訴えている（共感・感動・怒りなど）'],
    'No academic/empirical support': [
        '根拠・データが不明確（出典なし・検証不能など）'],
    'Authority Halo': [
        '権威を利用している（専門家・肩書き・実績など）'],
    'Fear/Urgency Manipulation': [
        '不安・恐怖を煽っている（病気・損失・孤立など）',
        '行動・購入を急かしている（期限・限定・今だけなど）'],
    'Desire Activation': [
        '欲求に訴えている（金銭・恋愛・承認など）'],
    'Normative Induction via Emotional Grounding': [
        '規範・同調圧力を使っている（みんなそうしている等）'],
    'Potential concealment of adverse info': [
        '不利な情報が隠れている（リスク・デメリットの隠蔽など）'],
}

# Rater options that map to NO author code, declared so that the coverage gate below can
# be exact. Both are procedural rather than substantive: one is an explicit residual
# category and one records that the rater could not decide.
UNMAPPED_ALLOWED = [
    'その他',
    '判定に迷う（テキスト不足・文脈不明など）',
]
M = len(CODES)

DEC072_REMOVED = {'AD_065', 'AD_067', 'AD_071', 'AD_072', 'AD_073', 'AD_074'}

# Values recorded independently of this script, in evidence_ledger EV-kappa-015 and
# EV-kappa-016 and in the manuscript body. Each is a gate, not a comment.
# (rater, code) -> (author pct, rater pct, author-only, rater-only, p or None, q or None)
RECORDED_202 = {
    ('Rater 1', 'Emotional Induction'):          (56.9, 18.8,  81,  4, None,   None),
    ('Rater 1', 'No academic/empirical support'):(42.1,  2.5,  85,  5, None,   None),
    ('Rater 1', 'Authority Halo'):               (31.7, 19.3,  41, 16, 0.0013, 0.0021),
    ('Rater 2', 'Emotional Induction'):          (56.9,  9.4, 102,  6, None,   None),
    ('Rater 2', 'Authority Halo'):               (31.7,  4.0,  61,  5, None,   None),
    ('Rater 2', 'Fear/Urgency Manipulation'):    (23.8, 38.1,  16, 45, 0.0003, 0.0004),
}
# the four entries above whose p is recorded only as "<.0001"
RECORDED_202_TINY_P = [
    ('Rater 1', 'Emotional Induction'),
    ('Rater 1', 'No academic/empirical support'),
    ('Rater 2', 'Emotional Induction'),
    ('Rater 2', 'Authority Halo'),
]

AUTHOR_FIELDS = ('riskfactor_1', 'riskfactor_2', 'riskfactor_3', 'human_label', 'cmi')

# PUBLIC MODE expectations at n = 196, transcribed from EV-r196-030 (Rater 1) and
# EV-r196-031 (Rater 2) BEFORE any public-mode run existed, so that the check is
# not fitted to its own output. Per code: (author pct, rater pct, author-only,
# rater-only, p, q); percentages to one place, p and q to six.
PUBLIC_196 = {
    'Rater 1': {
        'Emotional Induction':                         (57.7, 19.4, 79, 4, 0.000000, 0.000000),
        'No academic/empirical support':               (42.9, 2.0, 84, 4, 0.000000, 0.000000),
        'Authority Halo':                              (32.7, 19.4, 41, 15, 0.000686, 0.001200),
        'Fear/Urgency Manipulation':                   (24.0, 23.0, 27, 25, 0.889884, 0.889884),
        'Desire Activation':                           (28.1, 23.5, 27, 18, 0.232693, 0.271475),
        'Normative Induction via Emotional Grounding': (13.8, 2.6, 26, 4, 0.000059, 0.000139),
        'Potential concealment of adverse info':       (9.7, 3.1, 16, 3, 0.004425, 0.006195),
    },
    'Rater 2': {
        'Emotional Induction':                         (57.7, 9.7, 100, 6, 0.000000, 0.000000),
        'No academic/empirical support':               (42.9, 0.0, 84, 0, 0.000000, 0.000000),
        'Authority Halo':                              (32.7, 4.1, 61, 5, 0.000000, 0.000000),
        'Fear/Urgency Manipulation':                   (24.0, 39.3, 15, 45, 0.000135, 0.000188),
        'Desire Activation':                           (28.1, 21.9, 37, 25, 0.161881, 0.188862),
        'Normative Induction via Emotional Grounding': (13.8, 2.0, 25, 2, 0.000006, 0.000010),
        'Potential concealment of adverse info':       (9.7, 9.2, 14, 13, 1.000000, 1.000000),
    },
}


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def read_csv(path, expected, allow_mismatch):
    if not os.path.exists(path):
        raise SystemExit('[HALT] missing input: %s' % path)
    got = sha(path)
    if got != expected and not allow_mismatch:
        raise SystemExit('[HALT] %s sha256 %s != expected %s' % (path, got, expected))
    raw = open(path, 'rb').read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(raw))), got


def binom_two_sided(b, c):
    """Exact two-sided binomial test on the discordant pairs, p = 0.5.
    This is McNemar's exact test; no normal approximation and no continuity correction."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / float(2 ** n)
    return min(1.0, 2.0 * tail)


def bh_fdr(ps):
    """Benjamini-Hochberg step-up over the m tests, monotonicity enforced."""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    q = [0.0] * m
    prev = 1.0
    for rank, i in enumerate(reversed(order), 1):
        prev = min(prev, ps[i] * m / float(m - rank + 1))
        q[i] = prev
    return q


def analyse(master, rater, ids):
    n = len(ids)
    out = []
    for code, options in CODES.items():
        A = [code in {master[t][f].strip() for f in ('riskfactor_1', 'riskfactor_2',
                                                     'riskfactor_3')} for t in ids]
        R = [rater[t]['reason_1'].strip() in options for t in ids]
        b = sum(1 for x, y in zip(A, R) if x and not y)
        c = sum(1 for x, y in zip(A, R) if y and not x)
        out.append({'code': code, 'author_n': sum(A), 'rater_n': sum(R),
                    'author_pct': 100.0 * sum(A) / n, 'rater_pct': 100.0 * sum(R) / n,
                    'author_only': b, 'rater_only': c, 'p': binom_two_sided(b, c)})
    for rec, q in zip(out, bh_fdr([r['p'] for r in out])):
        rec['q'] = q
    return out


def public_mode(bundle_dir):
    """Reader mode. Recompute the reason-code rates and McNemar tests at n = 196
    from the released bundle (corpus_master.csv, rater1_labels.csv,
    rater2_labels.csv) and compare with the recorded values. Writes nothing.
    Exit 0 only when every value matches."""
    def load(name):
        path = os.path.join(bundle_dir, name)
        print('  %-18s %s' % (name, sha(path)))
        return {r['target']: r for r in
                csv.DictReader(io.StringIO(open(path, 'rb').read().decode('utf-8-sig')))}
    print('reason_code_mcnemar.py -- public mode')
    master = load('corpus_master.csv')
    raters = {'Rater 1': load('rater1_labels.csv'), 'Rater 2': load('rater2_labels.csv')}
    fails = checks = 0

    def check(name, ok, detail):
        nonlocal fails, checks
        fails += (not ok)
        checks += 1
        print('  [%s] %s %s' % ('OK' if ok else 'FAIL', name, detail))

    declared = {o for opts in CODES.values() for o in opts}
    observed = {r['reason_1'].strip() for rd in raters.values() for r in rd.values()
                if r['reason_1'].strip()}
    check('option coverage', observed <= declared | set(UNMAPPED_ALLOWED)
          and declared <= observed, '(every rater option mapped or declared unmapped)')
    valid = {t for t in master if float(master[t]['cmi']) > 0}
    ids = sorted(valid & set(raters['Rater 1']) & set(raters['Rater 2']))
    check('population', len(ids) == 196, 'n=%d expected=196' % len(ids))
    for name, rd in raters.items():
        for r in analyse(master, rd, ids):
            exp = PUBLIC_196[name][r['code']]
            got = (round(r['author_pct'], 1), round(r['rater_pct'], 1), r['author_only'],
                   r['rater_only'], round(r['p'], 6), round(r['q'], 6))
            check('%s / %s' % (name, r['code']), got == exp,
                  'computed=%s recorded=%s' % (got, exp))
    print('RESULT: %d checks, %d FAIL' % (checks, fails))
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public_dir',
                    help='released bundle directory; runs the reader check only')
    ap.add_argument('--master',
                    help='pseudonymised corpus_master; the join key')
    ap.add_argument('--canonical_master',
                    help='frozen v1_9 corpus_master; used only to gate the remapping')
    ap.add_argument('--rater1')
    ap.add_argument('--rater2')
    ap.add_argument('--log')
    ap.add_argument('--rows', default=None,
                    help='if given, also emit the two ledger rows, citing the log by hash')
    ap.add_argument('--session')
    ap.add_argument('--date', default='2026-08-18')
    ap.add_argument('--allow_hash_mismatch', action='store_true',
                    help='diagnostic only; never use for values that will be recorded')
    args = ap.parse_args()
    if args.public_dir:
        sys.exit(public_mode(args.public_dir))
    for k in ('master', 'canonical_master', 'rater1', 'rater2', 'log', 'session'):
        if getattr(args, k) is None:
            ap.error('--%s is required unless --public_dir is given' % k)

    m_rows, sha_m = read_csv(args.master, INPUTS['master'], args.allow_hash_mismatch)
    c_rows, sha_c = read_csv(args.canonical_master, INPUTS['canonical_master'],
                             args.allow_hash_mismatch)
    r1_rows, sha_r1 = read_csv(args.rater1, INPUTS['rater1'], args.allow_hash_mismatch)
    r2_rows, sha_r2 = read_csv(args.rater2, INPUTS['rater2'], args.allow_hash_mismatch)

    master = {r['target']: r for r in m_rows}
    canon = {r['target']: r for r in c_rows}
    raters = {'Rater 1': {r['target']: r for r in r1_rows},
              'Rater 2': {r['target']: r for r in r2_rows}}

    # ---- GATE 1: the remapping carries no value change ----------------------
    shared = sorted(set(master) & set(canon))
    if len(shared) != 187:
        raise SystemExit('[HALT] %d shared identifiers, expected 187' % len(shared))
    for t in shared:
        for f in AUTHOR_FIELDS:
            if master[t][f].strip() != canon[t][f].strip():
                raise SystemExit('[HALT] %s differs at %s between the two masters' % (t, f))
    only_master = sorted(set(master) - set(canon))
    only_canon = sorted(set(canon) - set(master))
    if len(only_master) != 24 or len(only_canon) != 24:
        raise SystemExit('[HALT] pseudonymised/original book counts are %d and %d, expected 24'
                         % (len(only_master), len(only_canon)))
    for t in only_master:
        if not (t.startswith('book') and '_ch' in t):
            raise SystemExit('[HALT] unexpected master-only identifier: %s' % t)

    # ---- GATE 2: the option mapping covers the data exactly -----------------
    # This gate exists because a single wrong codepoint in a declared option string
    # produces a silently wrong rate rather than an error. It fired during development:
    # one character of the fear option was mistyped, the fear option matched nothing, and
    # the Rater 2 fear/urgency rate came out 3.5 per cent instead of 38.1. The recorded-value
    # gate caught it, but only because a recorded value happened to cover that code. This
    # gate catches it whether or not a recorded value covers it.
    declared = {o for opts in CODES.values() for o in opts}
    observed = set()
    for rd in raters.values():
        for r in rd.values():
            v = r['reason_1'].strip()
            if v:
                observed.add(v)
    missing = sorted(declared - observed)
    if missing:
        raise SystemExit('[HALT] declared option string absent from both rater files, which '
                         'means it is mistyped: %r' % missing)
    unmapped = sorted(observed - declared - set(UNMAPPED_ALLOWED))
    if unmapped:
        raise SystemExit('[HALT] rater option present in the data but neither mapped nor '
                         'declared unmapped: %r' % unmapped)
    unused_allow = sorted(set(UNMAPPED_ALLOWED) - observed)
    if unused_allow:
        raise SystemExit('[HALT] declared unmapped option absent from the data, which means '
                         'it is mistyped: %r' % unused_allow)

    # ---- populations --------------------------------------------------------
    valid = {t for t in master if float(master[t]['cmi']) > 0}
    ids202 = sorted(valid & set(raters['Rater 1']) & set(raters['Rater 2']))
    if len(ids202) != 202:
        raise SystemExit('[HALT] the 202 population resolved to %d' % len(ids202))
    ids196 = sorted(set(ids202) - DEC072_REMOVED)
    if len(ids196) != 196:
        raise SystemExit('[HALT] the 196 population resolved to %d' % len(ids196))

    res202 = {name: analyse(master, rd, ids202) for name, rd in raters.items()}
    res196 = {name: analyse(master, rd, ids196) for name, rd in raters.items()}

    # ---- GATE 3: reproduce the recorded values ------------------------------
    checks = []
    for (name, code), exp in RECORDED_202.items():
        rec = next(r for r in res202[name] if r['code'] == code)
        ap_, rp_, bo, ro, p_exp, q_exp = exp
        checks.append(('author pct %s / %s' % (name, code),
                       round(rec['author_pct'], 1), ap_))
        checks.append(('rater pct %s / %s' % (name, code),
                       round(rec['rater_pct'], 1), rp_))
        checks.append(('author-only %s / %s' % (name, code), rec['author_only'], bo))
        checks.append(('rater-only %s / %s' % (name, code), rec['rater_only'], ro))
        if p_exp is not None:
            checks.append(('p %s / %s' % (name, code), round(rec['p'], 4), p_exp))
            checks.append(('q %s / %s' % (name, code), round(rec['q'], 4), q_exp))
    for (name, code) in RECORDED_202_TINY_P:
        rec = next(r for r in res202[name] if r['code'] == code)
        checks.append(('p < .0001 %s / %s' % (name, code), rec['p'] < 0.0001, True))

    failed = [(lbl, got, exp) for lbl, got, exp in checks if got != exp]
    if failed:
        for lbl, got, exp in failed:
            print('[FAIL] %s: got %r, recorded %r' % (lbl, got, exp), file=sys.stderr)
        raise SystemExit('[HALT] %d of %d recorded values not reproduced. The reconstruction '
                         'is not the original method; do not record anything from this run.'
                         % (len(failed), len(checks)))

    # ---- write the audit log ------------------------------------------------
    L = []
    L.append('R8 reason-code usage and McNemar exact tests')
    L.append('Generated by scripts/reason_code_mcnemar.py, session %s, %s'
             % (args.session, args.date))
    L.append('')
    L.append('SECTION 0  inputs')
    L.append('  master (join key)   %s  %s' % (sha_m, args.master))
    L.append('  canonical master    %s  %s' % (sha_c, args.canonical_master))
    L.append('  rater 1 labels      %s  %s' % (sha_r1, args.rater1))
    L.append('  rater 2 labels      %s  %s' % (sha_r2, args.rater2))
    L.append('')
    L.append('SECTION 1  method')
    L.append('  Author codes: any of riskfactor_1..3. Rater codes: reason_1, a closed option')
    L.append('  set; reason_2 and reason_3 are empty in every row of both files, so the author')
    L.append('  instrument offers up to three codes and the rater instrument one.')
    L.append('  Test: two-sided exact binomial on the discordant pairs, p = 0.5. No normal')
    L.append('  approximation, no continuity correction. Correction: Benjamini-Hochberg over')
    L.append('  m = %d, monotonicity enforced.' % M)
    L.append('  Fear and urgency are two rater options mapping to one author code.')
    if unmapped:
        for v in unmapped:
            L.append('  UNMAPPED rater option, excluded from all seven codes: %s' % v)
    L.append('  Option coverage gate: %d declared option strings all present in the data; '
             'the %d options declared unmapped are the residual and undecided categories; '
             'no option is unaccounted for.' % (len(declared), len(UNMAPPED_ALLOWED)))
    L.append('')
    L.append('SECTION 2  regression gate against recorded values, n = 202')
    L.append('  checks executed = %d, FAIL = 0, ALL PASS' % len(checks))
    L.append('  The recorded values are EV-kappa-015, EV-kappa-016 and the Section 5.3 body.')
    L.append('')
    for label, ids, res in (('SECTION 3  pre-deduplication population', ids202, res202),
                            ('SECTION 4  DEC-072 population', ids196, res196)):
        L.append('%s   n = %d' % (label, len(ids)))
        for name in ('Rater 1', 'Rater 2'):
            L.append('  author x %s' % name)
            L.append('    %-44s %8s %8s %8s %8s %10s %10s'
                     % ('code', 'auth_n', 'auth_%', 'rater_n', 'rater_%', 'p', 'q'))
            for r in res[name]:
                L.append('    %-44s %8d %8.1f %8d %8.1f %10.6f %10.6f'
                         % (r['code'], r['author_n'], r['author_pct'],
                            r['rater_n'], r['rater_pct'], r['p'], r['q']))
                L.append('        discordant: author_only=%d rater_only=%d'
                         % (r['author_only'], r['rater_only']))
        L.append('')
    log_text = '\n'.join(L) + '\n'
    os.makedirs(os.path.dirname(args.log) or '.', exist_ok=True)
    with open(args.log, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(log_text)
    log_sha = sha(args.log)
    log_bytes = len(log_text.encode('utf-8'))

    print('log written  : %s' % args.log)
    print('log sha256   : %s' % log_sha)
    print('log bytes    : %d' % log_bytes)
    print('gate checks  : %d, FAIL 0, ALL PASS' % len(checks))
    print('populations  : n=202 and n=196')

    if not args.rows:
        return 0

    # ---- emit the two ledger rows, citing the log just written --------------
    DATE = '%s / %s' % (args.date, args.session)
    SRC = ('%s (%s, %d bytes), written by scripts/reason_code_mcnemar.py in the same run. '
           'THE COMPUTATION WAS RECONSTRUCTED: no repository code computed it (measured '
           'S293-J). The reconstruction reproduces %d recorded values at n = 202, including '
           'two p-values and two q-values to four decimal places, as a run-time gate.'
           % (args.log, log_sha, log_bytes, len(checks)))

    def fmt(res, name):
        parts = []
        for r in res[name]:
            parts.append('%s author %.1f%% rater %.1f%% (author-only %d, rater-only %d, '
                         'p=%.6f, q=%.6f)' % (r['code'], r['author_pct'], r['rater_pct'],
                                              r['author_only'], r['rater_only'],
                                              r['p'], r['q']))
        return '; '.join(parts)

    def cell(*xs):
        s = ' '.join(xs)
        if '|' in s:
            raise SystemExit('[HALT] a cell contains a pipe')
        return s

    rows = []
    rows.append('| ' + ' | '.join([
        'EV-r196-030', 'EV-kappa-015',
        cell('Reason-code usage and McNemar exact tests, author x Rater 1, recomputed at '
             'n = 196.', fmt(res196, 'Rater 1'),
             'THE DIRECTION OF THE ENTRY IS UNCHANGED: the author\'s two most-used codes '
             'remain applied at far lower rates by the rater, and both remain significant '
             'after correction over m = %d.' % M,
             'WHAT CHANGES IS EVERY NUMBER. The instruments remain asymmetric, the author '
             'having up to three code slots and the rater one, which is a property of the '
             'instruments and not of the population change.'),
        cell('author 56.9%/42.1%/31.7%/13.4% against rater 18.8%/2.5%/19.3%/2.5% at n = 202; '
             'p<.0001, p<.0001, p=.0013 (q=.0021)'),
        SRC, 'VERIFIED', DATE]) + ' |')
    rows.append('| ' + ' | '.join([
        'EV-r196-031', 'EV-kappa-016',
        cell('Reason-code usage and McNemar exact tests, author x Rater 2, recomputed at '
             'n = 196.', fmt(res196, 'Rater 2'),
             'THE ENTRY\'S DISTINGUISHING CLAIM SURVIVES: fear/urgency remains the only code '
             'on which the rater exceeds the author, and it remains significant after '
             'correction. No other code reverses direction.'),
        cell('author 23.8% against rater 38.1% on fear/urgency, p=.0003 (q=.0004), the only '
             'code in that direction; author 56.9%/31.7% against rater 9.4%/4.0% on '
             'emotional and authority, both p<.0001, at n = 202'),
        SRC, 'VERIFIED', DATE]) + ' |')

    ids_ = [r.split('|')[1].strip() for r in rows]
    if len(ids_) != len(set(ids_)):
        raise SystemExit('[HALT] duplicate claim_id emitted')
    for r in rows:
        if r.count('|') != 8:
            raise SystemExit('[HALT] row does not carry 7 columns')

    hdr = [
        '<!-- PROVENANCE. This block is machine-generated. Do not hand-edit; regenerate.',
        '     generator : scripts/reason_code_mcnemar.py',
        '     log       : %s (%s, %d bytes)' % (args.log, log_sha, log_bytes),
        '     inputs    : %s (%s)' % (args.master, sha_m),
        '                 %s (%s)' % (args.canonical_master, sha_c),
        '                 %s (%s)' % (args.rater1, sha_r1),
        '                 %s (%s)' % (args.rater2, sha_r2),
        '     gate      : %d recorded values reproduced at n = 202, FAIL 0' % len(checks),
        '     rows      : %d (%s .. %s)' % (len(rows), ids_[0], ids_[-1]),
        '     session   : %s' % DATE,
        '     NOTE: the computation behind these rows existed nowhere in the repository and',
        '     was reconstructed at S293-J. See Pending 106. -->',
    ]
    out = '\n'.join(hdr) + '\n' + '\n'.join(rows) + '\n'
    with open(args.rows, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(out)
    print('rows written : %d' % len(rows))
    print('rows output  : %s' % args.rows)
    print('rows sha256  : %s' % hashlib.sha256(out.encode('utf-8')).hexdigest())
    print('rows bytes   : %d' % len(out.encode('utf-8')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
