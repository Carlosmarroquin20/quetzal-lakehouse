# Known limitations

[Back to the README](../README.md)

## Storage

- The store runs as a single node without replication. It is a local
  development stand-in for S3, not a production deployment.
- The image also starts components this project does not use (a filer UI, an
  admin UI, an Iceberg REST catalog). Their ports are not published to the
  host.

## Sources and ingestion

- Only the US dollar is ingested.
- Overwriting a partition discards what it held before. If a source revises
  a past value, the previous one is not kept.
- The two objects of a partition are written one after the other, not
  atomically. A failure between them leaves the original file newer than the
  Parquet file until the job runs again.
- The exchange rate source repeats the last published rate on days without a
  new one, such as weekends. Bronze and silver keep those rows as they come.
- Guatecompras rewrites the files of recent months every day. On 2026-10-14
  all 22 months from January 2025 had a new checksum while January 2020 did
  not, so the daily run downloads about 0.7 GB; the checksum only saves the
  downloads of a second run on the same day.
- The budget depends on someone downloading the workbooks. The only
  reminder is the freshness alert, 35 days after the last new workbook, and
  it reaches nobody when the notifications are not set up.
- The date up to which the current year's budget is accumulated is not in
  the workbook. Only the day of the download is known, in the file name.
- Loading an older workbook of a year after a newer one replaces the newer
  one; the job cannot tell which is more recent.
- Only the expenditure of the central government is loaded: not its income,
  and not the budgets of decentralized entities or municipalities. Those
  entities carry the names buyers use in Guatecompras, not official names.

## Models

- Of a contracting process only the tender, its awards, the buyer and the
  suppliers are modelled. Bids, items, documents and contracts stay in bronze,
  and processes that were never awarded do not reach gold.
- 487 suppliers have no legal type, so whether they are natural persons is
  unknown.
- Silver is written in place, so a failed test there reports a problem in a
  table that is already written; only gold is published after the tests.
- Publishing copies every gold table, so gold is written twice per run.
- The catalog is a single Postgres without replication. Losing it loses
  which files make up each table until a dump is restored, and changes since
  the last dump are lost (see Backups).
- The plain Parquet files the first versions wrote are still in the silver
  and gold buckets, outside `ducklake/`. Nothing reads them any more; they can
  be deleted by hand.
- The dashboard and the digest need the catalog running to read gold.
- DuckLake is young; its catalog format may change between DuckDB releases.
- `dim_date` does not mark public holidays.
- `dim_currency` is maintained by hand from a seed file.
- The hash keys make the fact tables unreadable without joining the
  dimensions.
- The published documentation has no catalog: column types and row counts
  appear only in the local `docs` service, after a build.
- The exposure of the dashboard links to `localhost`, so on the published
  site that link only works on a machine running the project.
- Freshness warnings, short of the error threshold, only show in the
  Airflow log; only errors raise an alert.

## Governance

- Silver keeps personal data in the clear. Only bucket permissions protect
  it, and the administrator key can read everything.
- Dev reads the real bronze, personal data included. Dev only differs from
  prod in where it writes.
- Changing a pseudonymization key changes every supplier key of that
  environment; nothing keeps the old ones.
- Permissions are per bucket and per role, not per column or per person.

## Orchestration

- When an ingestion fails, the build still runs on what bronze holds, so
  gold that day may mix sources refreshed today with one refreshed earlier.
  The run is marked failed and the failure alert names the task.
- A Guatecompras month the source keeps serving broken stays at its last good
  version until the source fixes it. The failure alert repeats every day it
  lasts; the freshness check does not notice it, because it looks at the
  latest load of the whole source.
- Airflow runs only while this machine and Docker are on. A day it misses is
  not run later; the next run refreshes everything anyway.
- The Airflow interface has no login. It is published on loopback only, for
  local development.
- Airflow reaches Docker through a proxy that refuses exec, builds,
  volumes, networks and system calls, but still lets it create containers,
  and a container can be created with the host mounted. Untrusted DAGs must
  not run on this stack.
- When Airflow kills a task, the operator stops and removes its container.
  If the scheduler itself dies before it can, the container stays; it is
  found by its label (see the getting started guide).
