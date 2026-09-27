#!/usr/bin/env python3
"""
table5_recount_205.py -- producer for manuscript Table 5 (Label Distribution:
Human vs. LLM Annotators) on the 205-document corpus population (Pending 28 D16,
S564-J, 2026-09-23).

WHAT IT PRODUCES
    Per-run HIGH / MEDIUM / LOW counts of the two LLM annotators restricted to the
    205 corpus documents of data/frozen/v1_9r (CMI = 0.0 documents included), the
    five-run count ranges, their percentages at one decimal place, and the
    whole-percent ranges used in Section 4.5. Claude covers all 205 documents;
    Gemini covers 201, four corpus targets being absent from every Gemini run.

ROUNDING
    Python round(), i.e. round-half-to-even, per EV-rounding-001 (S323-J). The
    script reports whether any value sits on an exact tie.

GATES, all before any new value is printed; any failure ends with RESULT: FAIL.
    G1  SHA256 of corpus_master.csv and of the ten run files equal the pinned values.
    G2  The population is derived by two routes that must agree as SETS on every
        run file: A, run targets intersected with corpus_master; B, run targets
        minus the twelve identifiers outside the corpus (EV-r196-069).
    G3  Controls reproduced from existing records (DEC-083 rule 3):
        - full-run count ranges equal the printed Table 5 at manuscript 881f4ed5
          (EV-r196-069): Claude 87-89 / 64-66 / 64-66, Gemini 184-191 / 13-20 / 8-9;
        - per-run distributions on the CMI > 0 population equal EV-r196-067
          (Claude, n = 196) and EV-r196-068 (Gemini, n = 192), run by run;
        - human_label on the 205 documents equals EV-r196-029: 118 / 73 / 14.
    G4  Every ai_label in the population is HIGH, MEDIUM or LOW.
    Then the new values are compared with ACCEPT, fixed in the S564-J judgment
    sandbox before this script existed.

USAGE (from the repository root)
    python scripts/table5_recount_205.py [--frozen_dir data/frozen/v1_9r] [--log PATH]
    python scripts/table5_recount_205.py --self-test

Standard library only. Read-only. The frozen files are gitignored (third-party
corpus metadata); this script carries identifiers and counts only.
"""

import argparse
import csv
import hashlib
import os
import sys
from collections import Counter

LABELS = ('HIGH', 'MEDIUM', 'LOW')

PINS = {
    'corpus_master.csv':     '57abffa26425c79569309b6210c12a8432fe7db21eaa654754c2b54aa838f29b',
    'results_claude.csv':    '367cfef0399fc470319503d192a520f8364d30ffc89e36cb28a451e3199ec7bb',
    'results_claude_v2.csv': 'be6630f1bb024224764c3595a8f5d11d11bdc516fcf04b8dea13e9f72c949505',
    'results_claude_v3.csv': '34dc750670a4f1e32dfbd09a6caf12ab319f515039b41ca193fb07cf5d08dee9',
    'results_claude_v4.csv': 'f2f4591ca6a52af0f112a48579d5fcf17841d65402e83e1059b812dbea8876f1',
    'results_claude_v5.csv': 'e8b624f06b2d56d788e1a0ba1c4816c4de1cd34085493b3d0479238095a888f3',
    'results_gemini_v2.csv': '1280223a5e157c425e174731cb6dedf003d7752a7874217edd79072a85e07f60',
    'results_gemini_v3.csv': 'd0986d50a705d7cbc081b9406d3cf1d790f5686e3dba68faf07e8ee348d41ace',
    'results_gemini_v4.csv': '3c1e3a42dc8e09b985bd7842ecc22adf0c0550cef26d317553f7e9b281496fa8',
    'results_gemini_v5.csv': 'aaf2a715bf683252da222d0721d7dde0b883ba8c8cedc2bc29be721e7f8959b5',
    'results_gemini_v6.csv': '28712c2b92efcd57cf290eb5c02ea1d8187ecc6537b5d4053c7972b46c0ec8fc',
}

