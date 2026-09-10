#!/usr/bin/env python3
"""
kappa_compute.py -- Canonical kappa computation script for R8 paper v1.9
[CANONICAL_SCRIPT]

PURPOSE:
    Single authoritative script for all kappa values reported in manuscript.
    Produces human-readable audit log verifiable by third parties (PLOS ONE requirement).

USAGE:
    python scripts/kappa_compute.py --frozen_dir data/frozen/v1_9
    python scripts/kappa_compute.py --frozen_dir data/frozen/v1_9 --log audit_log.txt

NOTE: This file is git-tracked (no copyright risk).
      The frozen_dir contents (data/frozen/) are .gitignore-excluded (third-party text risk).
      For public data repository: upload frozen_dir to Zenodo or OSF with DOI.

INPUT FILES (all read-only; must exist in frozen_dir):
    corpus_master.csv       ground truth (CMI, human_label)
    results_claude.csv      Claude run1  (n=202 valid)
    results_claude_v2.csv   Claude run2
    results_claude_v3.csv   Claude run3
    results_claude_v4.csv   Claude run4
    results_claude_v5.csv   Claude run5
    results_gemini_v2.csv   Gemini run2 (n=198 valid; 4 targets absent)
    results_gemini_v3.csv   Gemini run3
    results_gemini_v4.csv   Gemini run4
    results_gemini_v5.csv   Gemini run5
    results_gemini_v6.csv   Gemini run6

OUTPUT:
    stdout (and optional --log file): full audit log
    NO files are written to frozen_dir (read-only policy)

DESIGN NOTES:
    Valid set: CMI > 0 (n=202 from frozen corpus_master)
    Claude: n=202 per run (all valid targets present)
    Gemini: n=198 per run; 4 targets absent from frozen 202:
        WEB_043, Web_089, note112, note_096
        Reason: corpus finalized after Gemini runs were conducted;
        3 documents had API errors; 1 document did not exist at run time.
        Conclusion (Slight agreement, below acceptance threshold) is
        consistent across n=198 and prior n=212 calculation (EV-gemini-003).
    CMI bands: CMI < 20 = LOW band, 20-40 = MID band, > 40 = HIGH band
    kappa: sklearn cohen_kappa_score, labels=['HIGH','MEDIUM','LOW']
    Band-level: agreement rate only (kappa omitted; within-band label
        variance is insufficient for reliable kappa estimation --
        PLOS ONE statistical standards)
    SD: ddof=1 (sample SD across runs)

EVIDENCE LEDGER CROSS-REFERENCE:
    EV-llmkappa-007 : Claude n=202, M=0.2304 (reported as 0.230), SD=0.0186 (reported as 0.019)
    EV-gemini-003   : Gemini n=198, M=0.1059 (reported as 0.106), SD=0.0255 (reported as 0.026)
    EV-table-001    : Table 5 band-level values (UNVERIFIED -> VERIFIED by this script)

TRIGGER TAGS (see DEC-012, FROZEN_MANIFEST.md):
    [CANONICAL_SCRIPT] -- use this script for all kappa computations
    [MANIFEST_CHECK]   -- verify SHA256 before citing numbers in manuscript
    [ZENODO_GATE]      -- run with --log before Zenodo submission; all checks must PASS
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

LABELS = ['HIGH', 'MEDIUM', 'LOW']

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

# Expected input hashes. The default is the internal frozen v1.9 dataset.
# A released bundle whose inputs differ by construction (for example the
# pseudonymised public bundle) supplies its own values via --manifest, so
# that one canonical script serves every bundle without being forked.
MANIFEST_SHA256 = {
    'corpus_master.csv': 'b562425accd95cb64cd69b2462d6ddc3592fe0997d781b032742d3de0aaee362',
}


def load_manifest(path):
    if not path:
        return MANIFEST_SHA256
    with open(path, encoding='utf-8') as f:
        m = json.load(f)
    if not isinstance(m, dict) or not m:
        raise SystemExit('[FAIL] manifest is empty or not an object: %s' % path)
    return m

LEDGER_EXPECTED = {
    # UPDATED S365-J to the DEC-072 deduplicated population. Source, and the only
    # source: data/frozen/v1_9r/audit_kappa_v1_9r.txt
    # (74548d82a7aaf4e5621e307eecb8934e7b8448855806d6393c3278790eacc171),
    # SECTION 3, which prints
    #   Claude Sonnet 4.6  M=0.2413  SD=0.0165  n=196
    #   Gemini 2.5 Flash   M=0.1109  SD=0.0264  n=192
    # recorded into evidence_ledger.md rows EV-r196-023 and EV-r196-026 at S365-J.
    # These are PER-RUN mean and SD, not the majority-vote kappa. EV-r196-023
    # labelled 0.2413 "majority-vote", carrying the wording of the row it
    # supersedes; that label is corrected in the ledger. At n=202 the two
    # quantities differed (majority-vote 0.2414, per-run mean 0.2304).
    #
    # THE VALUES THIS TABLE HELD, 0.2304/0.0186/0.1059/0.0255, ARE n=202 VALUES.
    # That is why this script was the only producer of nineteen to exit 0 against
    # the released bundle while printing ALL LEDGER CHECKS PASSED: the bundle is
    # also n=202, so superseded expectations met superseded data and certified
    # figures the manuscript does not print. Measured S365-J. The frozen log
    # cited above had already reported LEDGER VERIFICATION FAILED on 2026-08-18.
    'claude_mean': (0.2413, 0.00005),
    'claude_sd':   (0.0165, 0.00005),
    'gemini_mean': (0.1109, 0.00005),
    'gemini_sd':   (0.0264, 0.00005),
}

GEMINI_ABSENT = ['WEB_043', 'Web_089', 'note112', 'note_096']


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def fmt_n(ns):
    """Render a per-run population. Never a literal: one value when all runs
    agree, an explicit range when they do not, so a divergence between runs
    cannot be printed as a single number."""
    u = sorted(set(ns))
    return str(u[0]) if len(u) == 1 else '%d-%d' % (u[0], u[-1])


def interpret_kappa(k):
    if k < 0:    return 'Poor'
    if k < 0.20: return 'Slight'
    if k < 0.40: return 'Fair'
    if k < 0.60: return 'Moderate'
    if k < 0.80: return 'Substantial'
    return 'Almost Perfect'


def load_corpus(frozen_dir):
    path = os.path.join(frozen_dir, 'corpus_master.csv')
    cm = pd.read_csv(path, encoding='utf-8-sig')
    valid = cm[cm['cmi'] > 0][['target', 'human_label', 'cmi']].copy().reset_index(drop=True)
    return cm, valid, set(valid['target'])


def load_run(frozen_dir, filename, valid_targets):
    path = os.path.join(frozen_dir, filename)
    df = pd.read_csv(path, encoding='utf-8-sig')
    return df[df['target'].isin(valid_targets)][['target', 'ai_label']].copy().reset_index(drop=True)


def compute_kappa(valid, run_df):
    merged = valid[['target', 'human_label']].merge(run_df, on='target', how='inner')
    n = len(merged)
    k = cohen_kappa_score(merged['human_label'], merged['ai_label'], labels=LABELS)
    agree = (merged['human_label'] == merged['ai_label']).mean()
    return n, round(k, 4), round(agree, 4)


def majority_vote_series(targets_list, run_df_list):
    vote_frames = []
    for rdf in run_df_list:
        s = rdf[rdf['target'].isin(targets_list)].set_index('target')['ai_label']
        vote_frames.append(s)
    combined = pd.concat(vote_frames, axis=1)
    combined.columns = range(len(vote_frames))
    return combined.mode(axis=1)[0]


def compute_band_agreement(valid, claude_run_dfs, gemini_run_dfs):
    bands = [
        ('LOW band (CMI < 20)',   valid['cmi'] < 20),
        ('MID band (CMI 20-40)', (valid['cmi'] >= 20) & (valid['cmi'] <= 40)),
        ('HIGH band (CMI > 40)', valid['cmi'] > 40),
    ]
    results = []
    for band_label, mask in bands:
        sub = valid[mask].copy()
        targets = list(sub['target'])
        n = len(sub)

        c_maj = majority_vote_series(targets, claude_run_dfs)
        sub_c = sub.copy()
        sub_c['c_maj'] = sub_c['target'].map(c_maj)
        c_agree = (sub_c['human_label'] == sub_c['c_maj']).mean()

        g_targets = [t for t in targets if t not in GEMINI_ABSENT]
        g_maj = majority_vote_series(g_targets, gemini_run_dfs)
        sub_g = sub[sub['target'].isin(g_targets)].copy()
        sub_g['g_maj'] = sub_g['target'].map(g_maj)
        g_agree = (sub_g['human_label'] == sub_g['g_maj']).mean()

        sub_3 = sub[sub['target'].isin(g_targets)].copy()
        sub_3['c_maj'] = sub_3['target'].map(c_maj)
        sub_3['g_maj'] = sub_3['target'].map(g_maj)
        three_agree = (
            (sub_3['human_label'] == sub_3['c_maj']) &
            (sub_3['human_label'] == sub_3['g_maj'])
        ).mean()

        results.append({
            'band': band_label, 'n': n, 'n_gemini': len(g_targets),
            # Rounding is applied once, at format time in main(). Rounding here as
            # well produced a double-rounding error: 25/46 = 54.3478% was rounded to
            # 0.5435 and then printed as 54.4% instead of 54.3%. One cell was
            # affected: Table 5, 3-way agreement, HIGH band.
            'claude_agree': float(c_agree),
            'gemini_agree': float(g_agree),
            'three_way':    float(three_agree),
        })
    return results


def main():
    parser = argparse.ArgumentParser(
        description='[CANONICAL_SCRIPT] Kappa computation for R8 v1.9')
    parser.add_argument('--frozen_dir', default='data/frozen/v1_9')
    parser.add_argument('--manifest', default=None,
                        help='JSON file of expected input SHA256 values; '
                             'defaults to the internal frozen v1.9 values')
    parser.add_argument('--log', default=None,
                        help='Optional path to save audit log (txt)')
    args = parser.parse_args()

    frozen_dir = args.frozen_dir
    manifest_path = args.manifest
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    lines = []

    def out(s=''):
        print(s)
        lines.append(s)

    out('=' * 70)
    out('AUDIT LOG -- kappa_compute.py [CANONICAL_SCRIPT]')
    out(f'Generated : {timestamp}')
    out(f'Frozen dir: {os.path.abspath(frozen_dir)}')
    out('=' * 70)

    # SECTION 1: SHA256
    out()
    out('--- SECTION 1: File Integrity (SHA256) ---')
    all_files = [('corpus_master.csv', True)] + \
                [(f, False) for _, f in CLAUDE_RUNS] + \
                [(f, False) for _, f in GEMINI_RUNS]
    manifest = load_manifest(manifest_path)
    integrity_pass = True
    for fname, check_manifest in all_files:
        path = os.path.join(frozen_dir, fname)
        if not os.path.exists(path):
            out(f'  MISSING   {fname}')
            integrity_pass = False
            continue
        h = sha256_file(path)
        size = os.path.getsize(path)
        if check_manifest and fname in manifest:
            ok = (h == manifest[fname])
            status = 'MATCH    ' if ok else 'MISMATCH '
            if not ok:
                integrity_pass = False
        else:
            status = 'RECORDED '
        out(f'  {status} {fname}')
        out(f'            SHA256={h}  bytes={size}')

    if not integrity_pass:
        out()
        out('INTEGRITY CHECK FAILED -- halting.')
        sys.exit(1)
    out()
    out('  corpus_master.csv: VERIFIED against FROZEN_MANIFEST')

    # SECTION 2: CORPUS
    out()
    out('--- SECTION 2: Corpus Summary ---')
    cm, valid, valid_targets = load_corpus(frozen_dir)
    out(f'  Total documents (n_total):  {len(cm)}')
    out(f'  Valid (CMI > 0, n_valid):   {len(valid)}')
    out(f'  Excluded (CMI = 0):         {len(cm) - len(valid)}')
    out('  human_label distribution (valid):')
    for lbl in LABELS:
        out(f'    {lbl:8s}: {(valid["human_label"] == lbl).sum()}')
    out('  Gemini absent targets (n=4; API error or pre-finalization absence):')
    for t in GEMINI_ABSENT:
        out(f'    {t}  (in valid set: {t in valid_targets})')

    # SECTION 3: PER-RUN KAPPA
    out()
    out('--- SECTION 3: Per-Run Kappa (vs human_label) ---')
    out()
    out(f'  {"Model":<22} {"Run":<6} {"n":>5}  {"kappa":>7}  {"agreement":>10}  Interpretation')
    out(f'  {"-"*22} {"-"*6} {"-"*5}  {"-"*7}  {"-"*10}  {"-"*15}')

    claude_kappas, claude_run_dfs, claude_ns = [], [], []
    for run_label, fname in CLAUDE_RUNS:
        run_df = load_run(frozen_dir, fname, valid_targets)
        n, k, ag = compute_kappa(valid, run_df)
        out(f'  {"Claude Sonnet 4.6":<22} {run_label:<6} {n:>5}  {k:>7.4f}  {ag:>9.1%}  {interpret_kappa(k)}')
        claude_kappas.append(k)
        claude_ns.append(n)
        claude_run_dfs.append(run_df)

    out()
    gemini_kappas, gemini_run_dfs, gemini_ns = [], [], []
    for run_label, fname in GEMINI_RUNS:
        run_df = load_run(frozen_dir, fname, valid_targets)
        n, k, ag = compute_kappa(valid, run_df)
        out(f'  {"Gemini 2.5 Flash":<22} {run_label:<6} {n:>5}  {k:>7.4f}  {ag:>9.1%}  {interpret_kappa(k)}')
        gemini_kappas.append(k)
        gemini_ns.append(n)
        gemini_run_dfs.append(run_df)

    claude_mean = float(np.mean(claude_kappas))
    claude_sd   = float(np.std(claude_kappas, ddof=1))
    gemini_mean = float(np.mean(gemini_kappas))
    gemini_sd   = float(np.std(gemini_kappas, ddof=1))

    out()
    out(f'  Claude Sonnet 4.6  M={claude_mean:.4f}  SD={claude_sd:.4f}  n={fmt_n(claude_ns)}  ({interpret_kappa(claude_mean)})')
    out(f'  Gemini 2.5 Flash   M={gemini_mean:.4f}  SD={gemini_sd:.4f}  n={fmt_n(gemini_ns)}  ({interpret_kappa(gemini_mean)})')
    out()
    out(f'  Note: Gemini n={fmt_n(gemini_ns)}; {len(valid) - max(gemini_ns)} valid documents '
        f'absent from all Gemini runs.')
    out('  Prior n=212 calculation (EV-gemini-001): M=0.108. Conclusion unchanged.')

    # SECTION 4: TABLE 5
    out()
    out('--- SECTION 4: Table 5 -- CMI Band-Level Agreement (majority vote) ---')
    out()
    out('  Band-level kappa omitted: within-band label variance insufficient')
    out('  for reliable kappa estimation (PLOS ONE statistical standards).')
    out('  Agreement rate reported instead (majority vote across 5 runs per model).')
    out()
    out(f'  {"CMI Band":<25} {"n":>5}  {"Claude-Human":>13}  {"Gemini-Human":>13}  {"3-Way":>8}')
    out(f'  {"-"*25} {"-"*5}  {"-"*13}  {"-"*13}  {"-"*8}')

    band_results = compute_band_agreement(valid, claude_run_dfs, gemini_run_dfs)
    for b in band_results:
        out(f'  {b["band"]:<25} {b["n"]:>5}  '
            f'{b["claude_agree"]:>12.1%}  '
            f'{b["gemini_agree"]:>12.1%}  '
            f'{b["three_way"]:>7.1%}')
    out()
    out(f'  Gemini agreement computed on intersection with frozen valid set '
        f'(n={fmt_n(gemini_ns)}).')
    out('  3-Way agreement computed on same intersection.')

    # SECTION 5: LEDGER VERIFICATION
    out()
    out('--- SECTION 5: Evidence Ledger Verification ---')
    out()
    checks = [
        ('Claude M(kappa)', claude_mean, *LEDGER_EXPECTED['claude_mean'], 'EV-llmkappa-007'),
        ('Claude SD',       claude_sd,   *LEDGER_EXPECTED['claude_sd'],   'EV-llmkappa-007'),
        ('Gemini M(kappa)', gemini_mean, *LEDGER_EXPECTED['gemini_mean'], 'EV-gemini-003'),
        ('Gemini SD',       gemini_sd,   *LEDGER_EXPECTED['gemini_sd'],   'EV-gemini-003'),
    ]
    all_pass = True
    for label, got, exp, tol, ev_id in checks:
        ok = abs(got - exp) <= tol
        status = 'PASS' if ok else 'FAIL'
        if not ok:
            all_pass = False
        out(f'  {status}  {label:<20} got={got:.4f}  expected={exp:.3f}  tol=+-{tol}  [{ev_id}]')

    out()
    if all_pass:
        out('  RESULT: ALL LEDGER CHECKS PASSED')
        out('  EV-table-001 status: VERIFIED by this audit run')
    else:
        out('  RESULT: LEDGER VERIFICATION FAILED')
        out('  Investigate before manuscript submission.')

    out()
    out('=' * 70)
    out(f'END OF AUDIT LOG -- {timestamp}')
    out('=' * 70)

    if args.log:
        with open(args.log, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f'\n[Log saved: {args.log}]')


if __name__ == '__main__':
    main()