- The DAG tests check how the DAG is built, not a run: they load it in
  Airflow without starting any task. Runs were checked end to end by hand.
- With the scheduler running, `airflow tasks test` creates a temporary run,
  and the scheduler starts that run's other ready tasks too, such as the
  ingestion. Pause the DAG before testing one task by hand.
- Everything shares one virtual machine of Docker Desktop. During one run a
  dbt build starved the Airflow scheduler for 36 seconds, Airflow declared it
  dead and killed the dbt task, and the retry succeeded. The scheduler now
  gets 120 seconds before being declared dead; that has not been proven to
  prevent it. Docker Desktop itself hung three times during development and
  had to be restarted.

## Dashboard

- The dashboard has no login. Like the other interfaces, it is published on
  loopback only.
- The dashboard caches results for an hour, so after a build it can show the
  previous data for up to an hour. Restarting it clears the cache.
- The awards page ranks legal entities only; the suppliers awarded the most
  overall may include natural persons, which it shows only as a group.
- The dashboard's pages have no automated tests; its queries do. The pages
  were checked by opening them against the data of 2026-10-14.

## Notifications

- Delivery through a real Telegram bot and a Gmail account was checked for
  the digest only. The failure alert, a refused message and the error
  workflow were checked against stand-ins for Telegram and an SMTP server.
- If n8n is down, nothing is reported: the digest task fails after its
  retries, and the alert about that failure cannot reach n8n either. Only
  the Airflow interface shows it.
- The error workflow cannot report when the recipients are not set, or when
  both channels fail; the failed execution is only listed in n8n.
- A failure alert is sent per failed task, so a run where the three
  ingestion tasks fail sends three alerts.
- That Airflow calls the failure callback once a task has used up its
  retries was not seen in a real run; the callback was called inside the
  Airflow scheduler and reached n8n.
- The digest counts the awards dated the day before the run that
  Guatecompras had published when the run loaded them, which may be fewer
  than the source holds later. The exchange rate it reports is the latest
  in gold up to that day.
- Any n8n workflow can read every environment variable of the n8n
  container, the encryption key included, because the workflows read their
  settings from there.
- One secret protects both webhooks. Changing it means changing `.env` and
  the n8n credential together.
- A workflow changed in the n8n interface stays different from the
  repository until it is exported and normalized by hand, and running the
  import script replaces such changes.
- n8n runs its code task runner inside its own container, a mode n8n has
  deprecated in favour of a separate runner, and it cannot run Python in
  code nodes.

## AWS

- The Terraform configuration has never been applied to an AWS account, only
  to an emulator. AWS may reject something the emulator accepted.
- The emulator does not enforce IAM policies, so the limits of each role
  were only checked against SeaweedFS, which enforces the same rules.
- The emulator does not keep bucket tags set through S3 Control, so a plan
  right after an apply proposes to add them again, along with the bucket
  policies that depend on the buckets.
- Only storage and permissions are written. Images, scheduled tasks, the
  dashboard service and secrets are described in docs/aws.md but not coded.
- Terraform state is a local file; a shared deployment needs remote state
  with locking.

## Continuous integration

- CI does not run `dbt build`: that needs the sources in an object store.
  The data tests run only with a build, locally or in Airflow.
- The scans only know published vulnerabilities. The image scan covers
  the four project images; the third-party images (Airflow, Postgres, n8n,
  SeaweedFS and the others) are not scanned, only kept current by
  Dependabot.
- The image scan ignores vulnerabilities without a fix, which cannot be acted
  on but still exist.
- gitleaks and Trivy, run by the CI workflow, are pinned by version tag
  only, and nothing updates them; a new release has to be adopted by hand.
- A pinned digest also freezes the operating system patches of the base
  image until Dependabot proposes the next one: it checks weekly and waits
  seven days after a release, so up to about two weeks.

## Backups

- Only the catalogs are backed up. The data files are protected by the
  versioning of bronze and by the 30 days of versions in silver and gold, not
  by a copy elsewhere.
- Locally, the backups live in the same object store, on the same disk, as
  the data. Losing the machine loses both; in AWS the bucket could be in
  another region or account.
- Restoring is a manual procedure, tried once on 2026-10-23.
