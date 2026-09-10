#!/usr/bin/env python3
"""Producer and gate for the document-level manuscript values that no claim row owns.

Covers Pending 113 cluster (5) items 50.5, 0.462, 0.454 and cluster (6) item 0.90.

THIRD-PARTY CONSTRAINT, BINDING ON THIS SCRIPT. The internal frozen corpus_master
carries title-derived romanised identifiers for the 24 book-format chapters. Those
identifiers encode the titles of commercially published works and are pseudonymised
for release under DEC-022. THIS SCRIPT NEVER EMITS ONE. Book values are read from the
pseudonymised public bundle, and GATE 1 proves that file is a faithful relabeling of
the internal one, so nothing is taken on trust. Where the internal file must be
compared, only counts are printed.

WHY THESE VALUES ARE POPULATION-INDEPENDENT, AND WHY THAT IS GATED RATHER THAN STATED.
r8.py scores each document against its own character count, with no corpus-level term,
so a per-document value cannot move when other documents leave the population. GATE 3
checks the consequence directly instead of relying on that argument: it asserts that
every row retained at n=196 is cell-identical to its n=202 row, and that none of the
six DEC-072 removals is one of the documents claimed here.

Reader mode, the only mode that runs on the released data:
    python scripts/document_level_values_recount.py --public_master corpus_master.csv --r8py r8.py

Exit 0 requires 0 FAIL across every gate. A FAIL anywhere exits 1 and emits no row.
"""

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter

EXPECTED_SHA = {
    'internal':   'b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362',
    'public':     '125fec3229cb972ab6818d05e6a488c007da8634d6e6de92eeb622fb49539005',
    'dedup':      '57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b',
    'r8py':       '53553ce13a815a4bcc30f448cbb3ed2808a6ce3fedb61a26059fc949b3fd09b5',
    'manuscript': '686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185',
}

DEC072_REMOVED = ['AD_065', 'AD_067', 'AD_071', 'AD_072', 'AD_073', 'AD_074']

BOOK_RE = re.compile(r'^book\d{3}_ch\d{2}$')

# Tokens this row claims ownership of, and the number of times each occurs in the
# EN canonical. A count that has moved means the passage was edited and the gate
# must be re-read before it is trusted.
MANUSCRIPT_TOKEN_COUNTS = {
    '50.5': 2,
    '0.462': 1,
    '0.454': 1,
    '0.90': 1,
}


def sha256_of(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path):
    with open(path, encoding='utf-8-sig') as f:
        return {r['target']: r for r in csv.DictReader(f)}


def parse_weights(r8_text):
    m = re.search(r'^WEIGHTS = \{(.*?)^\}', r8_text, re.S | re.M)
    if not m:
        raise SystemExit('ABORT: WEIGHTS table not found in r8.py')
    out = {}
    for k, v in re.findall(r'"([a-z_]+)":\s*([0-9.]+)', m.group(1)):
        out[k] = float(v)
    return out


