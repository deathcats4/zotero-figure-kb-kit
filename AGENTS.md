# Agent Instructions

This repository is a portable local workflow for extracting figures from Zotero PDFs into a reviewable figure knowledge base.

## Primary Goal

Use the bundled workflow so the user can run figure extraction without hand-cropping figures.

## Source of Truth

- Read `FOR_OTHER_AI.md` first for a fast handoff summary
- Read `skill/SKILL.md` before doing substantive work
- Use `skill/scripts/check_setup.py` to validate the environment
- Use `skill/scripts/figure_kb_workflow.py` for all workflow actions
- Assume this repo may be running on a machine other than the original author's

## Default Behavior

- Use the built-in default workflow first
- Choose `safe` or `auto` based on the user's preference
- In `safe` mode, stop after `extract` unless the user explicitly asks for ingest or has already edited `review.csv`
- In `auto` mode, allow `extract --ingest-mode auto` to continue directly into ingestion
- Treat `skill/assets/profiles/starter_profile.json` as an optional starter example, not as the core workflow
- Do not create ad hoc root-level test folders
- Keep temporary tests inside the current workspace only, and remove them after validation
- Do not assume the author's Zotero path, Python path, or manuscript project structure exists locally

## Scope Boundaries

- This repo is for the minimum shareable workflow
- Do not add project-specific domain or manuscript logic unless the user explicitly asks for a specialized profile
- Prefer explicit commands and file paths that another AI agent can reproduce locally
- Prefer the shortest runnable path before introducing profile customization
- Treat environment settings and topic profiles as separate concerns
