"""phase1_calibration_recount.py -- the Phase 1 calibration passage, gated at the
pre-deduplication population before any deduplicated value is emitted.

CANONICAL PRODUCER for: EV-phase1cal-001.

SCOPE. The six values the manuscript prints TWICE, at Section 6.1 and again at
Section 7.2, both of which must move together:
    42 of 43   HIGH-classified documents whose human_label is HIGH
    1 of 43, 2.3%   false discovery within the HIGH-classified group
    112 of 123, 91.1%   LOW-classified documents whose human_label is MEDIUM or HIGH
    n = 43, 21.3%   HIGH-classified share of the valid population
    n = 159, 78.7%  MEDIUM plus LOW share of the valid population
    202 valid cases, 9 of 211 at CMI = 0.0
The valid population count itself is owned by EV-r196-029 and the band counts by
EV-table3-001; both are reproduced here only as closure checks.

THE BANDS ARE AUTOMATED CLASSIFICATION LEVELS AND human_label IS THE HUMAN
JUDGEMENT. Every quantity here is a CROSS-TABULATION of the two, which is what
distinguishes this passage from Table 3 (bands alone) and from EV-r196-029
(human_label alone). Do not read any value here as either of those.

A NEAR-NEIGHBOUR WARNING, MEASURED AND RECORDED BECAUSE IT WILL RECUR.
EV-kappa-003 records "riskfactor_1 21.3% (43/202)". That is the same arithmetic
as this passage's HIGH-classified share and a different quantity: it counts the
author's QA meta-tag usage, not documents in the HIGH band. A ledger search on
the string 21.3 returns it. Presence is not ownership (Pending 113 cluster (2)).

THE GATE FINDS ONE PRINTED VALUE WRONG AT n=202, AND THAT IS THE DESIGN.
The manuscript prints "112 of 123 ... (91.1%)". The frozen pre-deduplication
data give 113 of 123 = 91.8699%. This is a subtraction error made at commit
8141fbd (2026-06-12, corpus 216 -> 211), traced S303-J: the deduplication removed
three LOW-classified documents, so the DENOMINATOR correctly went 126 -> 123, but
only two of those three were inside the numerator, and three were subtracted from
both. So the gate reports one FAIL against the printed values and that FAIL is
enumerated in EXPECTED_DEFECTS below.

WHY THE DEFECT IS ENUMERATED RATHER THAN ABSORBED OR LEFT AS A BARE FAIL.
Absorbing it -- gating against the measured 113 and saying nothing -- would make
this producer bless a printed value it knows to be wrong. Leaving a bare FAIL
would create a permanently failing check, which is the state Pending 69 records
as the one people learn to step past. Enumerating it is self-terminating: the
run asserts that the manuscript STILL prints 112, so when block 2 corrects the
passage that assertion fails loudly and this producer must be updated in the same
window, rather than silently continuing to expect a value that is no longer there.

Usage:
    python scripts/phase1_calibration_recount.py \
        --gate_master data/frozen/v1_9/corpus_master.csv \
        --new_master  data/frozen/v1_9r/corpus_master.csv \
        --manuscript  docs/drafts/R8_preprint_draft_v1_9.md \
        --log         data/frozen/v1_9r/audit_phase1_calibration_v1_9r.txt \
        --row_out     docs/drafts/pending_edits/S305-J_phase1_calibration_row.md

Reader mode, the only mode that runs on the released data:
    python scripts/phase1_calibration_recount.py --public_master corpus_master.csv

--manuscript is optional. When given, the file's sha256 is asserted against
MANUSCRIPT_SHA and the RECOVERY GUARD 4 count assertion is run: the string 91.1
must occur EXACTLY THREE times, two of them this passage and one at Section 4.3
being the Claude majority-vote agreement rate, a different quantity that must not
be edited. Block 2 needs that count before it may touch the passage.

Exit 0 only when the GATE is clean against EXPECTED_DEFECTS and every CLOSURE
check passes. The ledger row is written only on exit 0 and every number in it is
interpolated from the measurement rather than hand-typed (DEC-048).

NEWLINES ARE FORCED TO LF at every write, so that the same inputs produce the
same bytes on the judgment surface and on the execution surface and any hash
recorded for these outputs is not platform-dependent.
"""
import argparse
import csv
import hashlib
import io
import sys