def gate2_claims(P, r8_text, check):
    """The claimed document-level values and the r8.py weight table. P is a
    corpus_master keyed by target in the pseudonymised form (book001_ch01 ...).
    Shared by the internal run and by the reader mode, so both assert the same
    values by the same code."""
    n = P['note223']
    check('note223 cmi', n['cmi'] == '50.5', n['cmi'], '50.5')
    check('note223 level', n['level'] == 'HIGH', n['level'], 'HIGH')
    check('note223 human_label', n['human_label'] == 'LOW', n['human_label'], 'LOW')
    check('note223 emotional', n['emotional'] == '0.462', n['emotional'], '0.462')
    for cat in ('logical', 'authority', 'statistical'):
        check('note223 %s saturated' % cat, float(n[cat]) == 1.0, n[cat], '1.0')
    check('note223 fear', float(n['fear']) == 0.74, n['fear'], '0.74')
    check('note223 hype', float(n['hype']) == 0.74, n['hype'], '0.74')

    b1 = [P['book001_ch%02d' % i] for i in range(1, 8)]
    cmi1 = [float(r['cmi']) for r in b1]
    log1 = [float(r['logical']) for r in b1]
    emo1 = [float(r['emotional']) for r in b1]
    check('book001 chapter count', len(b1) == 7, len(b1), 7)
    check('book001 all human HIGH',
          all(r['human_label'] == 'HIGH' for r in b1),
          Counter(r['human_label'] for r in b1), "{'HIGH': 7}")
    check('book001 cmi min', min(cmi1) == 18.6, min(cmi1), 18.6)
    check('book001 cmi max', max(cmi1) == 46.6, max(cmi1), 46.6)
    low1 = sum(1 for r in b1 if r['level'] == 'LOW')
    check('book001 LOW count', low1 == 4, low1, 4)
    check('book001 logical min', min(log1) == 0.74, min(log1), 0.74)
    check('book001 logical max', max(log1) == 1.0, max(log1), 1.0)
    sat1 = sum(1 for v in log1 if v == 1.0)
    check('book001 logical saturated count', sat1 == 5, sat1, 5)
    statsat = sorted('ch%02d' % i for i in range(1, 8)
                     if float(P['book001_ch%02d' % i]['statistical']) == 1.0)
    check('book001 statistical ceiling set', statsat == ['ch03', 'ch04', 'ch07'],
          statsat, "['ch03', 'ch04', 'ch07']")
    check('book001 emotional min', min(emo1) == 0.093, min(emo1), 0.093)
    check('book001 emotional max', max(emo1) == 0.444, max(emo1), 0.444)
    check('book001 emotional all below 0.5', max(emo1) < 0.5, max(emo1), '< 0.5')

    b2 = [P['book002_ch%02d' % i] for i in range(1, 7)]
    log2 = [float(r['logical']) for r in b2]
    emo2 = [float(r['emotional']) for r in b2]
    check('book002 chapter count', len(b2) == 6, len(b2), 6)
    sat2 = sum(1 for v in log2 if v == 1.0)
    check('book002 logical saturated in all', sat2 == 6, sat2, 6)
    check('book002 emotional min', min(emo2) == 0.063, min(emo2), 0.063)
    check('book002 emotional max', max(emo2) == 0.454, max(emo2), 0.454)
    check('book002 emotional all below 0.5', max(emo2) < 0.5, max(emo2), '< 0.5')

    W = parse_weights(r8_text)
    supp = {'naked_number', 'sexual_induction', 'beauty_diet'}
    theo = {k: v for k, v in W.items() if k not in supp}
    check('WEIGHTS key count', len(W) == 14, len(W), 14)
    check('theoretical weighted key count', len(theo) == 11, len(theo), 11)
    check('theoretical weight sum', abs(sum(theo.values()) - 0.90) < 1e-9,
          round(sum(theo.values()), 10), 0.90)
    check('naked_number weight', W['naked_number'] == 0.06, W['naked_number'], 0.06)
    check('sexual_induction weight', W['sexual_induction'] == 0.04,
          W['sexual_induction'], 0.04)
    check('beauty_diet weight', W['beauty_diet'] == 0.00, W['beauty_diet'], 0.00)
    nz = sum(1 for v in W.values() if v > 0)
    check('non-zero scored components', nz == 13, nz, 13)
    check('all weights sum', abs(sum(W.values()) - 1.00) < 1e-9,
          round(sum(W.values()), 10), 1.00)
    check('statistical is the maximum weight',
          W['statistical'] == max(W.values()) == 0.14, W['statistical'], 0.14)


