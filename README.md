# Fictional Fashionwear: synthetic data generation and Airtable upload

**Author:** Joel Vinas · **License:** MIT

## 1. Executive summary

This project does two things: it **generates** a large, deterministic, entirely fictional relational dataset, and it **uploads** that dataset to Airtable through the Web API, measuring how the API behaves along the way.

The dataset describes a fictional luxury retailer, "Fictional Fashionwear". It is built to be hard on purpose, so that an upload exercises the API's edges instead of its happy path:

- **33 tables, 421 fields and about 2,900 records in one base, and 6 tables with deliberately colliding names in a second.**
- **Every link topology:** 2- and 3-table cycles, self-links, many-to-many pairs, diamonds, a six-level dependency chain, and tables with no links.
- **Every API-creatable field type, plus a "data quality lab"** of nulls, empty strings, whitespace, numeric edges and awkward names.
- **379 attachments** (about 14.6 MB), including a 0-byte file, a file over the 5 MB API limit, duplicate names and checksums, and a 255-character filename.
- **A 124-field table** to test field-count limits, and a **1,250-row table** to test volume and pagination.

Generation uses only the Python standard library and is deterministic from a fixed seed. The uploader is resumable, rate-limit-aware and restricted to trial bases. Alongside the data, the generator writes an **answer key**: the expected row counts, null counts, cardinalities, link treatment and attachment checksums, so a load can be checked against what it should have produced.

## 2. How it works

```
legacy/ (six original CSVs)
   │
   ▼
generate.py ──► out/schema        Airtable-metadata-shaped schema per base
   │          ► out/data_csv      raw CSVs (for manual import)
   │          ► out/seed_payload  JSONL used by the uploader
   │          ► out/attachments   blobs + manifest (sha256/md5)
   │          ► out/answer_key    expected profile, link treatment, load order, attachments
   ▼
verify.py        2,025 offline consistency checks (no network)
   ▼
seed.py ──► Airtable Web API ──► two TRIAL bases
   │         phases: preflight → schema → records → links → attachments
   ▼
verify_live_schema.py · show_failures.py · seed.py --adopt / --check-attachments
   (read the live bases back and compare with the expected schema and the upload log)
```

**Schema DSL.** `fw_schema.py` declares every table, field and link in a compact Python DSL. From that single description the generator derives the Airtable schema, the data, the profile and the answer key, so the key and the uploaded data cannot drift apart.