# The passage as printed, at manuscript sha256 MANUSCRIPT_SHA.
# key -> (printed value, what it is)
GATE_PRINTED = {
    'valid_n':        202,
    'cmi0_excluded':    9,
    'corpus_n':       211,
    'high_n':          43,
    'low_n':          123,
    'high_human_high': 42,
    'fd_numerator':     1,
    'fd_pct':         2.3,
    'high_pct':      21.3,
    'medlow_n':       159,
    'medlow_pct':    78.7,
    'low_mh_n':       112,   # WRONG at n=202; see EXPECTED_DEFECTS
    'low_mh_pct':    91.1,   # WRONG at n=202; follows from low_mh_n
}

# key -> (printed, measured). A FAIL is admissible only if it is listed here
# with exactly these two values. Any other FAIL, or the absence of one of these,
# stops the run.
EXPECTED_DEFECTS = {
    'low_mh_n':   (112, 113),
    'low_mh_pct': (91.1, 91.9),
}

DEC072_REMOVED = ['AD_065', 'AD_067', 'AD_071', 'AD_072', 'AD_073', 'AD_074']

# PUBLIC MODE expectations: the deduplicated population, transcribed from
# EV-phase1cal-001 BEFORE any public-mode run existed so that the check is not
# fitted to its own output. corpus_n and cmi0_excluded: EV-r196-029 (n = 205, the
# nine CMI = 0.0 documents unchanged by DEC-072). low_mh_n is the measured 109,
# not a printed value: the n=202 printing of 112 was a subtraction error.
PUBLIC_EXPECT = {
    'corpus_n':       205,
    'cmi0_excluded':    9,
    'valid_n':        196,
    'high_n':          42,
    'low_n':          119,
    'high_human_high': 41,
    'fd_numerator':     1,
    'fd_pct':         2.4,
    'high_pct':      21.4,
    'medlow_n':       154,
    'medlow_pct':    78.6,
    'low_mh_n':       109,
    'low_mh_pct':    91.6,
}

MANUSCRIPT_SHA = '686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185'
GUARD4_TOKEN = '91.1'
GUARD4_COUNT = 3

ORDER = ['corpus_n', 'cmi0_excluded', 'valid_n', 'high_n', 'low_n',
         'high_human_high', 'fd_numerator', 'fd_pct', 'high_pct',
         'medlow_n', 'medlow_pct', 'low_mh_n', 'low_mh_pct']


def sha256_of(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_master(path):
    with open(path, 'rb') as fh:
        raw = fh.read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(raw)))


def measure(rows):
    """Every quantity in the passage, from one pass over the master."""
    valid = [r for r in rows if float(r['cmi']) > 0]
    high = [r for r in valid if r['level'] == 'HIGH']
    med = [r for r in valid if r['level'] == 'MEDIUM']
    low = [r for r in valid if r['level'] == 'LOW']
    high_hh = [r for r in high if r['human_label'] == 'HIGH']
    fd = [r for r in high if r['human_label'] != 'HIGH']
    low_mh = [r for r in low if r['human_label'] in ('MEDIUM', 'HIGH')]
    m = {
        'corpus_n': len(rows),
        'cmi0_excluded': len(rows) - len(valid),
        'valid_n': len(valid),
        'high_n': len(high),
        'medium_n': len(med),
        'low_n': len(low),
        'high_human_high': len(high_hh),
        'fd_numerator': len(fd),
        'fd_pct': round(100.0 * len(fd) / len(high), 1),
        'high_pct': round(100.0 * len(high) / len(valid), 1),
        'medlow_n': len(med) + len(low),
        'medlow_pct': round(100.0 * (len(med) + len(low)) / len(valid), 1),
        'low_mh_n': len(low_mh),
        'low_mh_pct': round(100.0 * len(low_mh) / len(low), 1),
    }
    m['_fd_exact'] = 100.0 * len(fd) / len(high)
    m['_high_exact'] = 100.0 * len(high) / len(valid)
    m['_medlow_exact'] = 100.0 * (len(med) + len(low)) / len(valid)
    m['_low_mh_exact'] = 100.0 * len(low_mh) / len(low)
    m['_fd_docs'] = sorted(r['target'] for r in fd)
    m['_low_human'] = {
        lab: sum(1 for r in low if r['human_label'] == lab)
        for lab in ('HIGH', 'MEDIUM', 'LOW')
    }
    return m