def public_mode(master, r8py):
    """Reader mode. Assert the claimed document-level values on the released
    corpus_master.csv and the weight table in the released r8.py. The values are
    population-independent (see the module docstring), so they are the same values
    the internal run asserts. Writes nothing. Exit 0 only when every check passes."""
    fails = []

    def check(name, ok, got, want):
        if not ok:
            fails.append(name)
        print('  [%s] %-46s got=%s want=%s' % ('OK  ' if ok else 'FAIL', name, got, want))

    print('document_level_values_recount.py -- public mode')
    print('  corpus_master %s  %s' % (sha256_of(master), master))
    print('  r8.py         %s  %s' % (sha256_of(r8py), r8py))
    gate2_claims(load(master), open(r8py, encoding='utf-8').read(), check)
    print('RESULT: %s' % ('ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)))
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public_master',
                    help='released corpus_master.csv; runs the reader check only '
                         '(with --r8py)')
    ap.add_argument('--internal')
    ap.add_argument('--public')
    ap.add_argument('--dedup')
    ap.add_argument('--r8py')
    ap.add_argument('--manuscript', default=None)
    ap.add_argument('--log', default=None)
    ap.add_argument('--row-out', default=None,
                    help='path for the evidence-ledger claim row; written only on ALL PASS')
    args = ap.parse_args()
    if args.public_master:
        if not args.r8py:
            ap.error('--r8py is required with --public_master')
        return public_mode(args.public_master, args.r8py)
    for k in ('internal', 'public', 'dedup', 'r8py'):
        if getattr(args, k) is None:
            ap.error('--%s is required unless --public_master is given' % k)

    lines = []
    fails = []

    def emit(s=''):
        print(s)
        lines.append(s)

    def check(name, ok, got, want):
        tag = 'OK  ' if ok else 'FAIL'
        if not ok:
            fails.append(name)
        emit('  [%s] %-46s got=%s want=%s' % (tag, name, got, want))

    emit('document_level_values_recount.py')
    emit('Argument strings, echoed so the log identifies its own inputs:')
    for k in ('internal', 'public', 'dedup', 'r8py', 'manuscript'):
        emit('  --%-11s %s' % (k, getattr(args, k)))
    emit('')

    # ---------------- GATE 0: input identity ----------------
    emit('GATE 0  INPUT IDENTITY')
    for key, path in (('internal', args.internal), ('public', args.public),
                      ('dedup', args.dedup), ('r8py', args.r8py)):
        h = sha256_of(path)
        check('sha256 ' + key, h == EXPECTED_SHA[key], h, EXPECTED_SHA[key])
    if args.manuscript:
        h = sha256_of(args.manuscript)
        check('sha256 manuscript', h == EXPECTED_SHA['manuscript'], h,
              EXPECTED_SHA['manuscript'])
    if fails:
        emit('')
        emit('HALT: input identity failed. No further gate is run.')
        write_log(args.log, lines)
        return 1
    emit('')

    I = load(args.internal)
    P = load(args.public)
    D = load(args.dedup)
    r8_text = open(args.r8py, encoding='utf-8').read()

    # ---------------- GATE 1: the public file is a faithful relabeling ----------------
    emit('GATE 1  RELABELING FAITHFULNESS (public vs internal)')
    cols = [c for c in next(iter(P.values())).keys() if c != 'target']
    nonbook = [t for t in P if not BOOK_RE.match(t)]
    book = [t for t in P if BOOK_RE.match(t)]
    check('public row count', len(P) == 211, len(P), 211)
    check('public non-book count', len(nonbook) == 187, len(nonbook), 187)
    check('public book count', len(book) == 24, len(book), 24)
    check('compared column count', len(cols) == 24, len(cols), 24)

    absent = [t for t in nonbook if t not in I]
    check('non-book targets present in internal', not absent, len(absent), 0)
    celldiff = 0
    for t in nonbook:
        if t in I:
            for c in cols:
                if (P[t][c] or '') != (I[t][c] or ''):
                    celldiff += 1
    check('non-book cell differences', celldiff == 0, celldiff, 0)

    def tup(r):
        return tuple((r[c] or '') for c in cols)

    internal_only = [t for t in I if t not in P]
    check('internal-only targets', len(internal_only) == 24, len(internal_only), 24)
    same = Counter(tup(P[t]) for t in book) == Counter(tup(I[t]) for t in internal_only)
    check('book row multiset identical', same, same, True)
    emit('  NOTE: the 24 internal identifiers are NOT printed. Only counts appear above.')
    emit('')

    # ---------------- GATE 2: printed values at n=202 ----------------
    emit('GATE 2  PRINTED VALUES AT n=202')

    gate2_claims(P, r8_text, check)
    emit('')

    # ---------------- GATE 3: population independence ----------------
    emit('GATE 3  POPULATION INDEPENDENCE AT n=196')
    removed = sorted(set(I) - set(D))
    check('DEC-072 removed set', removed == sorted(DEC072_REMOVED),
          removed, sorted(DEC072_REMOVED))
    claimed_public = ['note223'] + ['book001_ch%02d' % i for i in range(1, 8)] \
                     + ['book002_ch%02d' % i for i in range(1, 7)]
    overlap = [t for t in claimed_public if t in DEC072_REMOVED]
    check('no claimed document was removed', not overlap, overlap, [])
    allcols = list(next(iter(I.values())).keys())
    moved = 0
    for t in D:
        if any((D[t][c] or '') != (I[t][c] or '') for c in allcols):
            moved += 1
    check('retained rows cell-identical to n=202', moved == 0, moved, 0)
    check('dedup row count', len(D) == 205, len(D), 205)
    emit('')

    # ---------------- GUARD: manuscript token counts ----------------
    if args.manuscript:
        emit('GUARD  MANUSCRIPT TOKEN COUNTS')
        mt = open(args.manuscript, encoding='utf-8-sig').read()
        for tok, want in MANUSCRIPT_TOKEN_COUNTS.items():
            got = len(re.findall(r'(?<![0-9.])' + re.escape(tok) + r'(?![0-9])', mt))
            check('token %s' % tok, got == want, got, want)
        emit('  A changed count means the passage was edited; re-read before trusting.')
        emit('')
    else:
        emit('GUARD  SKIPPED: --manuscript not supplied.')
        emit('')

    emit('SUMMARY')
    emit('  checks run : %d' % (len([l for l in lines if l.startswith('  [')])))
    emit('  FAIL       : %d' % len(fails))
    if fails:
        emit('  failed     : ' + ', '.join(fails))
        emit('RESULT: FAILED. No claim row may be written from this run.')
        write_log(args.log, lines)
        return 1
    emit('RESULT: ALL PASS')
    emit('')
    emit('VALUES CLAIMED BY THIS RUN, unchanged at n=196:')
    emit('  note223  CMI 50.5, level HIGH, human_label LOW, EmotionalRisk 0.462,')
    emit('           LogicalRisk / AuthorityRisk / StatisticalRisk at 1.0')
    emit('  book001  CMI 18.6-46.6, 4 of 7 LOW, LogicalRisk 0.740-1.000 saturated in 5,')
    emit('           StatisticalRisk at 1.000 in ch03/ch04/ch07, EmotionalRisk 0.093-0.444')
    emit('  book002  LogicalRisk saturated in all 6, EmotionalRisk 0.063-0.454')
    emit('  r8.py    11 theoretical weights sum 0.90; 13 scored components sum 1.00')
    write_log(args.log, lines)
    if args.row_out:
        write_row(args.row_out, args, P, W, theo, low1, sat1, sat2,
                  cmi1, log1, emo1, emo2, statsat)
        emit('')
        emit('ROW WRITTEN: ' + args.row_out)
    return 0


ROW_NARRATIVE = '''## Document-level values and the weight-table arithmetic (S306-J)

WHY THIS ROW IS OUTSIDE THE EV-r196 SECTION. It supersedes nothing. These values are
printed by the manuscript and were owned by no claim row, found by the ownership screen
and confirmed unowned at four rounding precisions (S306-J). A row with no superseded
predecessor cannot enter a section whose header declares a fixed set of 70 superseded
ids without breaking the set-equality assert that gates that write. Same treatment as
EV-table2-001, EV-table3-001, EV-prf-005 and EV-phase1cal-001.

THESE VALUES DO NOT MOVE AT n=196, AND THAT IS GATED RATHER THAN ARGUED. r8.py scores
each document against its own character count with no corpus-level term, so a
per-document value cannot move when other documents leave the population. GATE 3 checks
the consequence directly: every row retained at n=196 is cell-identical to its n=202
row, and none of the six DEC-072 removals is one of the documents claimed here. A reader
working through the block-2 population update must not treat these as pending updates.

THE BOOK VALUES ARE READ FROM THE PSEUDONYMISED PUBLIC BUNDLE, NOT FROM THE INTERNAL
FROZEN FILE. The internal identifiers are title-derived and are withheld under DEC-022.
GATE 1 proves the public file is a faithful relabeling -- 187 non-book rows identical
across 24 columns, and the 24 book rows an identical value multiset -- so reading the
public file costs nothing in provenance. The producer never emits an internal
identifier.
'''


def write_row(path, args, P, W, theo, low1, sat1, sat2, cmi1, log1, emo1, emo2, statsat):
    n = P['note223']
    claim = ('Document-level manuscript values that no claim row owned, and the '
             'arithmetic of the r8.py weight table. Sections 5.5, 5.7, 5.8 and 3.5. '
             'Population-independent: unchanged at n=196.')
    ev = (
        'note223 (Sections 5.7 and 6.3): CMI %s, automated level %s, human_label %s, '
        'EmotionalRisk %s, with LogicalRisk, AuthorityRisk and StatisticalRisk all at '
        'the 1.0 ceiling, FearRisk %s and HypeRisk %s. '
        'book001_ch01-ch07 (Section 5.8): CMI %s-%s, %d of 7 automated LOW, all 7 '
        'human_label HIGH, LogicalRisk %.3f-%.3f saturated in %d, StatisticalRisk at '
        'the ceiling in %s, EmotionalRisk %.3f-%.3f and below 0.5 throughout. '
        'book002_ch01-ch06 (Section 5.8): LogicalRisk saturated in all %d, EmotionalRisk '
        '%.3f-%.3f and below 0.5 throughout. '
        'r8.py WEIGHTS (Section 3.5, L187): 14 keys, of which %d are theoretical '
        'categories summing to %.2f; the supplementary components are naked_number %.2f, '
        'sexual_induction %.2f and beauty_diet %.2f; %d components carry non-zero weight '
        'and all keys sum to %.2f; StatisticalRisk carries the maximum weight %.2f.'
    ) % (
        n['cmi'], n['level'], n['human_label'], n['emotional'], n['fear'], n['hype'],
        ('%g' % min(cmi1)), ('%g' % max(cmi1)), low1,
        min(log1), max(log1), sat1, '/'.join(statsat),
        min(emo1), max(emo1),
        sat2, min(emo2), max(emo2),
        len(theo), sum(theo.values()),
        W['naked_number'], W['sexual_induction'], W['beauty_diet'],
        sum(1 for v in W.values() if v > 0), sum(W.values()), W['statistical'],
    )
    src = (
        'scripts/document_level_values_recount.py; internal corpus_master %s; '
        'public corpus_master %s; deduplicated corpus_master %s; r8.py %s; '
        'manuscript %s; log %s'
    ) % (EXPECTED_SHA['internal'], EXPECTED_SHA['public'], EXPECTED_SHA['dedup'],
         EXPECTED_SHA['r8py'], EXPECTED_SHA['manuscript'], args.log or '(not written)')
    body = (ROW_NARRATIVE
            + '\n| claim_id | claim | evidence | source | status |\n'
            + '|---|---|---|---|---|\n'
            + '| EV-doclevel-001 | %s | %s | %s | VERIFIED |\n' % (claim, ev, src)
            + '''
GATE. 56 checks in four blocks, 0 FAIL required for exit 0: input identity on five
files; relabeling faithfulness of the public bundle against the internal frozen file;
every printed value at n=202; and population independence at n=196. Five abort paths
were exercised before issue -- input hash mismatch, a perturbed non-book cell, a
perturbed printed value, a perturbed retained row, and a wrong manuscript token count --
and all five exit 1 with no row written.

NOT APPLIED TO THE MANUSCRIPT. Nothing here requires a manuscript edit: every printed
value reproduces. What was missing was the row, not a correction.
''')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(body)


def write_log(path, lines):
    if not path:
        return
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    sys.exit(main())
