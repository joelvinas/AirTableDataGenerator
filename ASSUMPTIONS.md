# Assumptions and open questions
Questions were not asked up front; these are the defaults taken. Tell me which to change.

## Open questions (with the default used)
1. Keep the 20 legacy `@monarchmenswear.com` emails? Default: yes (exact preservation). `--sanitize-legacy` replaces them.
2. Plan/record cap? Default 1,250-row large table. Per-base caps (fast.io summary, Oct 2026): Free 1,000, Team 50,000, Business 125,000, Enterprise Scale 500,000 records. Free also allows only 1,000 API calls per workspace per month, so seeding needs a paid trial.
3. Real collaborators? Default: none; supply `collaborator_emails` (workspace members) or collaborator cells are skipped.
4. Convert legacy id-text columns to real links? Default: yes, in place as real link fields with the same values (judgment call).

## Load-order rules (inferred from your two sample reports)
Child -> parent edge for each link field A -> B (A != B); self-links ignored for ordering; strongly-connected components load as one step; members ordered by (table name, table ID); Kahn's algorithm with the same tie-break; depth = longest parent chain at component level, parent lists include cycle partners. Resolve mode: for an inverse pair where exactly one side prefers a single record, that table is the child. Both-single or neither-single pairs stay a cycle. Literal mode treats every pair as a 2-cycle, so with inverses everywhere it collapses into very large cycles (expected_load_order_literal.csv). Only the resolve-mode file matches the sample reports closely; confirm literal mode with your tool.

## Airtable API facts used (docs, checked 2026-11-08)
10 records per create/update; 5 req/s per base; 50 req/s per token; 429 -> wait 30 s; attachment upload via content.airtable.com `uploadAttachment` (base64, 5 MB); create-base endpoint exists. Creating a link field takes only `linkedTableId`: the inverse is auto-created and single-record preference cannot be set, hence the manual steps.

## Unverified (the seed script tries and logs)
Creating formula/rollup/lookup/count/created/modified fields via API; very long or odd field names; 255-char or empty attachment files; whether attachment filenames get rewritten; link-array order; formula error shape; whether whitespace-only strings are trimmed; autonumber assumes one uninterrupted seed run. Failures land in `seed_log.json` -> `failed_fields`; create those fields by hand.

## Other limits
- Duplicate link ids in one cell cannot persist (Airtable collapses them); the key records the collapsed result.
- Button fields have no API creation; observed fields only have predictable row_count and null_count.
- Tables cannot be deleted by API, so teardown removes records only.
- Answer key uses placeholder IDs; match on (base, table, field).
- Seeding refuses any base not named TRIAL*. The write token lives only in `seed_config.json`; the migrator keeps its own read-only token.
