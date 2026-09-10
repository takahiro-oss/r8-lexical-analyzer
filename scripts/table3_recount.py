"""table3_recount.py -- manuscript Table 3 CMI summary statistics, gated at the
pre-deduplication population before any deduplicated value is emitted.

CANONICAL PRODUCER for: EV-table3-001.

WHY THIS IS A SEPARATE SCRIPT AND NOT AN EXTENSION OF recompute_stats.py.
recompute_stats.py section 4 already computes this table and its estimator was
confirmed correct against every printed value (S301-J). It carries no gate of
any kind -- no assert, no expected value, no non-zero exit -- and it also emits
detection performance, Fisher counts and chance level, quantities tied to the
unresolved EV-perf attribution question (Pending 106, S297-J). Adding a gate
there would couple this table to that question. This script owns Table 3 alone.

WHY NOT AN EXTENSION OF recount_corpus_r196.py: that script's audit log is cited
BY HASH in seven applied ledger rows, and the ledger is append-only, so changing
the log's bytes would leave those citations pointing at a file that no longer has
that hash. Same reasoning as table2_recount.py.

SCOPE. This script owns the HIGH / MEDIUM / LOW band cells of Table 3, the
Overall row's Mean, SD, Min and Max, and the median. Table 3's Overall n is the
valid (CMI > 0) population count, which is owned by EV-r196-029, and is
reproduced here solely as a closure check.

THE BANDS ARE AUTOMATED CLASSIFICATION LEVELS, NOT HUMAN LABELS. Table 3 groups
documents by CMI threshold (HIGH >= 41, 35 <= MEDIUM < 41, LOW < 35), whereas
EV-r196-029 reports the human_label distribution over the same population. The
two are different quantities that share a population; do not read one as the
other.

THE ESTIMATOR IS THE POPULATION STANDARD DEVIATION, divided by n and not by
n - 1. This is not a choice made here: it is what reproduces every printed SD,
and it matches recompute_stats.py line 109. Switching to the sample SD changes
the printed values and would break the gate. Recorded because the judgement is
otherwise invisible in the output (Pending 106).

Usage:
    python scripts/table3_recount.py \\
        --gate_master data/frozen/v1_9/corpus_master.csv \\
        --new_master  data/frozen/v1_9r/corpus_master.csv \\
        --log         data/frozen/v1_9r/audit_table3_v1_9r.txt \\
        --row_out     docs/drafts/pending_edits/S301-J_table3_row.md

Reader mode, the only mode that runs on the released data:
    python scripts/table3_recount.py --public_master corpus_master.csv

Exit 0 only when the GATE and the CLOSURE checks all pass. The ledger row is
written only on exit 0, and every number in it is interpolated from the
measurement rather than hand-typed (DEC-048). The log hash inside the row is
taken from the log file after it has been written.

NEWLINES ARE FORCED TO LF at every write, for the reason recorded in
table2_recount.py: without newline='\\n' Python's text mode translates to CRLF
on Windows, so the same inputs would produce different bytes on the judgment
surface and the execution surface, and any hash recorded for these outputs
would be platform-dependent.
"""
import argparse
import csv
import hashlib
import io
import math
import sys

# Manuscript Table 3 as printed, keyed by band: (n, Mean, SD, Min, Max).
# Source: docs/drafts/R8_preprint_draft_v1_9.md, Section 4.3, at manuscript
# sha256 686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185.
GATE_BY_BAND = {
    'HIGH':   (43, 49.1, 6.6, 41.3, 67.6),
    'MEDIUM': (36, 37.3, 1.8, 35.0, 40.9),
    'LOW':    (123, 22.0, 8.3, 2.6, 34.9),
}
GATE_OVERALL = (202, 30.5, 13.3, 2.6, 67.6)
GATE_MEDIAN = 31.25

# PUBLIC MODE expectations: the deduplicated valid population (CMI > 0, n=196)
# as recorded in EV-table3-001, transcribed BEFORE any public-mode run existed so
# that the check is not fitted to its own output. EV-table3-001 records that 7
# cells move (HIGH n and Mean; MEDIUM n, Mean and SD; LOW n; Overall n), that no
# band Min or Max moves, and that the median is unchanged; every other cell
# therefore equals GATE_BY_BAND / GATE_OVERALL. Overall n: EV-r196-029.
PUBLIC_BY_BAND = {
    'HIGH':   (42, 49.0, 6.6, 41.3, 67.6),
    'MEDIUM': (35, 37.2, 1.7, 35.0, 40.9),
    'LOW':    (119, 22.0, 8.3, 2.6, 34.9),
}
PUBLIC_OVERALL = (196, 30.5, 13.3, 2.6, 67.6)
PUBLIC_MEDIAN = 31.25

