# Schema change log (Step 0 defects and every change)

## Defects found in the supplied schemas and fixes
| # | Defect | Fix |
|---|---|---|
| 1 | `Purchase.Total` rollup references a missing field | Rollup `Total` now sums `Price` of SalesItems through the `Line Items` link (field exists); recomputed values match the original data (see `out/reports/legacy_check.txt`) |
| 2 | `SalesItems.primaryFieldId` missing | Added a primary field (`line` key, unique per row) |
| 3 | No inverse link fields anywhere (Airtable always creates them) | Every link now has a named inverse field. One-way links were tried and dropped: neither the API nor the app can create them, and deleting an inverse converts the other side to text |
| 4 | Repeated choice IDs across select fields | Choice IDs made unique per field (deterministic) |
| 5 | Dependency graph was a DAG, so it never stressed ordering | Added cycles (2- and 3-table), self-links, both-single and many-to-many pairs, a 6-level chain, a diamond, a link-free table |
| 6 | Primary values not unique in places (e.g. repeated names) | Primary values unique per table so CSV import can resolve links by text |
| 7 | Legacy columns holding JSON-list strings (`salesPersonId`) as text | Becomes a real multi-value link to Sales Persons with inverse `Sold Purchases` (values preserved as the link targets). Neither side is single, so Purchase and Sales Persons form a 2-table cycle in resolve mode |
| 8 | Link fields in legacy data are plain id text | Converted to real link fields resolved by the target's primary value |
| 9 | Margin formula divides by zero when Price = 0 | Original `Margin` kept (still errors on Price 0 by design); `Margin Safe` variant added (BLANK when Price = 0); Price 0 rows itm_099/100 exercise both |

Defects 7-9 are judgment calls; see ASSUMPTIONS.md.

## Preserved
All original ~20 rows per legacy table (values and keys) are kept; no existing table or field was renamed. `verify.py` checks this.

## Added (full list in out/schema and COVERAGE.md)
- ff_main: 27 new tables; legacy tables grew (Retail Locations 60, Sales Persons 80, Clients 150, Items 100, Purchase 200, SalesItems 1,250).
- Field-type coverage (Field Type Showcase, 32 fields), data-quality lab (29 fields), naming edge cases (30 fields), Attachment Lab, Quota Stress Wide (124 fields: 25+ long text, 20+ formulas, 35+ links) with six Quota Parent tables.
- ff_ops: second base with 6 tables whose names collide with ff_main (Retail Locations, Items, Style Glossary).
- Select choices include a typecast-only value (`Zeta-New`).
