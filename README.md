# R8 Cognitive Risk Analyzer

Lexical framework for detecting linguistic signals associated with cognitive
manipulation risk in Japanese text. R8 scores documents on a Cognitive
Manipulation Index (CMI) computed from dictionary-based category densities.

This repository holds the analysis code and the annotation criteria. The
research data bundle (corpus-level data, per-run results, rater labels,
codebook) is archived separately at Zenodo: 10.5281/zenodo.21928851.
Manuscript: 10.5281/zenodo.19306870.

## Licensing

- Code (`*.py`): MIT License — see `LICENSE`.
- Annotation criteria and documentation (`docs/`): CC BY 4.0 — see
  `LICENSE-CC-BY-4.0`.

## What R8 measures — and what it does not

R8 characterises lexical structure. Scores and labels are not findings about
the intent, honesty, or legality of any author or organisation; a HIGH
classification neither establishes nor implies deceptive purpose.

Measured performance on the v1.9 calibration corpus (205 documents, of which
196 carry a valid CMI above zero): Precision 97.6%, Recall 34.7%, F1 51.2.
These are calibration metrics against a single-rater reference — the author's
labels — not performance against a validated ground truth.

Reliability bounds every figure above. A preliminary assessment with two
independent human raters yielded Cohen's κ = 0.094 and κ = 0.197, both in the
insufficient tier of the framework pre-specified for the study. A two-model
LLM pilot yielded Cohen's κ = 0.241 (Claude Sonnet 4.6, n = 196) and κ = 0.111
(Gemini 2.5 Flash, n = 192). The reference against which Precision and Recall
were computed is therefore not established as reproducible across raters.

Known structural limitations, documented in the manuscript:

- A LOW classification does not assert the absence of manipulation — only that
  matched-term density did not reach the escalation threshold. A text whose
  vocabulary falls outside the dictionaries scores LOW by construction.
- Recall is low. A documented false-negative mechanism is surface-positive
  vocabulary manipulation, in which manipulative structure is carried by
  vocabulary the dictionaries do not flag.
- Detection scope is lexical. Fact-based disinformation — specific factual
  claims whose falsity cannot be assessed through lexical analysis — falls
  categorically outside it.

## Not recommended uses

The MIT license imposes no field-of-use restriction, so the following is a
statement of validation status, not a legal restriction: R8 has not been
validated for decisions affecting individuals (employment, credit, moderation,
legal or reputational judgments). Do not use scores as evidence about a
specific author's intent or character.

## Contents

- `r8.py` — scanner (per-category densities, CMI)
- `mass_audit.py` — batch scoring
- corpus preparation: `clean_corpus.py`, `preprocess.py`, `mask_corpus.py`,
  `remove_duplicate.py`, `quality_check.py`, `translate_corpus.py`
- `scripts/` — corpus acquisition and annotation support (`url_to_txt.py`,
  `url_batch.py`, `ocr_batch.py`, `pdf_to_corpus_clean.py`,
  `genre_classifier.py`, `make_annotation_sheet.py`, `apply_labels.py`,
  `gemini_kappa_stability.py`)
- `scripts/` — reproduction of reported values (`kappa_compute.py`,
  `human_kappa_compute.py`, `subgroup_kappa_compute.py`,
  `run_stability_compute.py`, `verify_public_bundle.py`). These computed
  the reliability figures reported in the manuscript and verify the
  archived bundle; they read the Zenodo bundle named above.
- `scripts/` — recomputation of further reported values from the same
  bundle. Each script checks its output against the values recorded for
  the manuscript and exits non-zero if any check fails. Some also contain a
  mode that reads internal files which are not released; that mode is not
  needed to reproduce the reported values. With the bundle unpacked in
  `<bundle>`:

  ```
  python scripts/table2_recount.py --public_master <bundle>/corpus_master.csv
  python scripts/table2_hp60_recount_r196.py --public_master <bundle>/corpus_master.csv
  python scripts/table3_recount.py --public_master <bundle>/corpus_master.csv
  python scripts/table4_recount.py --frozen_dir <bundle> --public_check
  python scripts/table4_human_recount.py --public_master <bundle>/corpus_master.csv
  python scripts/verify_table4_crosstab.py --bundle_dir <bundle>
  python scripts/phase1_calibration_recount.py --public_master <bundle>/corpus_master.csv
  python scripts/recount_corpus_r196.py --public_master <bundle>/corpus_master.csv --rater1 <bundle>/rater1_labels.csv
  python scripts/document_level_values_recount.py --public_master <bundle>/corpus_master.csv --r8py r8.py
  python scripts/permutation_pairs_compute.py --public_dir <bundle>
  python scripts/reason_code_mcnemar.py --public_dir <bundle>
  python scripts/short_form_rater_labels.py --master <bundle>/corpus_master.csv --rater1 <bundle>/rater1_labels.csv --rater2 <bundle>/rater2_labels.csv
  ```
- `requirements.txt` — third-party packages required to run the above
- `docs/drafts/` — annotation criteria v0.8 (current) and v0.7.1 (the version
  in use during the calibration reported in the manuscript), with the v0.8
  annotator guide and limitation note

Note for Windows users: clone with `core.autocrlf` disabled or rely on this
repository's `.gitattributes` (`* text=auto eol=lf`); recorded file hashes are
defined over LF content.

## Data and reproduction

The Zenodo record is authoritative for reproducing the values reported in the
manuscript, and holds the frozen dataset corresponding to them. This
repository reflects continuing development and is not version-bound to those
figures. To reproduce the reported figures, use the tag `manuscript-v1.9-2`,
which the bundle MANIFEST also names.

Original texts are not redistributed: the source documents are third-party
copyrighted material.

## Citation

Saito, Takahiro (2026). R8: An Exploratory Lexical Framework for Approximating Cognitive Manipulation Risk in Text. 10.5281/zenodo.19306870.
ORCID: 0009-0005-9464-6260.