**Two-pass upload.** Link fields cannot be filled until the linked records exist. `seed.py` upserts all records first (matching on each table's primary field), builds a map from primary-field value to Airtable record ID, then fills link cells in a second pass.

**Resumable by design.** `seed_log.json` records each completed batch. Interrupted runs resume where they stopped, and completed work is never repeated. Entries that failed and later succeeded are pruned, so the failure report shows only what is still wrong.

**Adopting hand-loaded data.** Tables loaded by CSV import (to save API calls) are reconciled with `--adopt`. The tool reads the live table back, translates record IDs to primary-field values, and logs only the rows that match. `--adopt-links` does the same for link cells.

## 3. Technical design

### API constraints respected
- 10 records per create/update request; 5 requests per second per base; 50 per second per token.
- A 429 response is followed by a 30-second wait.
- Attachments upload as base64 through the `uploadAttachment` endpoint (5 MB limit).
- Link fields are created with only `linkedTableId`; Airtable creates the inverse automatically.

### Call budget and speed
A full API seed costs about 940 calls (schema about 25 per run, records about 330, links about 110, attachments about 377, plus roughly one read per 100 records for each adopt or check). Re-running a phase does only what is missing. Loading the 1,250-row table by CSV import avoids roughly 125 calls. Free plans cap API calls at 1,000 per workspace per month, so the full upload needs a paid or trial plan. `burst_429.py` deliberately triggers the rate limit so the 30-second recovery can be observed.

### Link-dependency analysis
The answer key includes the order in which tables depend on each other through links:
- Each link field A → B is a child → parent edge; self-links are ignored for ordering.
- Strongly connected components (Tarjan's algorithm) form a single step; ties are broken by (table name, table ID); ordering within a step uses Kahn's algorithm.
- Depth is the longest parent chain at component level.
- **Resolve mode:** for an inverse pair where exactly one side allows a single record, that table is the child. Pairs where both sides, or neither side, are single-record stay cycles.
- **Literal mode:** every pair is a two-table cycle. Because every link here has an inverse, literal mode collapses much of the graph into large cycles, so the key includes both orderings.

### Safety
- The uploader refuses any base whose name does not start with `TRIAL`.
- The write-capable token lives only in `seed_config.json` (gitignored). It is never printed or logged; `seed_calls.log` records method, path and status only.
- `--dry-run` reads the real log and reports request counts without any network call.

### Reproducibility
Output is deterministic (seed 20261108): two runs produce byte-identical `out/`. Only the Python standard library is required; Pillow is used for one optional JPEG if installed.

## 4. Data quality

Data quality here has two meanings: the data must be **safe to publish**, and it must be **deliberately imperfect in known ways**.

### Safe to publish
- **Emails** use `@example.com`, a domain reserved for documentation (RFC 2606).
- **Phone numbers** use the `555-01xx` range, which the North American Numbering Plan reserves for fictional use.
- **Names and companies** are invented. Generated PDFs, PNGs and SVGs carry "SAMPLE - FICTIONAL DATA".
- **Legacy rows** (about 20 per original table) are preserved exactly, except that the 20 legacy emails were hand-edited from a real-looking domain to `example.com`, and one item name containing a real brand was hand-renamed to "Heritage Wool Trench Coat". `generate.py --sanitize-legacy` applies the email change automatically from unedited originals.
- **No affiliation:** the business is not The Men's Wearhouse or any real company (see Provenance).

### Deliberately imperfect, with known answers
The **Data Quality Lab** table has fields whose names say what they contain: always empty, always filled, mixed, empty string, empty array, rating 0, checkbox false versus missing, and whitespace-only text. Other cases:

| Concern | Where |
|---|---|
| Numeric edges (0, negatives, very large, precision rounding) | Data Quality Lab; Items prices of 0 |
| Formula error value | Margin on a price of 0 |
| Rollup/lookup over no links | Purchase, Field Type Showcase |
| Duplicate links in one cell (Airtable collapses them) | Flagged in the profile; key records the collapsed result |
| Link cells with 100+ records | Lookbooks (110), one Purchase with 110 SalesItems |
| Name hazards (case, spaces, emoji, quotes, commas, very long) | Naming Edge Cases (30 fields) |
| Time zones, date extremes | Showcase, Data Quality Lab |
| Name collisions across bases | Second base reuses table names |

Each field in `expected_profile.csv` carries a row count, null count, cardinality, value source and flags. Fields whose correct value is uncertain (whitespace trimming, link-array order, formula-error shape) are flagged so a comparison reports them as informational "soft" lines rather than failures.

## 5. Verification so far

| Check | Result |
|---|---|
| Offline self-consistency (`verify.py`) | 2,025 checks, 0 failed |
| Legacy rows preserved | Checked against `legacy/` by the generator |
| Live schema against expected (`verify_live_schema.py`) | Matches, apart from the known leftovers in Section 6 |
| Record counts and every forward link, both bases | Verified live; all rows match via `--adopt --adopt-links` |
| Attachments (`--check-attachments`) | 378 of 379 present; the missing one is the intentionally rejected 0-byte file |
| Append behaviour for attachments | Confirmed: uploads append and keep upload order |
| `compare.py` against its own key | 1,428 match, 0 fail |

## 6. Assumptions, hurdles and call-outs

### Assumptions
- **Legacy ID columns were converted to real links**, in place, as a judgment call.
- **A 1,250-row large table** was chosen to be above one page and below the smallest paid record cap. Per-base record caps cited (Oct 2026): Free 1,000, Team 50,000.
- **Collaborator fields** are skipped unless workspace member emails are supplied.
- **Unverified:** link-array order inside a cell, the shape of a formula error value, whether whitespace-only strings are trimmed, and autonumber values (which assume one uninterrupted seed run). These are flagged "soft" in the profile.

### Hurdles discovered by testing against the live service
- **Links always have an inverse.** The API cannot create one-way links or turn off "Allow linking to multiple records". Deleting one side of a link pair converts the other side to plain text (observed). An early version of this project wrongly told the user to delete inverse fields; that instruction was removed once the behaviour was observed, and the key now reflects inverses everywhere.
- **Single-record link preference** therefore needs manual toggles in the app; `verify_live_schema.py` lists them as `SINGLE-LINK PREF`.
- **Computed fields need exact options:** rollups require `formula: "SUM(values)"`; `createdTime` takes no options; `lastModifiedTime` takes only `referencedFieldIds`.
- **Some fields cannot be created by API.** The Button field was created by hand (name `Button`, URL formula `"https://example.com"`).
- **`Naming Edge Cases.total` does not exist** in the live base: Airtable rejects a field name that differs from another only by letter case. The key marks it `field_exists = no`.
- **0-byte attachments are rejected** (`BAD_REQUEST`). `empty.txt` is kept as a deliberate negative test.
- **Odd filenames** (Unicode, symbols, no extension, dotfile, 255 characters) were stored unchanged.
- **CSV import retyped fields.** Importing into existing tables changed some types (for example `Items.Name` to a select, `SalesItems` prices to number) and probably created blank select choices on six fields. It also, once, left the last 249 `SalesItems.purchaseId` link cells empty. This is a single observation with an unknown cause; a second large linked table would help investigate it. Re-check types and link counts after any import.
- **Tables cannot be deleted by API**, so teardown removes records only (including hand-uploaded files).

### Hand-made parts (intentional)
- **Product photos.** Twenty product images were generated with Gemini to suit the luxury-clothing theme and uploaded by hand to `Items.Product Photo`, then the uploader appended its own file. Twenty cells therefore hold two files each (the photo at position 1). They are the one exception to the "SAMPLE" watermark; `out/live_attachments.csv` records the true cell contents.
- **The over-5 MB file** (`over_5mb.png`) is uploaded through the Airtable UI because it exceeds the API limit.
- **Items, Purchase and SalesItems** were loaded by CSV import, which saves API calls and exercises the app's import path.

### Known gaps
- No wall-clock throughput benchmark is recorded yet; `seed_calls.log` holds method, path and status only.
- `compare.py` does not check attachments; `live_attachments.csv` and `expected_attachments.csv` are provided for that comparison.
- The 20 mixed attachment cells have no merged entry in the answer key.

## 7. Repository layout
```
README.md  LICENSE  .gitignore  seed_config.example.json     (root)
seed_config.json  seed_log.json  seed_calls.log               (root; local, gitignored)
src/       all Python (run everything from the repo root, e.g. python src/seed.py ...)
docs/      ASSUMPTIONS.md  CHANGELOG_SCHEMA.md  COVERAGE.md
legacy/    the six original CSVs (inputs)
out/       everything generated (gitignored)
```

| File in `src/` | Purpose |
|---|---|
| `fw_*.py`, `generate.py` | schema DSL, data, files, link graph, profile; `generate.py` writes `out/` |
| `verify.py` | offline self-check (2,025 checks) |
| `seed.py` | upload, plus `--adopt`, `--adopt-links` and `--check-attachments` |
| `verify_live_schema.py` | diff live schema against expected (`--dump` saves the live schema) |
| `show_failures.py`, `probe_link.py` | summarise logged failures; probe one failing link field |
| `teardown.py`, `burst_429.py` | reset records; trigger a 429 on purpose |
| `compare.py` | compare a profile export with the answer key |

`docs/COVERAGE.md` maps each edge case to the table that contains it; `docs/ASSUMPTIONS.md` holds the full list of assumptions and live observations; `docs/CHANGELOG_SCHEMA.md` tracks schema changes.

## 8. Reproducing the run

All commands run from the repo root.

1. `python src/generate.py` then `python src/verify.py` (offline, no token needed).
2. Create two empty bases in a trial workspace, with names beginning **TRIAL** (or `python src/seed.py --phase create-bases`, which needs `workspace_id`).
3. `cp seed_config.example.json seed_config.json`; fill in base IDs and a **write** token (scopes: data.records:read/write, schema.bases:read/write).
4. `python src/seed.py --dry-run --phase all` (request counts only), then `--phase preflight`.
5. `python src/seed.py --phase schema`. Turn off "Allow linking to multiple records" on the fields `verify_live_schema.py` lists as `SINGLE-LINK PREF`, and create the Button field by hand. **Never delete an inverse link field.** Repeat `verify_live_schema.py` until only the known leftovers remain.
6. Optional: load some tables by CSV import (parents before children, under 1,000 rows per import, link columns unmapped when the target is empty), then `python src/seed.py --adopt "Table" ... [--adopt-links] --only-base ff_main`.
7. `python src/seed.py --phase records`, then `--phase links`, then `--phase attachments`. If you uploaded attachments by hand, run `--check-attachments` first (`--accept-existing` leaves non-empty cells alone; leave it off to test that uploads append). Upload `out/attachments/manual_upload/*` through the app.
8. Verify: `python src/show_failures.py` (0 failed batches; only `Naming Edge Cases.total` expected under field creation), `--adopt <tables with links> --adopt-links` (all rows match), `--check-attachments` (only `empty.txt` missing).
9. Optional: `python src/burst_429.py --yes` to trigger and observe the rate limit.
10. Reset: `python src/teardown.py --yes` (records only). Revoke the write token when testing is finished.

## 9. Provenance and disclosure

- **Origin.** This is a personal, MIT-licensed project that reflects my interest in data-transfer and project-management tooling, alongside my graduate work as a Master's candidate in Computer Science (Data Science emphasis) at UMKC.
- **The fictional business.** The idea came from an Executive MBA case discussion of The Men's Wearhouse (Pfeffer, 2004). I invented "Fictional Fashionwear" as a luxury retailer and blended two UMKC courses to design the data: Principles of Big Data (COMP-SCI 5540) and Leadership and Organizations (MGT 5557). It has no affiliation with The Men's Wearhouse or any other real company.
- **AI assistance.** The code and documentation were developed with Claude Code as a pair-programming assistant; commits carry a co-author trailer. The design goals, live testing in Airtable, decisions and corrections are mine. The product photos were generated with Gemini.
- **Reference.** Pfeffer, J. (2004). *The Men's Wearhouse: Success in a declining industry* (Revised ed.) (Case No. HR-5). Stanford Graduate School of Business.
