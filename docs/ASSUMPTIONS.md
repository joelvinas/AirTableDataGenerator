# Assumptions and open questions
Questions were not asked up front; these are the defaults taken. Tell me which to change.

## Open questions (with the default used)
1. The 20 legacy emails once used `@monarchmenswear.com`, and item `itm_005` once had a real brand name in its Name. The owner edited the legacy CSVs, the generated Items.csv and the live Items table by hand (emails to `example.com`; `itm_005` to "Heritage Wool Trench Coat"). `--sanitize-legacy` applies the email replacement if you start from the unedited originals.
2. Plan/record cap? Default 1,250-row large table. Per-base caps (fast.io summary, Oct 2026): Free 1,000, Team 50,000, Business 125,000, Enterprise Scale 500,000 records. Free also allows only 1,000 API calls per workspace per month, so seeding needs a paid trial.
3. Real collaborators? Default: none; supply `collaborator_emails` (workspace members) or collaborator cells are skipped. Not yet checked against your base.
4. Convert legacy id-text columns to real links? Default: yes, in place as real link fields with the same values (judgment call).

## Load-order rules (inferred from your two sample reports)
Child -> parent edge for each link field A -> B (A != B); self-links ignored for ordering; strongly-connected components load as one step; members ordered by (table name, table ID); Kahn's algorithm with the same tie-break; depth = longest parent chain at component level, parent lists include cycle partners. Resolve mode: for an inverse pair where exactly one side prefers a single record, that table is the child. Both-single or neither-single pairs stay a cycle. Literal mode treats every pair as a 2-cycle, so with inverses everywhere it collapses into very large cycles (expected_load_order_literal.csv). Only the resolve-mode file matches the sample reports closely; confirm literal mode with your tool.

## Airtable API facts used (docs, checked 2026-11-08)
10 records per create/update; 5 req/s per base; 50 req/s per token; 429 -> wait 30 s; attachment upload via content.airtable.com `uploadAttachment` (base64, 5 MB); create-base endpoint exists. Creating a link field takes only `linkedTableId`: the inverse is auto-created and single-record preference cannot be set, hence the manual toggles. One-way links are not possible: the app's new-field dialog has no option to skip the inverse, and deleting one side of a pair converts the other side to single line text (observed). Every link therefore has an inverse; the answer key reflects that.

## Observed on the live trial base (2026-11-08)
- One-way links cannot be created, and deleting one side of a link pair converts the other side to single line text. Every link has an inverse.
- API creation options: rollups need `formula` (`SUM(values)`), createdTime takes no options, lastModifiedTime takes only `referencedFieldIds`.
- A field name that differs only by case from another (`Naming Edge Cases.total`) is rejected, so the field does not exist. The key lists it with `field_exists = no`.
- Uploading to an attachment cell appends to it and keeps upload order. A hand-uploaded `.jfif` (image/jpeg, ~2.2 MB) stayed at position 1 with ours at position 2.
- An empty (0-byte) attachment is rejected (`BAD_REQUEST`), so its cell stays empty. The key lists it as `seed_method = rejected`.
- Odd filenames (unicode, symbols, no extension, dotfile, 255 characters) were stored unchanged and matched by name and size.
- A CSV import into existing tables changed some field types (for example Items.Name to a select, SalesItems prices to number) and, once, left the last 249 rows' link cells empty. That is one observation; the cause is unknown. Check types and link counts after any import.
- Six select fields have one or two more choices than the schema (Retail Locations.Freestanding/Mall, Items.Style Interest Tags names, Purchase.Channel, Style Glossary.Language, Data Quality Lab.Multi Select Mix and Typecast Select). Probably blank choices created by the import; not confirmed. They are left as they are, and `Typecast Select` also gains `Zeta-New` by design.

## Still unverified (to be settled by the migrator's extraction)
Link-array order inside a cell; the shape of a formula error value; whether whitespace-only strings are trimmed; autonumber assumes one uninterrupted seed run. Fields flagged for these in `expected_profile.csv` show as `soft` lines in `compare.py`.

## Other limits
- Duplicate link ids in one cell cannot persist (Airtable collapses them); the key records the collapsed result.
- Button fields have no API creation (create `Field Type Showcase.Button` by hand); observed fields only have predictable row_count and null_count.
- Tables cannot be deleted by API, so teardown removes records only.
- Answer key uses placeholder IDs; match on (base, table, field).
- Seeding refuses any base not named TRIAL*. The write token lives only in `seed_config.json`; the migrator keeps its own read-only token.
- Hand-uploaded files (for example the 20 Items photos) are your own images and carry no "SAMPLE" mark; keep `out/` out of git.