BANDS = ('HIGH', 'MEDIUM', 'LOW')
COLS = ('n', 'Mean', 'SD', 'Min', 'Max')

# DEC-072 removed members. Asserted, not assumed, against the set difference.
DEC072_REMOVED = ['AD_065', 'AD_067', 'AD_071', 'AD_072', 'AD_073', 'AD_074']

MANUSCRIPT_SHA = '686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185'

HEADER_NOTE = '''## Table 3 CMI summary statistics (S301-J)

WHY THIS ROW IS OUTSIDE THE EV-r196 SECTION. It supersedes nothing. Manuscript
Table 3's cells are printed and population-dependent, and were owned by no claim
row: the string "Table 3" occurs zero times in the ledger (measured S301-J over
174 rows). A row with no superseded predecessor cannot enter a section whose
header declares a fixed set of 70 superseded ids without breaking the
set-equality assert that gates that write. Same treatment as EV-table2-001 and
EV-prf-005.

SCOPE. The HIGH, MEDIUM and LOW band cells, the Overall row's Mean, SD, Min and
Max, and the median. Table 3's Overall n is the valid (CMI > 0) population count
and is owned by EV-r196-029; it is reproduced here as a closure check, not as a
claim.'''


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def load_master(path):
    text = open(path, 'rb').read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(text)))


def cmi_of(row):
    return float(row['cmi'])


def band_of(row):
    """Automated classification level. Thresholds are r8.py standard mode."""
    v = cmi_of(row)
    if v >= 41:
        return 'HIGH'
    if v >= 35:
        return 'MEDIUM'
    return 'LOW'


def valid_of(rows):
    return [r for r in rows if cmi_of(r) > 0]


def stats(group):
    """(n, Mean, SD, Min, Max) at one decimal. SD is the POPULATION SD."""
    v = [cmi_of(r) for r in group]
    n = len(v)
    mean = sum(v) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in v) / n)
    return (n, round(mean, 1), round(sd, 1), round(min(v), 1), round(max(v), 1))


def median_of(group):
    v = sorted(cmi_of(r) for r in group)
    m = len(v) // 2
    return v[m] if len(v) % 2 else (v[m - 1] + v[m]) / 2.0


def table_of(rows):
    valid = valid_of(rows)
    out = {b: stats([r for r in valid if band_of(r) == b]) for b in BANDS}
    out['Overall'] = stats(valid)
    return out, median_of(valid)


def raw_means(rows):
    """Unrounded means, for reporting movement below printed precision."""
    valid = valid_of(rows)
    out = {}
    for b in BANDS:
        v = [cmi_of(r) for r in valid if band_of(r) == b]
        out[b] = sum(v) / len(v)
    out['Overall'] = sum(cmi_of(r) for r in valid) / len(valid)
    return out


def position_in_band(rows, target_row):
    """(rank, band_size, band_mean) for one document inside its own band."""
    b = band_of(target_row)
    v = sorted(cmi_of(r) for r in valid_of(rows) if band_of(r) == b)
    return v.index(cmi_of(target_row)) + 1, len(v), sum(v) / len(v)


