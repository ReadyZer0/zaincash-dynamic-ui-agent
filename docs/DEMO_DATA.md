# Synthetic demo data

All names, account identifiers, balances, bills, transaction references, dates,
and QR payloads below are fictional. They are local presentation fixtures; no
provider, external model, device, or payment service is called.

## Profiles

| Profile | Available balance | Saved contact | Saved bill | Read-only history fixtures |
| --- | ---: | --- | --- | --- |
| أمينة التجريبية (Amina) | 150,000 IQD | علي ضياء `0770•••483`; علي محمد `0771•••917` | Home electricity `BILL••2841`, 45,000 IQD | Transfer to Ali Diaa, 12,500 IQD; transfer to Ali Mohammed, 25,000 IQD; mock electricity, 45,000 IQD |
| حسن التجريبي (Hassan) | 87,500 IQD | أمينة `0770•••001` | Mock mobile `POST••1640`, 18,000 IQD | Mock mobile, 18,000 IQD; transfer to Amina, 9,500 IQD; mock mobile, 10,000 IQD |

Fixture dates are September 2026. On a fresh database, the listed historical
debits imply illustrative opening balances of 232,500 IQD for Amina and
125,000 IQD for Hassan. Seeding inserts these as `synthetic_history_fixture`
records for read-only history display and does not debit the seeded account.
Subsequent user-confirmed mock transactions use the normal mock ledger path.
Seed operations are idempotent; existing local databases keep their balances.

## Receive QR

The app encodes `MOCK-RECEIVE|AMINA|NOT-PAYABLE` or
`MOCK-RECEIVE|HASSAN|NOT-PAYABLE` as a local QR Model 2 symbol (version 2-L).
The visible card labels the symbol as demo-only and not payable. It is not a
payment request, deep link, provider QR, or an integration with the original app.

## Clean demo database

The app seeds the profiles at startup. To keep existing local demo state,
continue using the configured database. For a separate clean run, set
`READY_DB_PATH` to a new local SQLite path before starting `server.py`; do not
place real user or wallet records in the demo database.
