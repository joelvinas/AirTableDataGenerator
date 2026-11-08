# Fictional Fashionwear - proxy base kit

Synthetic, fully fictional proxy for the Airtable -> Workfront Planning migrator. Python standard library only (Pillow is used for one optional JPEG if present). Output is deterministic (seed 20261108): two runs give byte-identical `out/`.

Every email is `@example.com`, phones are `555-01xx`, names/companies are invented, and every generated PDF/PNG/SVG carries "SAMPLE - FICTIONAL DATA". The only exception is the 20 original rows' `@monarchmenswear.com` addresses, kept so the original ~20 records are preserved exactly. Use `--sanitize-legacy` to swap them to example.com (this breaks exact preservation of those values).

This kit covers the **generation and ingestion** phase: build the data, load it into two trial Airtable bases, and check it landed. Extracting the bases with the migrator is the next phase and is outside this kit, except for `compare.py` and the answer key it compares against.

## Layout
```
README.md  LICENSE  .gitignore  seed_config.example.json     (root)
seed_config.json  seed_log.json  seed_calls.log               (root; your token and run state, gitignored)
src/       all Python (run everything from the repo root, e.g. python src/seed.py ...)
docs/      ASSUMPTIONS.md  CHANGELOG_SCHEMA.md  COVERAGE.md
legacy/    the six original CSVs (inputs)
out/       everything generated (gitignored)
```

| File in `src/` | Purpose |
|---|---|
| `fw_*.py`, `generate.py` | schema DSL, data, files, graph, profile; `generate.py` writes everything to `out/` |
| `verify.py` | offline self-check (2,025 checks) |
| `seed.py` | seeding, plus `--adopt`, `--adopt-links` and `--check-attachments` for data loaded by hand |
| `teardown.py`, `burst_429.py` | reset (records only), optional 429 trigger |
| `verify_live_schema.py` | diff live trial-base schema vs expected (`--dump` saves the live schema) |
| `show_failures.py`, `probe_link.py` | read `seed_log.json` failures; probe one failing link field |
| `compare.py` | compare migrator exports to the answer key |

| Folder under `out/` | Contents |
|---|---|
| `schema` | Metadata-API-shaped schema per base |
| `data_csv` | raw CSV per table (for manual CSV import) |
| `seed_payload` | JSONL used by seed.py |
| `attachments` | blobs, manifest.json, `manual_upload/` (the >5 MB file) |
| `answer_key` | expected_profile / load_order (+_literal) / link_treatment / attachments |
| `reports` | summary.md, manual_steps.md, legacy_check.txt |
| `live_attachments.csv` | written by `seed.py --check-attachments`: what is really in the attachment cells |

All commands in this README are run from the repo root.

Size: ff_main 33 tables / 421 fields / ~2,900 rows (SalesItems = 1,250, change with `--large-rows`; Quota Stress Wide = 124 fields); ff_ops 6 tables / 29 fields / ~317 rows (name collisions with ff_main); 379 attachment files, ~14.6 MB.