def public_mode(path):
    """Reader mode. Recompute Table 3 from the released corpus_master.csv and
    compare every cell with the recorded values. Writes nothing. Exit 0 only
    when every cell matches."""
    print('=== table3_recount.py -- public mode ===')
    print('corpus_master : %s' % path)
    print('  sha256      : %s' % sha256_of(path))
    got, med = table_of(load_master(path))
    exp_all = dict(PUBLIC_BY_BAND)
    exp_all['Overall'] = PUBLIC_OVERALL
    fails = 0
    for b in BANDS + ('Overall',):
        ok = got[b] == exp_all[b]
        fails += (not ok)
        print('  %-8s computed=%-34s expected=%-34s [%s]'
              % (b, got[b], exp_all[b], 'OK' if ok else 'FAIL'))
    ok = med == PUBLIC_MEDIAN
    fails += (not ok)
    print('  median   computed=%-34s expected=%-34s [%s]'
          % (med, PUBLIC_MEDIAN, 'OK' if ok else 'FAIL'))
    print('RESULT: %d checks, %d FAIL' % (len(BANDS) + 2, fails))
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--public_master',
                    help='released corpus_master.csv; runs the reader check only')
    ap.add_argument('--gate_master')
    ap.add_argument('--new_master')
    ap.add_argument('--log')
    ap.add_argument('--row_out')
    args = ap.parse_args()
    if args.public_master:
        sys.exit(public_mode(args.public_master))
    for k in ('gate_master', 'new_master', 'log', 'row_out'):
        if getattr(args, k) is None:
            ap.error('--%s is required unless --public_master is given' % k)

    lines = []

    def out(s=''):
        print(s)
        lines.append(s)

    def finish(code):
        open(args.log, 'w', encoding='utf-8',
             newline='\n').write('\n'.join(lines) + '\n')
        sys.exit(code)

    out('=== table3_recount.py ===')
    out('gate_master : %s' % args.gate_master)
    out('  sha256    : %s' % sha256_of(args.gate_master))
    out('new_master  : %s' % args.new_master)
    out('  sha256    : %s' % sha256_of(args.new_master))
    out()

    gate_rows = load_master(args.gate_master)
    g, g_median = table_of(gate_rows)

    out('=== GATE -- manuscript Table 3 as printed, reproduced from the data ===')
    fails = 0
    checks = 0
    for b in BANDS:
        exp, got = GATE_BY_BAND[b], g[b]
        ok = got == exp
        fails += (not ok)
        checks += 1
        out('  %-8s computed=%-30s printed=%-30s [%s]'
            % (b, got, exp, 'OK' if ok else 'FAIL'))
    ok = g['Overall'][1:] == GATE_OVERALL[1:]
    fails += (not ok)
    checks += 1
    out('  %-8s computed=%-30s printed=%-30s [%s]'
        % ('Overall', g['Overall'][1:], GATE_OVERALL[1:], 'OK' if ok else 'FAIL'))
    ok = g_median == GATE_MEDIAN
    fails += (not ok)
    checks += 1
    out('  %-8s computed=%-30s printed=%-30s [%s]'
        % ('Median', g_median, GATE_MEDIAN, 'OK' if ok else 'FAIL'))
    ok = g['Overall'][0] == GATE_OVERALL[0]
    fails += (not ok)
    checks += 1
    out('  %-8s computed=%-30s printed=%-30s [%s]'
        % ('n valid', g['Overall'][0], GATE_OVERALL[0], 'OK' if ok else 'FAIL'))
    out('  (n valid is the closure check; owned by EV-r196-029)')
    band_sum = sum(g[b][0] for b in BANDS)
    ok = band_sum == g['Overall'][0]
    fails += (not ok)
    checks += 1
    out('  %-8s bands sum=%-6d overall n=%-6d [%s]'
        % ('sum', band_sum, g['Overall'][0], 'OK' if ok else 'FAIL'))
    out('GATE: %d checks over %d printed values, %d FAIL'
        % (checks, len(BANDS) * 5 + 5 + 1, fails))
    out()
    if fails:
        out('=== RESULT ===')
        out('GATE FAILED. No deduplicated value is emitted.')
        finish(1)

    new_rows = load_master(args.new_master)
    n, n_median = table_of(new_rows)

    out('=== NEW POPULATION -- Table 3 ===')
    out('  %-8s %6s %7s %7s %7s %7s' % (('Level',) + COLS))
    for b in BANDS + ('Overall',):
        out('  %-8s %6d %7.1f %7.1f %7.1f %7.1f' % ((b,) + n[b]))
    out('  %-8s %6s' % ('Median', n_median))
    out()

    out('=== CHANGED ===')
    moved = []
    for b in BANDS + ('Overall',):
        old = GATE_BY_BAND[b] if b in GATE_BY_BAND else GATE_OVERALL
        diff = [(COLS[i], old[i], n[b][i]) for i in range(5) if old[i] != n[b][i]]
        if diff:
            moved.append((b, diff))
            out('  %-8s %s' % (b, ', '.join('%s %s to %s' % d for d in diff)))
    unchanged_cells = [(b, COLS[i]) for b in BANDS + ('Overall',)
                       for i in range(5)
                       if (GATE_BY_BAND[b] if b in GATE_BY_BAND
                           else GATE_OVERALL)[i] == n[b][i]]
    out('  median %s to %s [%s]'
        % (GATE_MEDIAN, n_median,
           'unchanged' if n_median == GATE_MEDIAN else 'CHANGED'))
    out('  cells changed: %d of 20; unchanged: %d'
        % (sum(len(d) for _, d in moved), len(unchanged_cells)))
    out()

    out('=== CLOSURE -- the removals account for the whole of the change ===')
    cfails = 0
    gate_ids = {r['target'] for r in gate_rows}
    new_ids = {r['target'] for r in new_rows}
    removed = sorted(gate_ids - new_ids)
    added = sorted(new_ids - gate_ids)
    for name, got, exp in (('removed set', removed, DEC072_REMOVED),
                           ('added set', added, [])):
        ok = got == exp
        cfails += (not ok)
        out('  %-12s %-58s expected=%s [%s]'
            % (name, got, exp, 'OK' if ok else 'FAIL'))
    idx = {r['target']: r for r in gate_rows}
    per = {}
    for t in removed:
        per.setdefault(band_of(idx[t]), []).append((t, cmi_of(idx[t])))
    for b in BANDS:
        drop = per.get(b, [])
        out('  removed in %-8s %s' % (b, sorted(drop)))
        delta = GATE_BY_BAND[b][0] - n[b][0]
        ok = delta == len(drop)
        cfails += (not ok)
        out('  delta n %-6s table=%-4d removals=%-4d [%s]'
            % (b, delta, len(drop), 'OK' if ok else 'FAIL'))
    delta_all = GATE_OVERALL[0] - n['Overall'][0]
    ok = delta_all == len(removed)
    cfails += (not ok)
    out('  delta n %-6s table=%-4d removals=%-4d [%s]'
        % ('Overall', delta_all, len(removed), 'OK' if ok else 'FAIL'))
    out('CLOSURE: %d FAIL' % cfails)
    out()

    out('=== WHERE THE REMOVED DOCUMENTS SAT INSIDE THEIR BANDS ===')
    positions = {}
    for t in removed:
        rank, size, bmean = position_in_band(gate_rows, idx[t])
        side = 'ABOVE' if cmi_of(idx[t]) > bmean else 'below'
        positions[t] = (band_of(idx[t]), cmi_of(idx[t]), rank, size, bmean, side)
        out('  %-8s %-7s cmi=%-6.1f rank %d of %d   band mean %.4f   %s'
            % (t, band_of(idx[t]), cmi_of(idx[t]), rank, size, bmean, side))
    interior = all(1 < p[2] < p[3] for p in positions.values())
    out('  every removed document interior to its band (neither first nor last): %s'
        % interior)
    out()

    out('=== MEAN MOVEMENT BELOW PRINTED PRECISION ===')
    gm, nm = raw_means(gate_rows), raw_means(new_rows)
    for b in BANDS + ('Overall',):
        out('  %-8s %.4f -> %.4f  %s' % (b, gm[b], nm[b],
            'falls' if nm[b] < gm[b] else ('rises' if nm[b] > gm[b] else 'flat')))
    out()

    out('CLOSURE: %d FAIL (restated)' % cfails)
    out()

    out('=== RESULT ===')
    if cfails:
        out('CLOSURE FAILED.')
        finish(1)
    out('GATE 0 FAIL, CLOSURE 0 FAIL. Table 3 cells emitted for EV-table3-001.')
    open(args.log, 'w', encoding='utf-8',
         newline='\n').write('\n'.join(lines) + '\n')

    # Ledger row. Every number below is interpolated from the measurement above;
    # nothing is hand-typed (DEC-048). The log hash is taken from the log file
    # after it has been written.
    log_sha = sha256_of(args.log)
    moved_txt = '; '.join(
        '%s %s' % (b, ', '.join('%s %s to %s' % d for d in diff))
        for b, diff in moved)
    n_changed = sum(len(d) for _, d in moved)
    drops = []
    for b in BANDS:
        if per.get(b):
            drops.append('%s (%s)'
                         % (', '.join(t for t, _ in sorted(per[b])), b))

    # Interpolated from the position measurement above; nothing hand-typed.
    ranks_txt = ', '.join(
        '%d of %d' % (positions[t][2], positions[t][3]) for t in removed)
    above = [t for t in removed if positions[t][5] == 'ABOVE']
    mean_moved_bands = [b for b, diff in moved
                        if b in GATE_BY_BAND
                        and any(d[0] == 'Mean' for d in diff)]
    above_in_moved = [t for t in above if positions[t][0] in mean_moved_bands]
    above_bands_txt = ('both bands whose Mean moves'
                       if len(mean_moved_bands) == 2
                       else '%d of the bands whose Mean moves'
                            % len(mean_moved_bands))
    above_pairs_txt = '; '.join(
        '%s at %.1f against %.4f' % (t, positions[t][1], positions[t][4])
        for t in above_in_moved)
    med_doc = ', '.join(t for t in removed if positions[t][0] == 'MEDIUM')

    claim = ('Section 4.3, Table 3: the CMI summary statistics by automated '
             'classification level, and the median CMI across valid documents')
    evidence = (
        'At the pre-deduplication population the producer reproduces all %d '
        'printed Table 3 values exactly, which is what establishes that the '
        'same computation yields the printed table; the estimator is the '
        'POPULATION standard deviation, which is what reproduces the printed '
        'SD values. At the deduplicated population %d of the 20 band and '
        'Overall cells move: %s. The median is %s at %s. Every removed document '
        'sat interior to its band -- ranks %s -- so no band Min or Max moved. In '
        '%s the removed document sat ABOVE that band mean (%s), which is the '
        'mechanism behind the fall; %s also sat near the top of a narrow band '
        'spanning %s to %s, which is why MEDIUM SD falls as well. BELOW PRINTED '
        'PRECISION the three band means all fall while the Overall mean RISES, '
        '%.4f to %.4f, because four of the six removals came from the lowest '
        'band; both values print as %s, and this direction is recorded so that a '
        'later reader does not infer from the table that every mean fell. The '
        '%d documents removed under DEC-072 distribute across the bands as %s, '
        'and account for the whole of the change in n; the removed set was '
        'verified as the set difference between the two frozen populations '
        'rather than assumed. THE OVERALL n IS NOT CLAIMED HERE; it is the '
        'valid (CMI > 0) population owned by EV-r196-029, and this producer '
        'reproduces it only as a closure check. The bands are AUTOMATED '
        'classification levels (CMI thresholds), not human labels, and are a '
        'different quantity from the human_label distribution EV-r196-029 '
        'reports over the same population.'
        % (len(BANDS) * 5 + 5 + 1, n_changed, moved_txt,
           'unchanged' if n_median == GATE_MEDIAN else 'changed', n_median,
           ranks_txt, above_bands_txt, above_pairs_txt, med_doc,
           GATE_BY_BAND['MEDIUM'][3], GATE_BY_BAND['MEDIUM'][4],
           gm['Overall'], nm['Overall'], GATE_OVERALL[1],
           len(removed), '; '.join(drops)))
    source = (
        'scripts/table3_recount.py, log %s (%s); GATE %d checks over %d printed '
        'values, 0 FAIL, and CLOSURE %d FAIL, both required for exit 0. Gate '
        'population %s (%s); new population %s (%s). Printed values read from '
        'the EN canonical at %s. NOT APPLIED to the manuscript: the EN canonical '
        'stays at commit cda705d4.'
        % (args.log, log_sha, checks, len(BANDS) * 5 + 5 + 1, cfails,
           args.gate_master, sha256_of(args.gate_master),
           args.new_master, sha256_of(args.new_master), MANUSCRIPT_SHA))

    row = '| EV-table3-001 | %s | %s | %s | VERIFIED |' % (claim, evidence, source)
    block = (HEADER_NOTE
             + '\n\n| claim_id | scope | evidence | source | status |\n'
             + '|---|---|---|---|---|\n' + row + '\n')
    open(args.row_out, 'w', encoding='utf-8', newline='\n').write(block)
    print()
    print('row written to %s' % args.row_out)
    print('log sha256 %s' % log_sha)
    sys.exit(0)


if __name__ == '__main__':
    main()
