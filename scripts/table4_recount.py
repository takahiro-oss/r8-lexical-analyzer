#!/usr/bin/env python3
"""
table4_recount.py -- Investigation script for the Table 4 (sec4.5) run-level
denominator discrepancy (S165-J spec_04 / S168-X).

PURPOSE:
    Recount Table 4 (Label Distribution: Human vs. LLM Annotators) directly
    from the frozen v1.9 dataset and report:
      - per-run row counts, unique target counts, duplicate targets (TASK B-1)
      - set differences between each run's target IDs and the corpus_master
        target ID set (TASK B-2)
      - presence/absence check for the 4 documents footnote 2 names as
        absent from all Gemini runs (TASK B-3)
      - whether an initial (v1) Gemini run file exists in frozen data (TASK B-4)
      - whether the set of targets that survive kappa_compute.py's inner-join
        filtering (valid_targets = corpus_master CMI>0 set) includes any
        target absent from corpus_master (TASK C-2/C-3)
      - HIGH/MEDIUM/LOW counts and percentages per run, under three
        denominators (TASK D-1/D-2)

This script performs read-only analysis. It does not modify any frozen
file, the manuscript, candidates.md, or decision_index.md.

USAGE:
    python scripts/table4_recount.py --frozen_dir data/frozen/v1_9

INPUT FILES (all read-only; must exist in frozen_dir):
    corpus_master.csv (corpus of record, 211 rows)
    results_claude.csv, results_claude_v2.csv .. results_claude_v5.csv
    results_gemini_v2.csv .. results_gemini_v6.csv

READER CHECK, on the released bundle directory:
    python scripts/table4_recount.py --frozen_dir <bundle dir> --public_check
    The report is printed as above; --public_check then asserts the recorded
    values and exits 1 on any mismatch.
    TASK D-3 compares with the Table 4 values as read when this script was
    written. The current manuscript prints Gemini MEDIUM 13-20 (6.1-9.4%), which
    equals the measured range (EV-r196-069c), so the MISMATCH printed for that
    line refers to an earlier manuscript state, not to the current one.

NOTE: This file is git-tracked (no copyright risk, contains no corpus text).
      The frozen_dir contents are .gitignore-excluded.
"""

import argparse
import hashlib
import os
import sys
from collections import Counter

import pandas as pd

CLAUDE_RUNS = [
    ('run1', 'results_claude.csv'),
    ('run2', 'results_claude_v2.csv'),
    ('run3', 'results_claude_v3.csv'),
    ('run4', 'results_claude_v4.csv'),
    ('run5', 'results_claude_v5.csv'),
]

GEMINI_RUNS = [
    ('run2', 'results_gemini_v2.csv'),
    ('run3', 'results_gemini_v3.csv'),
    ('run4', 'results_gemini_v4.csv'),
    ('run5', 'results_gemini_v5.csv'),
    ('run6', 'results_gemini_v6.csv'),
]

GEMINI_ABSENT_PER_FOOTNOTE2 = ['WEB_043', 'Web_089', 'note112', 'note_096']

# The twelve run-file identifiers that lie outside the 205-document (v1_9r)
# corpus_master. Measured identical across all ten run files. Held as a literal
# so that the Option B population can be recomputed by a route that does not
# consult corpus_master at all (S299-J spec_01 STEP 3, two-route check).
TWELVE_OUTSIDE_CORPUS_205 = [
    'AD_053', 'AD_054', 'AD_065', 'AD_067', 'AD_071', 'AD_072',
    'AD_073', 'AD_074', 'AD_076', 'note122', 'note171', 'web198',
]

LABELS = ['HIGH', 'MEDIUM', 'LOW']

# PUBLIC CHECK expectations at the deduplicated population, transcribed from
# EV-r196-069 and EV-r196-070 BEFORE any public-check run existed, so that the
# check is not fitted to its own output. Label ranges are over the full run files
# (measured run denominators 217 and 213).
PUBLIC_EXPECT = {
    'Claude': {'rows': 217, 'missing_from_run': [], 'option_b': 205,
               'after_valid_filter': 196,
               'ranges': {'HIGH': (87, 89), 'MEDIUM': (64, 66), 'LOW': (64, 66)}},
    'Gemini': {'rows': 213, 'missing_from_run': sorted(GEMINI_ABSENT_PER_FOOTNOTE2),
               'option_b': 201, 'after_valid_filter': 192,
               'ranges': {'HIGH': (184, 191), 'MEDIUM': (13, 20), 'LOW': (8, 9)}},
}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def row_count_and_sha(path):
    sha = sha256_file(path)
    df = pd.read_csv(path, encoding='utf-8-sig')
    return len(df), sha, df


def duplicates(series):
    c = Counter(series)
    return sorted([t for t, n in c.items() if n > 1])


