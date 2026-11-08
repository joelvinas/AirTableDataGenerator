# Fictional Fashionwear - proxy base kit

Synthetic, fully fictional proxy for the Airtable -> Workfront Planning migrator. Python standard library only (Pillow is used for one optional JPEG if present). Output is deterministic (seed 20261108): two runs give byte-identical `out/`.

Every email is `@example.com`, phones are `555-01xx`, names/companies are invented, and every PDF/PNG/SVG carries "SAMPLE - FICTIONAL DATA". The only exception is the 20 original rows' `@monarchmenswear.com` addresses, kept because you asked for the original ~20 records to be preserved exactly. Use `--sanitize-legacy` to swap them to example.com (this breaks exact preservation of those values).

## Layout
| File | Purpose |
|---|---|
| `fw_*.py`, `generate.py` | schema DSL, data, files, graph, profile; `generate.py` writes everything to `out/` |
| `verify.py` | offline self-check (2,028 checks) |
| `seed.py`, `teardown.py`, `burst_429.py` | Airtable API seeding, reset, optional 429 trigger |
| `verify_live_schema.py` | diff live trial-base schema vs expected |
| `compare.py` | compare migrator exports to the answer key |
| `legacy/` | the six original CSVs (inputs) |
| `out/schema` | Metadata-API-shaped schema per base | 
| `out/data_csv` | raw CSV per table (for manual CSV import) |
| `out/seed_payload` | JSONL used by seed.py |
| `out/attachments` | blobs, manifest.json, `manual_upload/` (the >5 MB file) |
| `out/answer_key` | expected_profile / load_order (+_literal) / link_treatment / attachments |
| `out/reports` | summary.md, manual_steps.md, legacy_check.txt |

Size: ff_main 33 tables / 411 fields / ~2,900 rows (SalesItems = 1,250, change with `--large-rows`; Quota Stress Wide = 124 fields); ff_ops 6 tables / 28 fields / ~317 rows (name collisions with ff_main); 379 attachment files, ~14.6 MB.

## Run order
1. `python generate.py` then `python verify.py` (offline, no token needed).
2. Create two empty bases in a trial workspace, named with the prefix **TRIAL** (e.g. "TRIAL Fictional Fashionwear Main" / "...Ops"). Or `python seed.py --phase create-bases` (needs `workspace_id`; delete the placeholder table afterwards).
3. `cp seed_config.example.json seed_config.json` and fill in base IDs and your **write** token (scopes: data.records:read/write, schema.bases:read/write). The file is gitignored; the token is never printed or logged (`seed_calls.log` holds method/path/status only).
4. `python seed.py --dry-run --phase all` (shows request counts, no network).
5. `python seed.py --phase preflight` (refuses any base whose name does not start with the trial prefix).
6. `python seed.py --phase schema`, then do the manual UI steps in `out/reports/manual_steps.md` (turn off "Allow linking to multiple records" where listed; **never delete an inverse link field**, because Airtable then converts the other side of the pair to plain text; create anything listed in `seed_log.json` -> `failed_fields`), then `python verify_live_schema.py` until clean.
7. `python seed.py --phase records`, `--phase links`, `--phase attachments` (or `--phase all`). Safe to stop and re-run: records upsert on the primary field, and `seed_log.json` tracks progress.
8. Upload `out/attachments/manual_upload/*` by hand (over the 5 MB API limit).
9. Run the migrator (separate read-only token). Compare with `compare.py`.
10. Reset: `python teardown.py --yes` (deletes records only; there is no table-delete API).

Time: about 950 calls at ~4.5 req/s per base is a few minutes, plus 379 uploads. Free plans cap 1,000 records per base and 1,000 API calls per workspace per month, so use a Team trial or lower `--large-rows` and expect to exceed the call quota on Free.

## Test plan (migrator vs answer key)
1. **Load order**: export the migrator's report per base, run `python compare.py --load-order report.csv --mode resolve --base ff_main` (and `--mode literal` with "Resolve two-way link pairs" off). Expect exact load numbers and depths. Ties: name, then table ID. Cross-base ties can differ because ff_ops reuses table names, so numbering is per base.
2. **Link treatment**: eyeball/compare `expected_link_treatment.csv` (second-pass yes/no, reason, per mode). Check inverse fields are not treated as separate dependencies, self-links are ignored for ordering, and both-single / neither-single pairs stay cycles.
3. **Profile**: `python compare.py --profile profile.csv --base ff_main`. Hard failures = real mismatches; "soft" lines are fields flagged as uncertain in the key (whitespace-only, observed fields, link order, precision merges, typecast choices, API-created-or-not).
4. **Attachments**: compare counts, sizes, filenames and sha256/md5 to `expected_attachments.csv`; confirm checksum-duplicate groups across records and the 0/1/3+ cell shapes; the >5 MB file exists only after the manual upload.
5. **Rate limits**: while idle, `python burst_429.py --yes`; the migrator's next calls should back off ~30 s and resume. For a 403, point the *read-only migrator token* at a base it was not granted, or attempt a write call; record the status you see (403 expected, 404/401 possible).
6. **Throughput**: 100 records/page at ~5 req/s: SalesItems (1,250 rows) is 13 pages.

Real table/field IDs differ from the placeholder IDs in the key; match by (base, table, field name). Per-base load numbering is used.
