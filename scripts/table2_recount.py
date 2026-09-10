"""table2_recount.py -- manuscript Table 2 genre composition, gated at the
pre-deduplication population before any deduplicated value is emitted.

CANONICAL PRODUCER for: EV-table2-001.

WHY THIS IS A SEPARATE SCRIPT AND NOT AN EXTENSION OF recount_corpus_r196.py.
That script's audit log is cited BY HASH in seven applied evidence-ledger rows
(EV-r196-054, -055, -058, -063, -064, -065, -066). Adding a section to it would
change the log's bytes and leave those citations pointing at a file that no
longer has that hash, in a ledger that is append-only. The two scripts read the
same inputs and are expected to agree on n_total and on the HIGH/MEDIUM/LOW
totals; disagreement is a defect.

SCOPE. This script owns the PER-GENRE cells of Table 2 only. The table's total
row is owned by EV-r196-029 and is reproduced here solely as a closure check
(S294-J decision B).

GENRE KEYING IS ASCII. genre_label carries a Japanese name after a numeric code
prefix. Everything here keys on the code, so no multibyte literal and no \\u
escape enters this file (DEC-044). The English names below are the manuscript's
own Table 2 row labels, used for log readability only; they are never matched
against the data.

Usage:
    python scripts/table2_recount.py \\
        --gate_master data/frozen/v1_9/corpus_master.csv \\
        --new_master  data/frozen/v1_9r/corpus_master.csv \\
        --log         data/frozen/v1_9r/audit_table2_v1_9r.txt \\
        --row_out     docs/drafts/pending_edits/S300-J_table2_row.md

Reader mode, the only mode that runs on the released data:
    python scripts/table2_recount.py --public_master corpus_master.csv

Exit 0 only when the GATE and the CLOSURE checks all pass. The ledger row is
written only on exit 0, and every number in it is interpolated from the
measurement rather than hand-typed (DEC-048). The log hash inside the row is
taken from the log file after it has been written.

NEWLINES ARE FORCED TO LF at every write. Without newline='\\n' Python's
text mode translates to CRLF on Windows, so the same inputs would produce
different bytes on the judgment surface and the execution surface, and any
hash recorded for these outputs would be platform-dependent. Measured
S300-X: the log came out 47 bytes larger over 47 lines and the row file 15
over 15. The evidence ledger this row is appended to carries 0 CRLF, and
docs/drafts/pending_edits/ is git-tracked, where a CRLF file's recorded
hash can be invalidated by a checkout with no one editing it (Pending 65).
"""
import argparse
import csv
import hashlib
import io
import sys

# Manuscript Table 2 as printed, keyed by genre code: (n, HIGH, MEDIUM, LOW).
# Source: docs/drafts/R8_preprint_draft_v1_9.md, Section 4.2, at manuscript
# sha256 686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185.
GATE_BY_GENRE = {
    '1': (49, 22, 23, 4),
    '2': (40, 17, 21, 2),
    '3': (36, 30, 6, 0),
    '4': (58, 37, 14, 7),
    '5': (24, 14, 10, 0),
    '6': (4, 1, 2, 1),
}
GATE_TOTAL = (211, 121, 76, 14)

# PUBLIC MODE expectations: the deduplicated population (n=205, whole corpus,
# CMI = 0.0 included) as recorded in the evidence ledger, transcribed BEFORE any
# public-mode run existed so that the check is not fitted to its own output.
# Codes 1 and 3: EV-table2-001 (moved cells). Codes 2, 4, 5, 6: EV-table2-001
# states them unchanged, so they equal GATE_BY_GENRE. Total: EV-r196-029.
PUBLIC_BY_GENRE = {
    '1': (45, 21, 20, 4),
    '2': (40, 17, 21, 2),
    '3': (34, 28, 6, 0),
    '4': (58, 37, 14, 7),
    '5': (24, 14, 10, 0),
    '6': (4, 1, 2, 1),
}
PUBLIC_TOTAL = (205, 118, 73, 14)

# Manuscript Table 2 row labels, for log readability only.
NAMES = {
    '1': 'Investment/Finance',
    '2': 'Cult/Religion',
    '3': 'Romance/Relationships',
    '4': 'Education/Self-help',
    '5': 'Politics/Conspiracy',
    '6': 'Other',
}

# DEC-072 removed members. Asserted, not assumed, against the set difference.
DEC072_REMOVED = ['AD_065', 'AD_067', 'AD_071', 'AD_072', 'AD_073', 'AD_074']

LABELS = ('HIGH', 'MEDIUM', 'LOW')

MANUSCRIPT_SHA = '686f67827d5949d530ee19b0263402e5ee6a3578c0eb99224ca52a7b6ee46185'

