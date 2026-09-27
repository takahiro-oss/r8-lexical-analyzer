"""annotator_package_mapping.py -- S534-J, Pending 28 D11.

Relates the annotator package (214 distributed .txt files) to the populations the
manuscript defines (205 analysed documents, 196 with CMI > 0, 202 rater-labelled).
Prints counts only. The only identifiers printed are sn230, sn233 and WEB_043, which
the manuscript names or which EV-annot-003 names; no book-derived identifier is printed.

Run from the repository root (relative paths; DEC-038):
  ./.venv/Scripts/python.exe scripts/annotator_package_mapping.py
Exit 0 only if every input hash and every expected count matches.
"""
import csv
import hashlib
import sys
import zipfile
from pathlib import Path

INPUTS = {
    "docs/drafts/annotator_materials/annotator_corpus.zip": "46ec0dd7",
    "data/frozen/v1_9r/corpus_master.csv": "57abffa2",
    "data/frozen/v1_9/corpus_master.csv": "b562425a",
    "data/frozen/v1_9_rater_tmp/rater1_labels.csv": "88a2f64e",
    "data/frozen/v1_9_rater_tmp/rater2_labels.csv": "9da2465c",
}
EXPECTED = {
    "distributed_txt": 214,
    "distributed_in_205": 203,
    "distributed_not_in_205": 11,
    "not_in_205_absent_from_v1_9": 5,
    "not_in_205_in_v1_9_only": 6,
    "analysed_not_distributed": 2,
    "cmi_label_header_files": 196,
    "header_in_196": 186,
    "header_in_v1_9_only": 5,
    "header_absent_from_v1_9": 5,
    "header_within_202_rater_set": 191,
    "no_header_in_196": 10,
    "no_header_in_196_translation_header": 9,
    "no_header_in_196_no_header_at_all": 1,
    "rater_rows_each": 202,
    "v1_9_cmi_gt0": 202,
    "v1_9r_cmi_gt0": 196,
}
failures = []


def sha8(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:8]


def check(name, value):
    exp = EXPECTED[name]
    verdict = "MATCH" if value == exp else "MISMATCH"
    if value != exp:
        failures.append(name)
    print(f"{name:40s} {value:5d}  expected {exp:5d}  {verdict}")


for p, h in INPUTS.items():
    got = sha8(p)
    ok = h is None or got == h
    print(f"INPUT {p}  sha256[:8] {got}  " + ("MATCH" if h and ok else ("recorded" if h is None else "MISMATCH")))
    if not ok:
        failures.append("input:" + p)
if failures:
    print("HALT: input hash mismatch")
    sys.exit(1)


def load(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return {r["target"]: r for r in csv.DictReader(f)}


R = load("data/frozen/v1_9r/corpus_master.csv")
V = load("data/frozen/v1_9/corpus_master.csv")
pos196 = {t for t, r in R.items() if float(r["cmi"] or 0) > 0}
pos202 = {t for t, r in V.items() if float(r["cmi"] or 0) > 0}
for i in (1, 2):
    with open(f"data/frozen/v1_9_rater_tmp/rater{i}_labels.csv", encoding="utf-8-sig", newline="") as f:
        n = sum(1 for _ in csv.DictReader(f))
    check("rater_rows_each", n)
check("v1_9_cmi_gt0", len(pos202))
check("v1_9r_cmi_gt0", len(pos196))

z = zipfile.ZipFile("docs/drafts/annotator_materials/annotator_corpus.zip")
txt = [i for i in z.infolist() if i.filename.endswith(".txt")]
check("distributed_txt", len(txt))


def norm(stem):
    return stem[:-3] if stem.endswith("_ja") else stem


files = {}
for i in txt:
    head = z.read(i.filename).decode("utf-8", "replace")[:800]
    files[norm(i.filename[:-4])] = {
        "cmi_header": "CMIスコア" in head,
        "translation_header": "翻訳テキスト" in head,
        "any_header": any(l.startswith("#") for l in head.replace("\r", "").split("\n")[:8]),
        "date": i.date_time,
    }
if len(files) != len(txt):
    failures.append("stem collision after _ja normalisation")

D = set(files)
check("distributed_in_205", len(D & set(R)))
check("distributed_not_in_205", len(D - set(R)))
check("not_in_205_absent_from_v1_9", len(D - set(V)))
check("not_in_205_in_v1_9_only", len((D & set(V)) - set(R)))
nd = sorted(set(R) - D)
check("analysed_not_distributed", len(nd))
print("  analysed_not_distributed ids:", nd, " cmi:", [R[t]["cmi"] for t in nd])
if nd != ["sn230", "sn233"]:
    failures.append("analysed_not_distributed ids")

H = {s for s, f in files.items() if f["cmi_header"]}
check("cmi_label_header_files", len(H))
check("header_in_196", len(H & pos196))
check("header_in_v1_9_only", len((H & set(V)) - set(R)))
check("header_absent_from_v1_9", len(H - set(V)))
check("header_within_202_rater_set", len(H & pos202))
NH = pos196 - H
check("no_header_in_196", len(NH))
tr = {s for s in NH if files[s]["translation_header"]}
bare = {s for s in NH if not files[s]["any_header"]}
check("no_header_in_196_translation_header", len(tr))
check("no_header_in_196_no_header_at_all", len(bare))
print("  translation-header files all is_english=1:", all(R[s]["is_english"] == "1" for s in tr))
print("  no-header-at-all ids:", sorted(bare))
if sorted(bare) != ["WEB_043"] or not all(R[s]["is_english"] == "1" for s in tr):
    failures.append("header-absent composition")

dates = sorted({f["date"][:3] for f in files.values() if f["cmi_header"]})
print("  zip dates of CMI/label-header files:", dates)
print("  zip date of WEB_043:", files["WEB_043"]["date"])
late = sorted(f["date"] for s, f in files.items() if f["date"][:3] == (2026, 6, 3))
print("  files dated 2026-06-03:", len(late), " earliest", late[0], " latest", late[-1],
      " any with CMI/label header:", any(files[s]["cmi_header"] for s, f in files.items() if f["date"][:3] == (2026, 6, 3)))

print("RESULT:", "ALL MATCH" if not failures else "FAIL " + ", ".join(failures))
sys.exit(0 if not failures else 1)