def main():
    parser = argparse.ArgumentParser(description='Table 4 recount investigation')
    parser.add_argument('--frozen_dir', default='data/frozen/v1_9')
    parser.add_argument('--log', default=None)
    parser.add_argument('--public_check', action='store_true',
                        help='after the report, assert the recorded values; '
                             'exit 1 on any mismatch')
    args = parser.parse_args()

    frozen_dir = args.frozen_dir
    lines = []

    def out(s=''):
        print(s)
        lines.append(s)

    out('=' * 78)
    out('TASK A: FILE INVENTORY (rows / SHA256)')
    out('=' * 78)

    all_files = [f for _, f in CLAUDE_RUNS] + [f for _, f in GEMINI_RUNS]
    file_data = {}
    for fname in all_files:
        path = os.path.join(frozen_dir, fname)
        if not os.path.exists(path):
            out(f'  MISSING: {fname}')
            continue
        n, sha, df = row_count_and_sha(path)
        file_data[fname] = df
        out(f'  {fname:28s} rows={n:4d}  SHA256={sha}')

    cm_path = os.path.join(frozen_dir, 'corpus_master.csv')
    cm_n, cm_sha, cm = row_count_and_sha(cm_path)
    out(f'  {"corpus_master.csv":28s} rows={cm_n:4d}  SHA256={cm_sha}')

    valid_cm = cm[cm['cmi'] > 0]
    corpus_all_targets = set(cm['target'])
    corpus_valid_targets = set(valid_cm['target'])
    out()
    out(f'  corpus_master.csv total targets (n_total): {len(corpus_all_targets)}')
    out(f'  corpus_master.csv valid targets (CMI>0, n_valid): {len(corpus_valid_targets)}')

    out()
    out('=' * 78)
    out('TASK B-1: PER-RUN ROW COUNT / UNIQUE TARGET COUNT / DUPLICATES')
    out('=' * 78)

    run_target_sets = {}
    for model_label, runs in [('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS)]:
        for run_label, fname in runs:
            df = file_data[fname]
            total_rows = len(df)
            unique_targets = df['target'].nunique()
            dups = duplicates(df['target'])
            run_target_sets[(model_label, run_label)] = set(df['target'])
            out(f'  {model_label:7s} {run_label:5s} ({fname:24s}) total_rows={total_rows:4d}  '
                f'unique_targets={unique_targets:4d}  duplicates={dups if dups else "NONE"}')

    out()
    out('=' * 78)
    out('TASK B-2: SET DIFFERENCE vs corpus_master (205 total targets)')
    out('=' * 78)

    for model_label, runs in [('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS)]:
        out(f'-- {model_label} --')
        union_extra = set()
        union_missing = set()
        per_run_sets = []
        for run_label, fname in runs:
            s = run_target_sets[(model_label, run_label)]
            per_run_sets.append((run_label, s))
            extra = sorted(s - corpus_all_targets)
            missing = sorted(corpus_all_targets - s)
            union_extra |= set(extra)
            union_missing |= set(missing)
            out(f'  {run_label}: (a) in_run_not_in_corpus n={len(extra)} ids={extra}')
            out(f'  {run_label}: (b) in_corpus_not_in_run n={len(missing)} ids={missing}')
        # (c) do the 5 run-level ID sets match each other exactly?
        base_label, base_set = per_run_sets[0]
        all_match = all(s == base_set for _, s in per_run_sets)
        out(f'  (c) 5-run ID-set identical across all runs: {all_match}')
        if not all_match:
            for run_label, s in per_run_sets:
                diff_from_base = sorted(s.symmetric_difference(base_set))
                if diff_from_base:
                    out(f'      {run_label} differs from {base_label} by: {diff_from_base}')
        out(f'  UNION across 5 runs -- in_run_not_in_corpus: n={len(union_extra)} ids={sorted(union_extra)}')
        out(f'  UNION across 5 runs -- in_corpus_not_in_run: n={len(union_missing)} ids={sorted(union_missing)}')
        out()

    out('=' * 78)
    out('TASK B-2b: OPTION B POPULATION -- TWO INDEPENDENT ROUTES')
    out('=' * 78)
    out('  route A: |run target set INTERSECT corpus_master|')
    out(f'  route B: |run target set MINUS the twelve identifiers outside the '
        f'{len(corpus_all_targets)}-document corpus|')
    out()

    option_b = {}
    twelve = set(TWELVE_OUTSIDE_CORPUS_205)
    for model_label, runs in [('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS)]:
        out(f'-- {model_label} --')
        route_a_sizes = []
        route_b_sizes = []
        for run_label, fname in runs:
            s = run_target_sets[(model_label, run_label)]
            a = len(s & corpus_all_targets)
            b = len(s - twelve)
            route_a_sizes.append(a)
            route_b_sizes.append(b)
            out(f'  {run_label}: unique_targets={len(s):4d}  route_A={a:4d}  route_B={b:4d}  '
                f'{"AGREE" if a == b else "DISAGREE"}')
        a_const = len(set(route_a_sizes)) == 1
        b_const = len(set(route_b_sizes)) == 1
        routes_agree = route_a_sizes == route_b_sizes
        out(f'  route A constant across the 5 run files: {a_const} ({sorted(set(route_a_sizes))})')
        out(f'  route B constant across the 5 run files: {b_const} ({sorted(set(route_b_sizes))})')
        out(f'  BOTH ROUTES AGREE ON EVERY RUN FILE: {routes_agree}')
        if not (a_const and b_const and routes_agree):
            out('  HALT CONDITION: Option B population is not a single set size '
                '(S299-J spec_01 STEP 3, DEC-072).')
            print('\nHALT: Option B population not constant / routes disagree.', file=sys.stderr)
            sys.exit(1)
        option_b[model_label] = route_a_sizes[0]
        out(f'  Option B population ({model_label}): {option_b[model_label]}')
        out()

    out(f'  Option B populations: Claude {option_b["Claude"]}, Gemini {option_b["Gemini"]}')
    out()

    out('=' * 78)
    out('TASK B-3: FOOTNOTE 2 4-DOCUMENT ABSENCE CHECK (Gemini)')
    out('=' * 78)
    for target in GEMINI_ABSENT_PER_FOOTNOTE2:
        presence = []
        for run_label, fname in GEMINI_RUNS:
            present = target in run_target_sets[('Gemini', run_label)]
            presence.append(f'{run_label}={"present" if present else "absent"}')
        out(f'  {target}: {", ".join(presence)}')

    out()
    out('=' * 78)
    out('TASK B-4: INITIAL (v1 / pre-run2) GEMINI RUN FILE PRESENCE IN FROZEN DATA')
    out('=' * 78)
    all_frozen_files = sorted(os.listdir(frozen_dir))
    gemini_files_found = [f for f in all_frozen_files if 'gemini' in f.lower()]
    out(f'  All gemini-named files in {frozen_dir}: {gemini_files_found}')
    v1_candidates = [f for f in gemini_files_found if f not in [fn for _, fn in GEMINI_RUNS]]
    out(f'  Files not in the 5 canonical Gemini run list (candidate initial-run files): '
        f'{v1_candidates if v1_candidates else "NONE FOUND"}')

    out()
    out('=' * 78)
    out('TASK C: KAPPA POPULATION CONTAMINATION CHECK')
    out('=' * 78)
    out('  kappa_compute.py load_run() filters each run dataframe to')
    out('  df["target"].isin(valid_targets), where valid_targets = corpus_master[cmi>0].target')
    out('  (see scripts/kappa_compute.py load_corpus()/load_run(), read this session).')
    out()

    for model_label, runs in [('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS)]:
        out(f'-- {model_label} --')
        for run_label, fname in runs:
            df = file_data[fname]
            filtered = df[df['target'].isin(corpus_valid_targets)]
            n_in = len(filtered)
            # contamination check: does the filtered (post-join) set contain
            # any target NOT in corpus_master's full 211 (i.e. would have
            # been "extra" per TASK B-2)?
            contamination = sorted(set(filtered['target']) - corpus_all_targets)
            out(f'  {run_label}: n_after_valid_target_filter={n_in}  '
                f'contamination(target outside corpus_master)={contamination if contamination else "NONE"}')
        out()

    out('=' * 78)
    out('TASK D-1/D-2: LABEL COUNTS AND PERCENTAGES (3 denominators)')
    out('=' * 78)

    def label_counts(df):
        c = df['ai_label'].value_counts()
        return {lbl: int(c.get(lbl, 0)) for lbl in LABELS}, len(df)

    n_corpus = len(corpus_all_targets)
    denom_defs = {
        'Claude': {'(i) measured_run_n': 217, '(ii) manuscript_stated_n': 211,
                   f'(iii) corpus_{n_corpus}': n_corpus,
                   '(iv) option_b_n': option_b['Claude']},
        'Gemini': {'(i) measured_run_n': 213, '(ii) manuscript_stated_n': 212,
                   f'(iii) corpus_{n_corpus}': n_corpus,
                   '(iv) option_b_n': option_b['Gemini']},
    }

    summary = {}  # model -> label -> list of (count, run_label)
    for model_label, runs in [('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS)]:
        out(f'-- {model_label} --')
        summary[model_label] = {lbl: [] for lbl in LABELS}
        for run_label, fname in runs:
            df = file_data[fname]
            counts, n = label_counts(df)
            unclassified = n - sum(counts.values())
            out(f'  {run_label}: n={n}  HIGH={counts["HIGH"]}  MEDIUM={counts["MEDIUM"]}  '
                f'LOW={counts["LOW"]}  sum={sum(counts.values())}  unclassified={unclassified}')
            for lbl in LABELS:
                summary[model_label][lbl].append(counts[lbl])
        out()

    out('=' * 78)
    out('TASK D-2: RANGES AND PERCENTAGES UNDER 3 DENOMINATORS')
    out('=' * 78)
    for model_label in ['Claude', 'Gemini']:
        out(f'-- {model_label} --')
        for lbl in LABELS:
            vals = summary[model_label][lbl]
            lo, hi = min(vals), max(vals)
            out(f'  {lbl}: count range = {lo}-{hi}')
            for denom_name, denom in denom_defs[model_label].items():
                pct_lo = 100 * lo / denom
                pct_hi = 100 * hi / denom
                out(f'    pct range under {denom_name} (denom={denom}): {pct_lo:.1f}-{pct_hi:.1f}%')
        out()

    out('=' * 78)
    out('TASK D-3: MANUSCRIPT-PRINTED VALUES FOR COMPARISON (hardcoded from')
    out('  R8_preprint_draft_v1_9.md Table 4, read this session -- NOT recomputed)')
    out('=' * 78)
    printed = {
        'Claude': {
            'HIGH':   {'count': '87-89', 'pct': '40.1-41.0%'},
            'MEDIUM': {'count': '64-66', 'pct': '29.5-30.4%'},
            'LOW':    {'count': '64-66', 'pct': '29.5-30.4%'},
        },
        'Gemini': {
            'HIGH':   {'count': '184-191', 'pct': '86.4-89.7%'},
            'MEDIUM': {'count': '13-16', 'pct': '6.1-7.5%'},
            'LOW':    {'count': '8-9', 'pct': '3.8-4.2%'},
        },
    }
    for model_label in ['Claude', 'Gemini']:
        denom_i = denom_defs[model_label]['(i) measured_run_n']
        for lbl in LABELS:
            vals = summary[model_label][lbl]
            lo, hi = min(vals), max(vals)
            pct_lo = 100 * lo / denom_i
            pct_hi = 100 * hi / denom_i
            measured_count_str = f'{lo}-{hi}'
            measured_pct_str = f'{pct_lo:.1f}-{pct_hi:.1f}%'
            p = printed[model_label][lbl]
            count_match = (measured_count_str == p['count'])
            # percent match compared with 0.1pp tolerance on string compare via recompute
            pct_match_note = 'see printed vs measured strings'
            out(f'  {model_label} {lbl:7s}  measured_count={measured_count_str:10s} printed_count={p["count"]:10s} '
                f'{"MATCH" if count_match else "MISMATCH"}')
            out(f'  {model_label} {lbl:7s}  measured_pct(i)={measured_pct_str:12s} printed_pct={p["pct"]:12s}')
        out()

    if args.log:
        with open(args.log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f'\n[Log saved: {args.log}]')

    if args.public_check:
        sys.exit(public_check(file_data, run_target_sets, corpus_all_targets,
                              corpus_valid_targets, option_b, summary))


def public_check(file_data, run_target_sets, corpus_all, corpus_valid,
                 option_b, summary):
    """Reader check. Compare the quantities computed above with the recorded
    values. Prints one line per check. Returns 0 only when every check passes."""
    fails = checks = 0

    def check(name, got, exp):
        nonlocal fails, checks
        ok = got == exp
        fails += (not ok)
        checks += 1
        print(f'  [{"OK" if ok else "FAIL"}] {name}: got={got} expected={exp}')

    print()
    print('=' * 78)
    print('PUBLIC CHECK against EV-r196-069 / EV-r196-070')
    print('=' * 78)
    twelve = sorted(TWELVE_OUTSIDE_CORPUS_205)
    for model, runs in [('Claude', CLAUDE_RUNS), ('Gemini', GEMINI_RUNS)]:
        e = PUBLIC_EXPECT[model]
        for run_label, fname in runs:
            df = file_data[fname]
            s = run_target_sets[(model, run_label)]
            check(f'{model} {run_label} rows', len(df), e['rows'])
            check(f'{model} {run_label} unique targets', len(s), e['rows'])
            check(f'{model} {run_label} outside corpus', sorted(s - corpus_all), twelve)
            check(f'{model} {run_label} corpus targets not in run',
                  sorted(corpus_all - s), e['missing_from_run'])
            check(f'{model} {run_label} after valid-target filter',
                  int(df['target'].isin(corpus_valid).sum()), e['after_valid_filter'])
        check(f'{model} option B population', option_b[model], e['option_b'])
        for lbl in LABELS:
            vals = summary[model][lbl]
            check(f'{model} {lbl} count range', (min(vals), max(vals)), e['ranges'][lbl])
    print(f'RESULT: {checks} checks, {fails} FAIL')
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    main()