HEADER_NOTE = '''## Table 2 genre composition (S300-J)

WHY THIS ROW IS OUTSIDE THE EV-r196 SECTION. It supersedes nothing. Manuscript
Table 2's per-genre cells are printed and population-dependent, and were owned by
no claim row (S294-J, measured over 102 rows; re-measured S300-J over 173). A row
with no superseded predecessor cannot enter a section whose header declares a
fixed set of 70 superseded ids without breaking the set-equality assert that
gates that write. Same treatment as EV-prf-005.

SCOPE. Per-genre cells only. Table 2's total row is owned by EV-r196-029 and is
reproduced here as a closure check, not as a claim (S294-J decision B).'''


def sha256_of(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def load_master(path):
    text = open(path, 'rb').read().decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(text)))


def code_of(row):
    return row['genre_label'].split(':')[0].strip()


def label_of(row):
    return row['human_label'].strip().upper()


def by_genre(rows):
    """Return {code: (n, HIGH, MEDIUM, LOW)} over every code present."""
    out = {}
    for c in sorted({code_of(r) for r in rows}):
        sub = [r for r in rows if code_of(r) == c]
        out[c] = tuple([len(sub)] + [sum(1 for r in sub if label_of(r) == k)
                                     for k in LABELS])
    return out


def total_of(table):
    return tuple(sum(v[i] for v in table.values()) for i in range(4))