def public_mode(path):
    """Reader mode. Recompute the Phase 1 calibration passage from the released
    corpus_master.csv and compare every value with the recorded one. Writes
    nothing. Exit 0 only when every value matches."""
    print('phase1_calibration_recount.py -- public mode')
    print('corpus_master : %s' % path)
    print('                sha256 %s' % sha256_of(path))
    m = measure(load_master(path))
    fails = 0
    for k in ORDER:
        ok = m[k] == PUBLIC_EXPECT[k]
        fails += (not ok)
        print('  %-16s computed=%-8s expected=%-8s [%s]'
              % (k, m[k], PUBLIC_EXPECT[k], 'OK' if ok else 'FAIL'))
    print('RESULT: %d checks, %d FAIL' % (len(ORDER), fails))
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public_master',
                    help='released corpus_master.csv; runs the reader check only')
    ap.add_argument('--gate_master')
    ap.add_argument('--new_master')
    ap.add_argument('--manuscript', default=None)
    ap.add_argument('--log')
    ap.add_argument('--row_out')
    a = ap.parse_args()
    if a.public_master:
        sys.exit(public_mode(a.public_master))
    for k in ('gate_master', 'new_master', 'log', 'row_out'):
        if getattr(a, k) is None:
            ap.error('--%s is required unless --public_master is given' % k)

    lines = []

    def out(s=''):
        print(s)
        lines.append(s)

    def finish(code):
        with open(a.log, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('\n'.join(lines) + '\n')
        sys.exit(code)

    gate_sha = sha256_of(a.gate_master)
    new_sha = sha256_of(a.new_master)

    out('phase1_calibration_recount.py -- EV-phase1cal-001')
    out('gate_master : %s' % a.gate_master)
    out('              sha256 %s' % gate_sha)
    out('new_master  : %s' % a.new_master)
    out('              sha256 %s' % new_sha)
    out('manuscript  : %s' % (a.manuscript or '(not supplied)'))
    out()

    # ---------------- GUARD 4 --------------------------------------------
    if a.manuscript:
        ms_sha = sha256_of(a.manuscript)
        ok_sha = ms_sha == MANUSCRIPT_SHA
        out('MANUSCRIPT sha256 %s   expected %s   %s'
            % (ms_sha, MANUSCRIPT_SHA, 'OK' if ok_sha else 'FAIL'))
        with open(a.manuscript, 'rb') as fh:
            body = fh.read().decode('utf-8-sig')
        n_tok = body.count(GUARD4_TOKEN)
        ok_tok = n_tok == GUARD4_COUNT
        out('RECOVERY GUARD 4: occurrences of %r = %d, expected %d   %s'
            % (GUARD4_TOKEN, n_tok, GUARD4_COUNT, 'OK' if ok_tok else 'FAIL'))
        out('  two of the three are this passage; the third is the Claude '
            'majority-vote rate at Section 4.3 and is a different quantity.')
        if not (ok_sha and ok_tok):
            out('MANUSCRIPT CHECK FAILED. No value is emitted.')
            finish(1)
        out()

    # ---------------- GATE ------------------------------------------------
    g = measure(load_master(a.gate_master))
    out('GATE at the pre-deduplication population, against the printed passage')
    fails = {}
    for k in ORDER:
        exp = GATE_PRINTED[k]
        got = g[k]
        ok = got == exp
        if not ok:
            fails[k] = (exp, got)
        out('  %-16s printed %-8s measured %-8s %s'
            % (k, exp, got, 'OK' if ok else 'FAIL'))
    out('GATE: %d checks over %d printed values, %d FAIL'
        % (len(ORDER), len(ORDER), len(fails)))
    out()

    out('EXPECTED_DEFECTS reconciliation')
    admissible = True
    for k, (exp, meas) in EXPECTED_DEFECTS.items():
        if k not in fails:
            out('  %-16s DECLARED DEFECT DID NOT OCCUR -- the manuscript no '
                'longer prints %s. Update this producer.' % (k, exp))
            admissible = False
            continue
        got_exp, got_meas = fails[k]
        ok = (got_exp, got_meas) == (exp, meas)
        out('  %-16s printed %-8s measured %-8s declared (%s, %s)   %s'
            % (k, got_exp, got_meas, exp, meas, 'OK' if ok else 'FAIL'))
        if not ok:
            admissible = False
    for k in fails:
        if k not in EXPECTED_DEFECTS:
            out('  %-16s UNDECLARED FAIL. Stop.' % k)
            admissible = False
    out('EXPECTED_DEFECTS: %s' % ('reconciled' if admissible else 'NOT reconciled'))
    out()

    if not admissible:
        out('GATE FAILED. No deduplicated value is emitted.')
        finish(1)

    out('THE DEFECT, STATED IN FULL SO THE CLAIM ROW CANNOT UNDERSTATE IT.')
    out('  The manuscript prints 112 of 123 (91.1%). The frozen '
        'pre-deduplication data give')
    out('  %d of %d = %.4f%%. The printed value was ALREADY WRONG at n=202; '
        'the correction'
        % (g['low_mh_n'], g['low_n'], g['_low_mh_exact']))
    out('  therefore superimposes a subtraction error on a population change '
        'and is NOT a pure')
    out('  population update (RECOVERY GUARD 5).')
    out('  LOW-classified human_label distribution at n=202: %s, closing at %d.'
        % (g['_low_human'], g['low_n']))
    out('  The single false-discovery document is %s.' % ', '.join(g['_fd_docs']))
    out()

    # ---------------- NEW POPULATION --------------------------------------
    n = measure(load_master(a.new_master))
    out('DEDUPLICATED POPULATION')
    for k in ORDER:
        out('  %-16s n=202 %-8s ->  n=196 %-8s' % (k, g[k], n[k]))
    out('  %-16s n=202 %-8s ->  n=196 %-8s'
        % ('medium_n', g['medium_n'], n['medium_n']))
    out('  exact percentages at n=196: fd %.4f  high %.4f  medlow %.4f  low_mh %.4f'
        % (n['_fd_exact'], n['_high_exact'], n['_medlow_exact'], n['_low_mh_exact']))
    out('  LOW-classified human_label distribution at n=196: %s, closing at %d.'
        % (n['_low_human'], n['low_n']))
    out('  The single false-discovery document is %s.' % ', '.join(n['_fd_docs']))
    out()

    # ---------------- CLOSURE ---------------------------------------------
    gate_rows = load_master(a.gate_master)
    new_rows = load_master(a.new_master)
    gt = {r['target']: r for r in gate_rows}
    nt = {r['target']: r for r in new_rows}
    removed = sorted(set(gt) - set(nt))
    added = sorted(set(nt) - set(gt))

    out('CLOSURE -- the DEC-072 removals must account for the whole movement')
    cf = 0

    ok = removed == sorted(DEC072_REMOVED)
    cf += 0 if ok else 1
    out('  removed set      %s   %s' % (removed, 'OK' if ok else 'FAIL'))
    ok2 = added == []
    cf += 0 if ok2 else 1
    out('  added set        %s   %s' % (added, 'OK' if ok2 else 'FAIL'))

    d_low = d_lowmh = d_high = d_hh = 0
    for t in removed:
        r = gt[t]
        if float(r['cmi']) <= 0:
            continue
        if r['level'] == 'LOW':
            d_low += 1
            if r['human_label'] in ('MEDIUM', 'HIGH'):
                d_lowmh += 1
        if r['level'] == 'HIGH':
            d_high += 1
            if r['human_label'] == 'HIGH':
                d_hh += 1

    for name, base, delta, got in (
            ('low_n', g['low_n'], d_low, n['low_n']),
            ('low_mh_n', g['low_mh_n'], d_lowmh, n['low_mh_n']),
            ('high_n', g['high_n'], d_high, n['high_n']),
            ('high_human_high', g['high_human_high'], d_hh, n['high_human_high'])):
        ok = base - delta == got
        cf += 0 if ok else 1
        out('  %-16s %d - %d = %d   measured %d   %s'
            % (name, base, delta, base - delta, got, 'OK' if ok else 'FAIL'))

    ok = n['high_n'] + n['medium_n'] + n['low_n'] == n['valid_n']
    cf += 0 if ok else 1
    out('  bands sum        %d + %d + %d = %d   %s'
        % (n['high_n'], n['medium_n'], n['low_n'], n['valid_n'],
           'OK' if ok else 'FAIL'))

    ok = n['_fd_docs'] == g['_fd_docs']
    cf += 0 if ok else 1
    out('  fd document      survives the removal: %s   %s'
        % (n['_fd_docs'], 'OK' if ok else 'FAIL'))

    out('CLOSURE: %d FAIL' % cf)
    out()
    if cf:
        out('CLOSURE FAILED. No row is written.')
        finish(1)

    out('GATE reconciled against 2 declared defects, CLOSURE 0 FAIL. '
        'Values emitted for EV-phase1cal-001.')

    # ---------------- ROW --------------------------------------------------
    with open(a.log, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    log_sha = sha256_of(a.log)

    row = ROW_TEMPLATE.format(
        gate_sha=gate_sha, new_sha=new_sha, log=a.log, log_sha=log_sha,
        ms_sha=MANUSCRIPT_SHA,
        g_low_mh=g['low_mh_n'], g_low=g['low_n'], g_low_pct=g['_low_mh_exact'],
        n_low_mh=n['low_mh_n'], n_low=n['low_n'], n_low_pct=n['_low_mh_exact'],
        n_low_pct1=n['low_mh_pct'],
        g_hh=g['high_human_high'], g_high=g['high_n'],
        n_hh=n['high_human_high'], n_high=n['high_n'],
        g_fd_pct=g['fd_pct'], n_fd_pct=n['fd_pct'], n_fd_exact=n['_fd_exact'],
        g_high_pct=g['high_pct'], n_high_pct=n['high_pct'],
        n_high_exact=n['_high_exact'],
        g_medlow=g['medlow_n'], n_medlow=n['medlow_n'],
        g_medlow_pct=g['medlow_pct'], n_medlow_pct=n['medlow_pct'],
        n_medlow_exact=n['_medlow_exact'],
        g_valid=g['valid_n'], n_valid=n['valid_n'],
        fd_doc=', '.join(n['_fd_docs']),
        removed=', '.join(removed),
        d_low=d_low, d_lowmh=d_lowmh, d_high=d_high, d_hh=d_hh,
    )
    with open(a.row_out, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(row)
    out('row written: %s  sha256 %s  %d bytes'
        % (a.row_out, sha256_of(a.row_out), len(row.encode('utf-8'))))
    sys.exit(0)


ROW_TEMPLATE = '''## Phase 1 calibration passage (S305-J)

WHY THIS ROW IS OUTSIDE THE EV-r196 SECTION. It supersedes nothing. The six
values are printed by the manuscript at Section 6.1 and repeated at Section 7.2,
are population-dependent, and were owned by no claim row. A ledger search on
their tokens returns only different quantities: 91.1 belongs to EV-kappa-007
(adjacent agreement 184/202) and EV-stability-001 (Claude 5/5 support 184/202),
and 21.3 belongs to EV-kappa-003 (riskfactor_1 QA meta-tag usage, 43/202 -- the
same arithmetic as the HIGH-classified share and a different quantity). Same
treatment as EV-table2-001, EV-table3-001 and EV-prf-005.

THIS IS NOT A PURE POPULATION UPDATE, and a reader who treats it as one will not
learn that the passage was ever wrong. Two changes are superimposed. (1) A
COUNTING ERROR AT n=202: the manuscript prints 112 of 123 LOW-classified
documents with a MEDIUM or HIGH human_label; the frozen pre-deduplication data
give {g_low_mh} of {g_low} = {g_low_pct:.4f}%. Traced S303-J to commit 8141fbd
(2026-06-12, corpus 216 -> 211), which removed three LOW-classified documents,
correctly moved the denominator 126 -> 123, and subtracted three from the
numerator when only two of the three were inside it. (2) THE POPULATION MOVE from
n=202 to n=196 under DEC-072. The corrected value carries both.

| claim_id | 主張 | 数値・根拠 | 出典 | status |
|---|---|---|---|---|
| EV-phase1cal-001 | Phase 1 calibration passage, Sections 6.1 and 7.2, at the deduplicated population. Cross-tabulation of the automated CMI band against human_label. Supersedes no earlier row: the values were unowned. | LOW-classified with human MEDIUM/HIGH {g_low_mh}/{g_low} ({g_low_pct:.4f}%) -> {n_low_mh}/{n_low} ({n_low_pct:.4f}% -> printed {n_low_pct1}%), manuscript printing 112 of {g_low} (91.1%) being WRONG at n=202 as well; HIGH-classified with human HIGH {g_hh}/{g_high} -> {n_hh}/{n_high}; false discovery within HIGH 1/{g_high} ({g_fd_pct}%) -> 1/{n_high} ({n_fd_exact:.4f}% -> {n_fd_pct}%), the document being {fd_doc}, which survives the DEC-072 removal; HIGH share {g_high_pct}% -> {n_high_exact:.4f}% ({n_high_pct}%); MEDIUM+LOW {g_medlow} ({g_medlow_pct}%) -> {n_medlow} ({n_medlow_exact:.4f}% -> {n_medlow_pct}%); valid population {g_valid} -> {n_valid}. Closure: removed {removed}, of which LOW {d_low} (all {d_lowmh} inside the numerator) and HIGH {d_high} (all {d_hh} with human HIGH), accounting for the whole movement. | scripts/phase1_calibration_recount.py; gate corpus_master {gate_sha}; new corpus_master {new_sha}; log {log} ({log_sha}); manuscript {ms_sha} | VERIFIED |

GATE. Thirteen printed values compared at n=202. Eleven reproduce. Two FAIL and
both are the single counting error above, declared in EXPECTED_DEFECTS in the
producer and reconciled by it; an undeclared FAIL, or the disappearance of a
declared one, stops the run and emits nothing. The declaration is
self-terminating: once block 2 corrects the passage the producer's assertion that
the manuscript still prints 112 fails loudly and the producer is updated in the
same window.

RECOVERY GUARD 4 IS IMPLEMENTED IN THE PRODUCER. With --manuscript supplied it
asserts the manuscript sha256 and that the string 91.1 occurs EXACTLY THREE
times. Two are this passage; the third is the Claude majority-vote agreement rate
at Section 4.3, a different quantity that must not be edited. Block 2 anchors on
surrounding words, never on the bare digits, and edits exactly two of the three.

NOT APPLIED TO THE MANUSCRIPT. The passage states manuscript values, so any edit
is a FREEZE_UNLOCK under DEC-025 and belongs to block 2.
'''


if __name__ == '__main__':
    main()
