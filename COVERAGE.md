# Coverage checklist (edge case -> where it lives)
Names are tables in `ff_main` unless noted. Row IDs are primary-field values. The answer key lists exact values per field.

## Link topologies
| Case | Where |
|---|---|
| 2-table cycle | Retail Locations <-> Store Managers |
| 3-table cycle | Collections -> Designers -> Ateliers -> Collections |
| Link from outside into a cycle | Items.Collection (Items sits at depth 1) |
| Self-link (clean) | Clients.Referred By, Employees.Reports To; emp_001 links to itself |
| Mutual self-links | cli_022 <-> cli_023, emp_050 <-> emp_051; cli_021 self-referral |
| Many-to-many pair (stays a cycle in resolve mode) | Lookbooks <-> Style Tags; Purchase.salesPersonId <-> Sales Persons.Sold Purchases (up to 2 people per purchase) |
| Single-record hint resolves a pair | Campaigns / Campaign Tasks (Campaign Tasks depth 1) |
| Both sides single (ambiguous cycle) | Suppliers <-> Supplier Contracts |
| Two links, same target table | Special Orders.Billing Store + Shipping Store -> Retail Locations |
| Diamond-like shape | Purchase and Sales Persons (a 2-table cycle) both lead to Retail Locations; Purchase also links to Clients |
| Chain depth 6 | Clients -> Purchase -> SalesItems -> Returns -> Return Inspections -> Restock Orders |
| No links | Style Glossary |
| Name collisions across bases | ff_ops Retail Locations, Items, Style Glossary |

## Record-level link cases
| Case | Where |
|---|---|
| Empty link cells | Data Quality Lab, Clients (no referrer), Purchase |
| Cell with 100+ links | Lookbooks 110-link cell; pur_200 with 110 SalesItems |
| Duplicate links in one cell (collapse) | RAW_DUPLICATE_LINKS_COLLAPSED flag in expected_profile |
| Forward-only seeded, inverse derived | every inverse field (value_source = derived_inverse) |

## Field types / values
| Case | Where |
|---|---|
| Every API-creatable field type | Field Type Showcase |
| Null patterns: always empty, always filled, mixed, empty string, empty array, rating 0, checkbox false/missing, whitespace-only | Data Quality Lab (field names say which) |
| Numeric edges: 0, negatives, large, precision rounding | Data Quality Lab, Items (Price 0 for itm_099/100) |
| Formula error value | Margin / Margin Safe on Price = 0 |
| Rollup over no links = 0; lookup over no links | Purchase, Showcase |
| Typecast select adds a choice | Showcase 'Zeta-New' |
| Observed fields (created/modified/createdBy/button) | Showcase |
| Names: duplicates ignoring case, spaces, emoji, quotes, commas, very long | Naming Edge Cases (30 fields; unsupported names flagged `NAME_MAY_BE_REJECTED`) |
| Quota stress | Quota Stress Wide (124 fields), Quota Parent 1-6 |
| Large table | SalesItems (1,250, configurable) |
| Dates / date-times, time zones, extremes | Showcase, Data Quality Lab |
| Collaborators | Showcase (needs `collaborator_emails` in seed_config.json) |

## Attachments (Attachment Lab, `Files` field; plus ID Photo etc. on Sales Persons)
tiny (0-byte try, 27-37 B), small PNG/PDF/SVG/TXT/CSV, medium 300 KB and 1.5 MB, 4.5 MB (exact 4,500,000 B), over 5 MB (5,453,342 B, manual upload), same filename in several records (att_05/att_07), same filename twice in one cell, identical checksums across records (copy_a/b/c.png), odd filenames (unicode, symbols, no extension, dotfile, 255 chars), uppercase extension, mismatched extension/MIME (looks_like.jpg), cells of 0, 1 and 3+ files (many_00.txt cell). Optional JPEG if Pillow is present.