RUNS = {
    'Claude': ['results_claude.csv', 'results_claude_v2.csv', 'results_claude_v3.csv',
               'results_claude_v4.csv', 'results_claude_v5.csv'],
    'Gemini': ['results_gemini_v2.csv', 'results_gemini_v3.csv', 'results_gemini_v4.csv',
               'results_gemini_v5.csv', 'results_gemini_v6.csv'],
}

TWELVE_OUTSIDE_CORPUS = {
    'AD_053', 'AD_054', 'AD_065', 'AD_067', 'AD_071', 'AD_072',
    'AD_073', 'AD_074', 'AD_076', 'note122', 'note171', 'web198',
}
GEMINI_ABSENT = ['WEB_043', 'Web_089', 'note112', 'note_096']

# Controls from existing ledger rows (see docstring G3).
CONTROL_FULL_RANGES = {
    'Claude': {'HIGH': (87, 89), 'MEDIUM': (64, 66), 'LOW': (64, 66)},
    'Gemini': {'HIGH': (184, 191), 'MEDIUM': (13, 20), 'LOW': (8, 9)},
}
CONTROL_VALID_PER_RUN = {
    'Claude': [(81, 57, 58), (81, 57, 58), (81, 55, 60), (81, 56, 59), (83, 55, 58)],
    'Gemini': [(173, 13, 6), (170, 16, 6), (172, 14, 6), (172, 14, 6), (167, 18, 7)],
}
CONTROL_VALID_N = {'Claude': 196, 'Gemini': 192}
CONTROL_HUMAN_205 = (118, 73, 14)

# Acceptance values for the new population, fixed S564-J before this script.
ACCEPT = {
    'Claude': {'n': 205, 'HIGH': (84, 86), 'MEDIUM': (56, 58), 'LOW': (63, 65),
               'pct': {'HIGH': ('41.0', '42.0'), 'MEDIUM': ('27.3', '28.3'),
                       'LOW': ('30.7', '31.7')}},
    'Gemini': {'n': 201, 'HIGH': (173, 179), 'MEDIUM': (13, 19), 'LOW': (8, 9),
               'pct': {'HIGH': ('86.1', '89.1'), 'MEDIUM': ('6.5', '9.5'),
                       'LOW': ('4.0', '4.5')}},
}


def sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_rows(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def pct1(count, n):
    return f'{round(count * 100 / n, 1):.1f}'


def pct0(count, n):
    return f'{round(count * 100 / n):d}'


def is_tie(count, n, places):
    # exact rational test: count*100/n * 10**places has fractional part 1/2
    num = count * 100 * (10 ** places) * 2
    return num % n == 0 and (num // n) % 2 == 1


def compute(data):
    """data: dict filename -> list of row dicts. Returns (checks, values)."""
    checks = []

    def check(name, ok, detail=''):
        checks.append((name, bool(ok), detail))

    cm = data['corpus_master.csv']
    corpus = {r['target'] for r in cm}
    valid = {r['target'] for r in cm if float(r['cmi']) > 0}
    check('corpus_master rows 205 / unique 205 / valid 196',
          (len(cm), len(corpus), len(valid)) == (205, 205, 196),
          f'{len(cm)} / {len(corpus)} / {len(valid)}')
    human = Counter(r['human_label'] for r in cm)
    got_h = tuple(human[k] for k in LABELS)
    check('G3 human_label on 205 = 118 / 73 / 14 (EV-r196-029)',
          got_h == CONTROL_HUMAN_205, str(got_h))

    values = {}
    for model, files in RUNS.items():
        per_pop, per_full = [], []
        for i, fn in enumerate(files):
            rows = data[fn]
            targets = [r['target'] for r in rows]
            tset = set(targets)
            check(f'{model} {fn} no duplicate targets', len(targets) == len(tset),
                  f'{len(targets)} rows, {len(tset)} unique')
            route_a = tset & corpus
            route_b = tset - TWELVE_OUTSIDE_CORPUS
            check(f'G2 {model} {fn} route A == route B as sets', route_a == route_b,
                  f'A {len(route_a)} B {len(route_b)}')
            exp_missing = [] if model == 'Claude' else sorted(GEMINI_ABSENT)
            check(f'G2 {model} {fn} corpus targets absent from run',
                  sorted(corpus - tset) == exp_missing, str(sorted(corpus - tset)))
            pop = [r for r in rows if r['target'] in route_a]
            bad = sorted({r['ai_label'] for r in pop} - set(LABELS))
            check(f'G4 {model} {fn} labels in HIGH/MEDIUM/LOW', not bad, str(bad))
            c_pop = Counter(r['ai_label'] for r in pop)
            c_full = Counter(r['ai_label'] for r in rows)
            vrows = [r for r in rows if r['target'] in valid]
            c_val = Counter(r['ai_label'] for r in vrows)
            got_v = tuple(c_val[k] for k in LABELS)
            check(f'G3 {model} {fn} CMI>0 n and distribution (EV-r196-06{"7" if model == "Claude" else "8"})',
                  len(vrows) == CONTROL_VALID_N[model] and got_v == CONTROL_VALID_PER_RUN[model][i],
                  f'n {len(vrows)} {got_v}')
            per_pop.append((len(pop), c_pop))
            per_full.append(c_full)
        for k in LABELS:
            full_rng = (min(c[k] for c in per_full), max(c[k] for c in per_full))
            check(f'G3 {model} {k} full-run range = printed Table 5 (EV-r196-069)',
                  full_rng == CONTROL_FULL_RANGES[model][k], str(full_rng))
        ns = sorted({n for n, _ in per_pop})
        check(f'{model} population n constant across the five runs', len(ns) == 1, str(ns))
        n = ns[0]
        vals = {'n': n, 'per_run': [tuple(c[k] for k in LABELS) for _, c in per_pop]}
        for k in LABELS:
            lo = min(c[k] for _, c in per_pop)
            hi = max(c[k] for _, c in per_pop)
            vals[k] = (lo, hi)
            vals['pct1_' + k] = (pct1(lo, n), pct1(hi, n))
            vals['pct0_' + k] = (pct0(lo, n), pct0(hi, n))
            vals['tie_' + k] = any(is_tie(x, n, p) for x in (lo, hi) for p in (0, 1))
        values[model] = vals
    return checks, values


def accept(values):
    checks = []
    for model, a in ACCEPT.items():
        v = values[model]
        checks.append((f'ACCEPT {model} n = {a["n"]}', v['n'] == a['n'], str(v['n'])))
        for k in LABELS:
            checks.append((f'ACCEPT {model} {k} count range {a[k]}', v[k] == a[k], str(v[k])))
            checks.append((f'ACCEPT {model} {k} percent {a["pct"][k]}',
                           v['pct1_' + k] == a['pct'][k], str(v['pct1_' + k])))
            checks.append((f'{model} {k} no exact tie at 0 or 1 decimal', not v['tie_' + k], ''))
    return checks


def load(frozen_dir):
    data, pin_checks = {}, []
    for fn, pin in PINS.items():
        path = os.path.join(frozen_dir, fn)
        if not os.path.exists(path):
            pin_checks.append((f'G1 {fn} exists', False, path))
            continue
        h = sha256(path)
        pin_checks.append((f'G1 {fn} SHA256 pinned', h == pin, h[:8]))
        data[fn] = read_rows(path)
    return data, pin_checks


def report(checks, out):
    fails = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        out(f'  [{"OK" if ok else "FAIL"}] {name}' + (f'  ({detail})' if detail else ''))
    return fails


def run(frozen_dir, log_path):
    lines = []

    def out(s=''):
        print(s)
        lines.append(s)

    out('table5_recount_205.py -- Table 5 on the 205-document corpus population')
    out(f'frozen_dir: {frozen_dir}')
    data, pin_checks = load(frozen_dir)
    out('GATE G1 (pins)')
    fails = report(pin_checks, out)
    if fails:
        out(f'RESULT: FAIL (G1: {len(fails)} pin check(s) failed)')
        return finish(lines, log_path, 1)
    checks, values = compute(data)
    out('GATES G2-G4 and controls')
    fails = report(checks, out)
    if fails:
        out(f'RESULT: FAIL (gates: {len(fails)} check(s) failed; no new value printed)')
        return finish(lines, log_path, 1)
    out('VALUES (population = the 205 corpus documents present in each run file)')
    for model in ('Claude', 'Gemini'):
        v = values[model]
        out(f'  {model} n per run = {v["n"]}; per run (HIGH, MEDIUM, LOW): {v["per_run"]}')
        for k in LABELS:
            lo, hi = v[k]
            p1, p0 = v['pct1_' + k], v['pct0_' + k]
            out(f'  {model} {k:6s} counts {lo}-{hi}  percent {p1[0]}-{p1[1]}  '
                f'whole percent {p0[0]}-{p0[1]}')
    out('TABLE 5 CELLS (as the manuscript prints them)')
    for k in LABELS:
        cells = []
        for model in ('Claude', 'Gemini'):
            v = values[model]
            cells.append(f'{v["pct1_" + k][0]}\u2013{v["pct1_" + k][1]}% '
                         f'({v[k][0]}\u2013{v[k][1]})')
        out(f'  | {k} | ... | {cells[0]} | {cells[1]} |')
    out('ACCEPTANCE')
    fails = report(accept(values), out)
    if fails:
        out(f'RESULT: FAIL (acceptance: {len(fails)} check(s) failed)')
        return finish(lines, log_path, 1)
    out('RESULT: PASS')
    return finish(lines, log_path, 0)


def finish(lines, log_path, code):
    if log_path:
        with open(log_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        print(f'[log written: {log_path}]')
    return code


def self_test(frozen_dir):
    """Mutation tests on in-memory copies of the pinned data."""
    data, pin_checks = load(frozen_dir)
    if any(not ok for _, ok, _ in pin_checks):
        print('self-test: cannot run, pinned inputs unavailable')
        print('RESULT: FAIL (self-test inputs)')
        return 1
    failures = 0

    def expect(name, checks_fn, want_fail):
        nonlocal failures
        checks = checks_fn()
        failed = any(not ok for _, ok, _ in checks)
        good = failed == want_fail
        failures += (not good)
        print(f'  [{"OK" if good else "FAIL"}] {name}: '
              f'{"detected" if failed else "clean"} (expected {"detected" if want_fail else "clean"})')

    def clone():
        return {k: [dict(r) for r in v] for k, v in data.items()}

    base = lambda: compute(data)[0] + accept(compute(data)[1])
    expect('unmodified data', base, False)

    def m1():  # flip one in-corpus Claude label: a control or acceptance must fire
        d = clone()
        for r in d['results_claude.csv']:
            if r['target'] == 'AD_001':
                r['ai_label'] = 'LOW' if r['ai_label'] != 'LOW' else 'HIGH'
        c, v = compute(d)
        return c + accept(v)
    expect('one Claude label flipped', m1, True)

    def m2():  # add an out-of-corpus identifier not in the twelve: route A != route B
        d = clone()
        r = dict(d['results_gemini_v2.csv'][0]); r['target'] = 'ZZ_999'
        d['results_gemini_v2.csv'].append(r)
        return compute(d)[0]
    expect('extra identifier outside both routes', m2, True)

    def m3():  # unknown label inside the population
        d = clone()
        d['results_gemini_v3.csv'][0]['ai_label'] = 'Intent-Unresolved'
        return compute(d)[0]
    expect('unknown label', m3, True)

    def m4():  # drop one corpus row from a Claude run
        d = clone()
        d['results_claude_v4.csv'] = [r for r in d['results_claude_v4.csv'] if r['target'] != 'AD_001']
        return compute(d)[0]
    expect('corpus target missing from a Claude run', m4, True)

    print(f'self-test: {failures} failure(s)')
    print('RESULT: PASS' if failures == 0 else f'RESULT: FAIL (self-test: {failures})')
    return 0 if failures == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--frozen_dir', default=os.path.join('data', 'frozen', 'v1_9r'))
    ap.add_argument('--log', default=None)
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test(a.frozen_dir))
    sys.exit(run(a.frozen_dir, a.log))


if __name__ == '__main__':
    main()