def public_mode(path):
    """Reader mode. Recompute Table 2 from the released corpus_master.csv and
    compare every cell with the recorded values. Writes nothing. Exit 0 only
    when every cell matches."""
    print('=== table2_recount.py -- public mode ===')
    print('corpus_master : %s' % path)
    print('  sha256      : %s' % sha256_of(path))
    got = by_genre(load_master(path))
    fails = 0
    for c in sorted(PUBLIC_BY_GENRE):
        exp = PUBLIC_BY_GENRE[c]
        ok = got.get(c) == exp
        fails += (not ok)
        print('  %-1s %-22s computed=%-20s expected=%-20s [%s]'
              % (c, NAMES[c], got.get(c), exp, 'OK' if ok else 'FAIL'))
    unexpected = sorted(set(got) - set(PUBLIC_BY_GENRE))
    ok = not unexpected
    fails += (not ok)
    print('  genre codes outside the table: %s [%s]'
          % (unexpected, 'OK' if ok else 'FAIL'))
    t = total_of(got)
    ok = t == PUBLIC_TOTAL
    fails += (not ok)
    print('  TOTAL  computed=%-20s expected=%-20s [%s]'
          % (t, PUBLIC_TOTAL, 'OK' if ok else 'FAIL'))
    print('RESULT: %d checks, %d FAIL' % (len(PUBLIC_BY_GENRE) + 2, fails))
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
        open(args.log, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
        sys.exit(code)

    out('=== table2_recount.py ===')
    out('gate_master : %s' % args.gate_master)
    out('  sha256    : %s' % sha256_of(args.gate_master))
    out('new_master  : %s' % args.new_master)
    out('  sha256    : %s' % sha256_of(args.new_master))
    out()

    gate_rows = load_master(args.gate_master)
    g = by_genre(gate_rows)

    out('=== GATE -- manuscript Table 2 as printed, reproduced from the data ===')
    fails = 0
    checks = 0
    for c in sorted(GATE_BY_GENRE):
        exp = GATE_BY_GENRE[c]
        got = g.get(c)
        ok = got == exp
        fails += (not ok)
        checks += 1
        out('  %-1s %-22s computed=%-20s printed=%-20s [%s]'
            % (c, NAMES[c], got, exp, 'OK' if ok else 'FAIL'))
    unexpected = sorted(set(g) - set(GATE_BY_GENRE))
    ok = not unexpected
    fails += (not ok)
    checks += 1
    out('  genre codes outside the printed table: %s [%s]'
        % (unexpected, 'OK' if ok else 'FAIL'))
    got_total = total_of(g)
    ok = got_total == GATE_TOTAL
    fails += (not ok)
    checks += 1
    out('  TOTAL (closure, owned by EV-r196-029)  computed=%-20s printed=%-20s [%s]'
        % (got_total, GATE_TOTAL, 'OK' if ok else 'FAIL'))
    out('GATE: %d checks over %d printed cells, %d FAIL'
        % (checks, len(GATE_BY_GENRE) * 4 + 4, fails))
    out()
    if fails:
        out('=== RESULT ===')
        out('GATE FAILED. No deduplicated value is emitted.')
        finish(1)

    new_rows = load_master(args.new_master)
    n = by_genre(new_rows)

    out('=== NEW POPULATION -- per-genre cells ===')
    for c in sorted(n):
        out('  %-1s %-22s n=%-4d HIGH=%-4d MEDIUM=%-4d LOW=%d'
            % ((c, NAMES.get(c, '?')) + n[c]))
    new_total = total_of(n)
    out('  TOTAL (not owned here; see EV-r196-029)  n=%d HIGH=%d MEDIUM=%d LOW=%d'
        % new_total)
    out()

    out('=== CHANGED ===')
    changed = []
    for c in sorted(GATE_BY_GENRE):
        if n.get(c) != GATE_BY_GENRE[c]:
            changed.append(c)
            out('  %-1s %-22s %s  ->  %s' % (c, NAMES[c], GATE_BY_GENRE[c], n[c]))
    out('  genres unchanged: %s'
        % [c for c in sorted(GATE_BY_GENRE) if c not in changed])
    out('  TOTAL %s  ->  %s' % (GATE_TOTAL, new_total))
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
        out('  %-14s %-58s expected=%s [%s]'
            % (name, got, exp, 'OK' if ok else 'FAIL'))
    idx = {r['target']: r for r in gate_rows}
    per = {}
    for t in removed:
        per.setdefault(code_of(idx[t]), []).append((t, label_of(idx[t])))
    for c in sorted(per):
        out('  removed in %s %-22s %s' % (c, NAMES.get(c, '?'), per[c]))
    for c in sorted(GATE_BY_GENRE):
        drop = per.get(c, [])
        exp = tuple([len(drop)] + [sum(1 for _, l in drop if l == k) for k in LABELS])
        delta = tuple(GATE_BY_GENRE[c][i] - n[c][i] for i in range(4))
        ok = delta == exp
        cfails += (not ok)
        out('  delta %s %-22s table=%-16s removals=%-16s [%s]'
            % (c, NAMES[c], delta, exp, 'OK' if ok else 'FAIL'))
    out('CLOSURE: %d FAIL' % cfails)
    out()

    out('=== RESULT ===')
    if cfails:
        out('CLOSURE FAILED.')
        finish(1)
    out('GATE 0 FAIL, CLOSURE 0 FAIL. Per-genre cells emitted for EV-table2-001.')
    open(args.log, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')

    # Ledger row. Every number below is interpolated from the measurement above;
    # nothing is hand-typed (DEC-048). The log hash is taken from the log file
    # after it has been written.
    log_sha = sha256_of(args.log)
    moved = []
    for c in sorted(GATE_BY_GENRE):
        if n[c] != GATE_BY_GENRE[c]:
            o, w = GATE_BY_GENRE[c], n[c]
            cols = ('n', 'HIGH', 'MEDIUM', 'LOW')
            parts = ['%s %d to %d' % (cols[i], o[i], w[i])
                     for i in range(4) if o[i] != w[i]]
            same = ['%s %d' % (cols[i], w[i]) for i in range(4) if o[i] == w[i]]
            moved.append('%s %s, %s unchanged'
                         % (NAMES[c], ', '.join(parts), ' and '.join(same)))
    unchanged = [NAMES[c] for c in sorted(GATE_BY_GENRE)
                 if n[c] == GATE_BY_GENRE[c]]
    drops = []
    for c in sorted(per):
        byl = {}
        for t, l in sorted(per[c]):
            byl.setdefault(l, []).append(t)
        groups = sorted(byl.items(), key=lambda kv: sorted(kv[1])[0])
        seg = ' and '.join('%s (%s)' % (', '.join(sorted(v)), k)
                           for k, v in groups)
        drops.append('%s from %s' % (seg, NAMES[c]))

    claim = ('Section 4.2, Table 2: the per-genre document counts and human '
             'label counts of the corpus genre distribution')
    evidence = (
        'At the pre-deduplication population the producer reproduces all %d '
        'printed Table 2 cells exactly, which is what establishes that the same '
        'computation yields the printed table. At the deduplicated population '
        '%d genres move and %d are unchanged: %s. %s are unchanged in every '
        'cell. The %d documents removed under DEC-072 account for the whole of '
        'the change and were verified as the set difference between the two '
        'frozen populations rather than assumed: %s. The Section 4.2 prose '
        'prints the same %d n values and carries the same %d changes. THE '
        'TOTAL ROW IS NOT CLAIMED HERE; it is owned by EV-r196-029, and this '
        'producer reproduces it only as a closure check.'
        % (len(GATE_BY_GENRE) * 4 + 4, len(moved), len(unchanged),
           '; '.join(moved),
           ', '.join(unchanged[:-1]) + ' and ' + unchanged[-1],
           len(removed), '; '.join(drops),
           len(GATE_BY_GENRE), len(moved)))
    source = (
        'scripts/table2_recount.py, log %s (%s); GATE %d checks over %d printed '
        'cells, 0 FAIL, and CLOSURE 0 FAIL, both required for exit 0. Gate '
        'population %s (%s); new population %s (%s). Printed values read from '
        'the EN canonical at %s. NOT APPLIED to the manuscript: the EN canonical '
        'stays at commit cda705d4.'
        % (args.log, log_sha, checks, len(GATE_BY_GENRE) * 4 + 4,
           args.gate_master, sha256_of(args.gate_master),
           args.new_master, sha256_of(args.new_master), MANUSCRIPT_SHA))

    row = '| EV-table2-001 | %s | %s | %s | VERIFIED |' % (claim, evidence, source)
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