## Run order
1. `python src/generate.py` then `python src/verify.py` (offline, no token needed).
2. Create two empty bases in a trial workspace, named with the prefix **TRIAL** (e.g. "TRIAL Fictional Fashionwear Main" / "...Ops"). Or `python src/seed.py --phase create-bases` (needs `workspace_id`; delete the placeholder table afterwards).
3. `cp seed_config.example.json seed_config.json` and fill in base IDs and your **write** token (scopes: data.records:read/write, schema.bases:read/write). The file is gitignored; the token is never printed or logged (`seed_calls.log` holds method/path/status only).
4. `python src/seed.py --dry-run --phase all` (request counts, no network). A dry run reads your real `seed_log.json`, so it also shows what is already done.
5. `python src/seed.py --phase preflight` (refuses any base whose name does not start with the trial prefix).
6. `python src/seed.py --phase schema`, then in the app turn off "Allow linking to multiple records" on the fields `python src/verify_live_schema.py` lists as `SINGLE-LINK PREF`. **Never delete an inverse link field**: Airtable then converts the other side of the pair to plain text. Create `Field Type Showcase.Button` by hand (name `Button`, URL formula `"https://example.com"` in double quotes). Repeat `verify_live_schema.py` until only the known leftovers remain (see docs/ASSUMPTIONS.md).
7. Optional: load some tables by CSV import instead of the API (saves calls; also exercises the app). Import parents before children, leave link columns unmapped when the target table is empty, keep imports under 1,000 rows, then run `python src/verify_live_schema.py` again (an import can change field types). Tell the seeder with `python src/seed.py --adopt "Table" ... [--adopt-links] --only-base ff_main`. `--adopt-links` only if you imported the link columns too; it reads them back and logs only the rows that match.
8. `python src/seed.py --phase records`, then `--phase links`, then `--phase attachments`. Safe to stop and re-run: records upsert on the primary field, and `seed_log.json` tracks progress.
9. If you uploaded attachments by hand, run `python src/seed.py --check-attachments` before the attachments phase. Add `--accept-existing` to leave cells that already hold files alone; leave it off to test that uploads append.
10. Upload `out/attachments/manual_upload/*` by hand (over the 5 MB API limit).
11. Verify: `python src/show_failures.py` (0 failed batches; only `Naming Edge Cases.total` under field creation is expected), `python src/seed.py --adopt <every table with links> --adopt-links` (all rows match), `python src/seed.py --check-attachments` (only the rejected `empty.txt` missing). `probe_link.py "Table" "Field"` diagnoses one failing link field.
12. Reset: `python src/teardown.py --yes` (deletes records only, including files you uploaded by hand; there is no table-delete API). Revoke the write token when testing is finished.

## API call budget
Approximate, per full seed: schema ~25 per run, records ~330 (less for tables imported by hand), links ~110, attachments ~377, plus about 1 read per 100 records for each adopt or check. A full API seed is about 940 calls; each re-run of a phase only does what is missing. Free plans cap 1,000 records per base and 1,000 API calls per workspace per month; a Team trial should allow far more (check your plan page). The 5 req/s limit is per base on every plan.

## Test plan (migrator vs answer key)
1. **Load order**: export the migrator's report per base, run `python src/compare.py --load-order report.csv --mode resolve --base ff_main` (and `--mode literal` with "Resolve two-way link pairs" off). Expect exact load numbers and depths. Ties: name, then table ID. Cross-base ties can differ because ff_ops reuses table names, so numbering is per base.
2. **Link treatment**: eyeball/compare `expected_link_treatment.csv` (second-pass yes/no, reason, per mode). Check inverse fields are not treated as separate dependencies, self-links are ignored for ordering, and both-single / neither-single pairs stay cycles.
3. **Profile**: `python src/compare.py --profile profile.csv --base ff_main`. Hard failures = real mismatches; "soft" lines are fields flagged as uncertain in the key (whitespace-only, observed fields, link order, precision merges, typecast choices, API-created-or-not).
4. **Attachments**: compare counts, sizes, filenames and sha256/md5 with `expected_attachments.csv`. For the 20 `Items.Product Photo` cells that also hold a hand-uploaded photo, use `out/live_attachments.csv` (your photo is position 1, ours position 2). `compare.py` does not check attachments yet.
5. **Rate limits**: while idle, `python src/burst_429.py --yes`; the migrator's next calls should back off ~30 s and resume. For a 403, point the *read-only migrator token* at a base it was not granted, or attempt a write call; record the status you see (403 expected, 404/401 possible).
6. **Throughput**: 100 records/page at ~5 req/s: SalesItems (1,250 rows) is 13 pages.

Real table/field IDs differ from the placeholder IDs in the key; match by (base, table, field name). Per-base load numbering is used.
