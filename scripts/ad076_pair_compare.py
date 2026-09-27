"""ad076_pair_compare.py -- is AD_076 a duplicate of any retained document?

READ ONLY, AND NO DOCUMENT TEXT REACHES DISK. AD_076's text is read from the git
object store through `git cat-file blob` into memory. It is never written to a
file, never printed, and never copied. Output is identifiers, counts and ratios
only ([COMMON] Third-Party Information Handling [4]).

WHY THE MEASURE IS IMPORTED AND NOT REIMPLEMENTED. The deciding measure recorded
for the six DEC-072 pairs -- character-weighted share of the shorter document --
has no identified producer, so reimplementing it here and quoting its 96.5 / 76.0
calibration would assert an agreement between two implementations that nobody has
tested. Instead this script imports flatten(), grams() and containment() from
scripts/dup_scan_chargram.py and normalise() from scripts/dup_scan_containment.py,
both of which carry recorded SHA256 values, and RE-MEASURES the nine calibration
pairs in the same run. Separation is then a result of this run rather than a
number carried in from a record.

REFUSAL. If the calibration does not separate -- if the lowest DUP pair does not
sit above the highest NOT_DUP pair -- the script prints the calibration and stops
without scoring AD_076. This mirrors the refusal already built into
dup_scan_chargram.py.

WHAT THIS CAN AND CANNOT SETTLE. It settles whether AD_076 duplicates a retained
document. It does not settle why AD_076 was removed; a negative result means the
removal was not a duplicate removal, not that the reason is recoverable.

CANONICAL PRODUCER for: EV-ad076-001. Promoted from handout/ at S382-J, the
measurement having been made there; the file content is unchanged apart from the
import path and this note, and the promoted copy reproduces the same result.

Usage, from /c/r8/r8_strategy:
    python scripts/ad076_pair_compare.py \
        --master    data/frozen/v1_9r/corpus_master.csv \
        --clean_dir corpus/corpus_clean \
        --blob      b775939c2933

Exit 0 on a completed comparison, 1 on any refusal or identity failure.
"""
import argparse
import csv
import io
import os
import subprocess
import sys

# The two measure modules sit beside this file once it is promoted to scripts/.
# Inserting this file's own directory keeps the import working regardless of the
# working directory the run is launched from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dup_scan_chargram import (flatten, grams, containment, NGRAM,  # noqa: E402
                               CAL_DUP, CAL_NOT)
from dup_scan_containment import normalise  # noqa: E402

TARGET = 'AD_076'
EXPECTED_BLOB_SIZE = 1613
EXPECTED_BLOB_PATH = 'corpus/corpus_clean/AD_076.txt'
TOP_N = 15


