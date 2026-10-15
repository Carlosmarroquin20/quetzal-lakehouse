# Data quality

[Back to the README](../README.md)

Each source was profiled before its models were written. Silver keeps the
values the source published, and the tests encode what the profile found, so
the build fails on anything new instead of on what is already known.

## Exchange rates

Profile of the full history (13,486 rows, 1989-11-06 to 2026-10-13):

| Finding | How it is handled |
|---|---|
| Five calendar days have no record: 2000-04-02, 2000-05-01, 2001-09-02, 2004-03-06 and 2004-03-07. | They are listed in the seed `banguat_known_missing_dates`. One test fails on any other missing day; another fails if a listed day appears in the data, so the list cannot go stale. |
| On 85 days between 1989-11-16 and 1991-04-09 the selling rate is below the buying rate. | Kept as published. A test requires the selling rate to be at least the buying rate from 1992 on. |
| Buying and selling rates differ on every day up to 2006-12-01 and are equal on every day since 2006-12-02. | A test requires both rates to be equal from 2006-12-02 on. If they diverge again, the meaning of the fields has changed. |

The remaining tests check that no column is null, that `rate_date` is unique,
that the currency is `USD`, that both rates fall between 1 and 20 quetzales
(the historical range is 2.78 to 8.39), and that silver has exactly as many
rows as bronze.

In gold, `dim_date` has no missing days, the fact table has exactly one row
per currency and calendar day, the days it fills in are exactly the five days
listed as missing, and `reference_rate` always lies between the buying and
selling rates.

## Contracting processes

Profile of the processes published from January 2025 to October 2026
(638,884 records, 4.9 GB of JSON):

| Finding | How it is handled |
|---|---|
| Six processes are written twice in their monthly file, with identical content. | Silver keeps one row per process, the most recently updated. Tests require process, tender and award identifiers to be unique. |
| 93 processes have no status. All of them are detailed as "No adjudicado". | Kept. A test fails if a status is missing with any other detail. |
| 4,481 processes (0.7 %) do not list the budget entity of their buyer. They belong to 119 buyers that never list it. | Kept with an empty entity code. A test fails if the share goes above 2 %. |
| The entity code does not identify a buyer: code 11130016 appears with 25 different buyer names. | The dimension is built per buyer, identified by its tax number, with the entity code as an attribute. No buyer has more than one entity code. |
| 145 suppliers appear under more than one spelling of their name. | The most recent name is kept. |
| 289 awards name a supplier that is missing from the list of parties of its process. | Suppliers are read from the awards, so none is lost. Their legal type, which only the list of parties gives, is empty. |
| Timestamps carry the offset of Guatemala, and the engine runs in UTC inside its container. Taking the engine's date would put 28,201 awards on the wrong day. | Dates are converted explicitly to the calendar day in Guatemala. A unit test covers a late evening case. |
| Every award is in quetzales. | The currency must exist in the `currencies` seed, and a gold test fails if an award cannot be expressed in quetzales. |
| 25,942 awards are cancelled, and 51 have an amount of zero. | Kept as published. Cancelled awards are flagged in gold. |

The remaining tests check keys, required columns, code lists, that amounts
are not negative, that every award belongs to a process and to a supplier,
and that every award has exactly one supplier.

In gold, every key of `fct_awards` exists in its dimension, the fact table
has the same number of rows and the same total amount as the awards in
silver, and every award has an amount in quetzales and in dollars. That last
test also fails when exchange rates are older than the awards.

## Budget execution

Profile of the workbooks of 2025 (173,054 lines) and 2026 (156,202 lines):

| Finding | How it is handled |
|---|---|
| Both years have the same 42 columns, and the fifteen classification codes identify each line. | The ingestion job rejects a workbook whose header differs in any way. Silver tests that the fifteen codes and the year are unique. |
| The current budget equals the approved budget plus its changes on every line, and the amount paid never exceeds the amount accrued. | Both rules are tests. |
| 13 lines of 2025 have more accrued than committed, and 1,469 lines of 2026 (0.9 %) have more committed than the current budget. | Kept as published. A test fails if either share grows past its limit (0.1 % and 2 %). |
| Codes below the entity (executing unit, program and so on) repeat across entities with different meanings. | The program dimension is keyed by the whole path, starting with the entity. |

Silver also checks that every bronze line arrives, that the entity code has
eight digits and that amounts are not negative where they cannot be. In gold,
every key of `fct_budget_execution` exists in its dimension and the totals of
each year match silver.

## Unit tests

Eight unit tests run the model logic on small invented inputs: the conversion
of source text to typed values, for exchange rates and for the budget, a
process repeated in the source, a process with several awards and one with
none, a gap in the exchange rates, the conversion of an award with the rate of
its day, the choice of an entity's name, and the masking of natural persons.

dbt runs a model's unit tests before building it, so a logic error that a
unit test catches stops the build before the table is overwritten.
