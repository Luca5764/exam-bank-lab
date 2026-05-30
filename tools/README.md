# Maintained Tools

This directory keeps scripts that are still useful for rebuilding the static
site data or importing exam banks. One-off experiments and obsolete parser
prototypes should stay outside the repository, preferably under `.tmp/`.

## Site maintenance

- `build_index.py` rebuilds `data/banks.json` from `questions/*.json`.
- `update_changelog.ps1` is used by `.githooks/post-commit` to update
  `data/changelog.json`.

## Law data

- `build_laws.js` rebuilds `data/laws.json` from law text files.
- `generate_law_explanations_gemini.py` generates law article explanations.
- `generate_law_explanation_layouts_gemini.py` generates display layout blocks
  for law explanations.
- `generate_law_links.py` rebuilds deterministic law cross-links.

## Question-bank imports

- `build_tvee_bank.py` builds TVE accounting/economics banks.
- `convert_liteparse_questions.py` converts LiteParse coordinate output into
  quiz-bank JSON.
- `import_management_questions.py` imports irrigation-management and TVE
  agriculture PDF text layers.
- `normalize_question_spacing.py` removes accidental Chinese word-break spaces
  from question-bank JSON while preserving table-like option spacing.
- `run_management_hybrid_import.py` is the preferred end-to-end management-bank
  pipeline.

## Visual materials

- `crop_tvee_questions.py` crops full TVE question screenshots.
- `crop_tvee_materials.py` crops chart or figure material from TVE questions.
- `extract_materials_vision.py` uses a vision model only for missing
  `materials` blocks in existing question JSON.