def git(args):
    p = subprocess.run(['git'] + args, capture_output=True)
    if p.returncode != 0:
        raise SystemExit('git %s failed: %s'
                         % (' '.join(args), p.stderr.decode('utf-8', 'replace')))
    return p.stdout


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument('--master', required=True)
    ap.add_argument('--clean_dir', required=True)
    ap.add_argument('--blob', required=True)
    args = ap.parse_args()

    print('=== ad076_pair_compare.py  (READ-ONLY, no text to disk) ===')
    print('master    :', args.master)
    print('clean_dir :', args.clean_dir)
    print('blob      :', args.blob)
    print('measure   : containment over distinct character %d-grams' % NGRAM)
    print()

    print('=== 1. BLOB IDENTITY ===')
    oid = git(['rev-parse', '%s^{blob}' % args.blob]).decode().strip()
    size = int(git(['cat-file', '-s', oid]).decode().strip())
    print('  full oid :', oid)
    print('  size     : %d  (expected %d)' % (size, EXPECTED_BLOB_SIZE))
    if size != EXPECTED_BLOB_SIZE:
        print('  [FAIL] this is not the blob S378-J measured at %s.'
              % EXPECTED_BLOB_PATH)
        return 1
    raw = git(['cat-file', 'blob', oid]).decode('utf-8-sig', errors='replace')
    t_flat = flatten(raw)
    t_grams = grams(t_flat)
    t_lines = set(normalise(raw))
    print('  flattened characters :', len(t_flat))
    print('  distinct %d-grams     : %d' % (NGRAM, len(t_grams)))
    print('  distinct normalised lines :', len(t_lines))
    if not t_grams:
        print('  [FAIL] shorter than %d characters; not comparable.' % NGRAM)
        return 1
    print()

    text = open(args.master, 'rb').read().decode('utf-8-sig')
    rows = list(csv.DictReader(io.StringIO(text)))
    targets = [r['target'] for r in rows]
    print('=== 2. POPULATION ===')
    print('  master rows        :', len(rows))
    print('  master targets uniq:', len(set(targets)))
    if len(set(targets)) != len(targets):
        print('  [FAIL] duplicate target identifiers in master')
        return 1

    on_disk = sorted(x for x in os.listdir(args.clean_dir) if x.endswith('.txt'))
    stem_exact = {x[:-4]: x for x in on_disk}
    stem_lower = {}
    for x in on_disk:
        stem_lower.setdefault(x[:-4].lower(), []).append(x)
    mapping, missing = {}, []
    for t in targets:
        if t in stem_exact:
            mapping[t] = stem_exact[t]
        else:
            cands = stem_lower.get(t.lower(), [])
            if len(cands) == 1:
                mapping[t] = cands[0]
            else:
                missing.append(t)
    print('  files in clean_dir :', len(on_disk))
    print('  mapped             :', len(mapping))
    print('  targets w/o file   :', len(missing), missing if missing else '')
    if missing:
        print('  [FAIL] every master target must map to a file; nothing compared')
        return 1
    if TARGET in mapping:
        print('  [FAIL] %s is inside the retained population; the premise of this'
              ' comparison is that it was removed.' % TARGET)
        return 1
    print()

    def load_path(fname):
        with open(os.path.join(args.clean_dir, fname),
                  encoding='utf-8-sig', errors='replace') as f:
            r = f.read()
        s = flatten(r)
        return grams(s), set(normalise(r))

    def load(t):
        return load_path(mapping[t])

    def load_disk(t):
        """Calibration members are resolved against the DIRECTORY, not against
        the master. Six of the twelve calibration documents were REMOVED by
        DEC-072 and so appear in no retained population, while their files may
        still sit in clean_dir. Resolving them through the master makes the
        calibration permanently incomplete and the script permanently refuse --
        measured in rehearsal before issue."""
        if t in stem_exact:
            return load_path(stem_exact[t])
        cands = stem_lower.get(t.lower(), [])
        if len(cands) == 1:
            return load_path(cands[0])
        return None

    print('=== 3. CALIBRATION, RE-MEASURED IN THIS RUN ===')
    held = {}
    for t in {x for p in CAL_DUP + CAL_NOT for x in p}:
        got = load_disk(t)
        if got is not None:
            held[t] = got
    dup_scores, not_scores = [], []
    for label, pairs, sink in (('DUP', CAL_DUP, dup_scores),
                               ('NOT', CAL_NOT, not_scores)):
        for a, b in pairs:
            if a not in held or b not in held:
                print('  %-4s %-8s %-8s ABSENT from %s'
                      % (label, a, b, args.clean_dir))
                continue
            c = containment(held[a][0], held[b][0])
            sink.append((c, a, b))
            print('  %-4s %-8s %-8s containment=%.4f' % (label, a, b, c))
    if len(dup_scores) < len(CAL_DUP) or len(not_scores) < len(CAL_NOT):
        print('  [REFUSE] calibration incomplete; %s is not scored.' % TARGET)
        return 1
    lo_dup = min(s[0] for s in dup_scores)
    hi_not = max(s[0] for s in not_scores)
    print('  lowest DUP  = %.4f' % lo_dup)
    print('  highest NOT = %.4f' % hi_not)
    print('  separation  = %+.4f' % (lo_dup - hi_not))
    if lo_dup <= hi_not:
        print('  [REFUSE] the calibration does not separate in this run.'
              ' AD_076 is not scored.')
        return 1
    print('  DECISION BAND for reading the scores below: a score at or above'
          ' %.4f sits in the DUP group, at or below %.4f in the NOT group,'
          ' and between them is undecided by this instrument.'
          % (lo_dup, hi_not))
    print()

    print('=== 4. %s AGAINST EVERY RETAINED DOCUMENT ===' % TARGET)
    scored = []
    for t in sorted(mapping):
        g, ln = held[t] if t in held else load(t)
        c = containment(t_grams, g)
        lc = (len(t_lines & ln) / min(len(t_lines), len(ln))
              if t_lines and ln else None)
        scored.append((c if c is not None else -1.0, lc, t, len(g)))
    scored.sort(reverse=True)
    print('  compared: %d' % len(scored))
    print('  %-4s %-10s %-12s %-12s %s' % ('#', 'target', 'chargram', 'line-cont',
                                           'grams'))
    for i, (c, lc, t, ng) in enumerate(scored[:TOP_N], 1):
        print('  %-4d %-10s %-12.4f %-12s %d'
              % (i, t, c, ('%.4f' % lc) if lc is not None else '-', ng))
    print()
    in_dup = [s for s in scored if s[0] >= lo_dup]
    in_band = [s for s in scored if hi_not < s[0] < lo_dup]
    print('  at or above the DUP floor (%.4f): %d %s'
          % (lo_dup, len(in_dup), [s[2] for s in in_dup]))
    print('  inside the undecided band       : %d %s'
          % (len(in_band), [s[2] for s in in_band]))
    print('  maximum score observed          : %.4f (%s)'
          % (scored[0][0], scored[0][2]))
    print()
    print('=== RESULT ===')
    print('Comparison complete. No document text was written to disk.')
    print('The verdict is not stated here; the judgment session rules it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
