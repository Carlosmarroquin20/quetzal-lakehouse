# Design decisions

[Back to the README](../README.md)

Each decision is stated with the alternatives that were rejected and why.
The decisions about personal data, roles, environments and lineage are in
[Governance](governance.md#design-decisions).

## Storage

**Object storage behind the S3 API instead of a local folder.** A folder would
be simpler, but every reader and writer would then depend on file paths.
Talking to an S3 endpoint from the start means that moving to AWS S3 changes
configuration (endpoint and credentials), not code.

**SeaweedFS instead of MinIO.** MinIO was the original choice. When this stack
was written (October 2026) the MinIO community repository was archived and its
official images could no longer be pulled from Docker Hub, so a compose file
based on them would not start. SeaweedFS is Apache-2.0 licensed, actively
maintained, and runs as a single container. Two alternatives were rejected:
RustFS, because its first stable release was less than a month old, and a
community fork of MinIO, because it is a third-party build of code its
original authors abandoned.

**One bucket per layer.** Each layer gets its own bucket rather than a prefix
inside a shared one, so access rules and retention can differ per layer: for
example, ingestion may only write to bronze and a dashboard may only read from
gold. A bucket is created when its layer is built.

**Pinned image tag.** The image starts several components with defaults that
may change between releases. Pinning `4.48` keeps `docker compose up`
reproducible.

**Port published on loopback only.** The S3 port is bound to `127.0.0.1`, so
the store is reachable from the development machine and not from the network.

**Project-specific variable names in `.env`.** The store's key pair is read
from `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY`, not from the standard
`AWS_*` names. Compose gives shell variables priority over `.env`, so reusing
the standard names could silently pass real AWS credentials from a developer's
shell into the local container.

## Ingestion

**A period of the source is the unit of work.** A job requests one whole
period (a year of exchange rates, a month of contracting processes), stores
it under one partition with fixed object names, and replaces that partition
on every run. Because what is fetched, what is stored and what is overwritten
are the same thing, running a job twice cannot duplicate data and needs no
record of previous runs. The alternative, loading only what was added since
the last run, was rejected: it needs stored state and appends rows, which is
exactly what produces duplicates when a run is retried.

**The partition follows the source.** Exchange rates have about one record
per day, so daily or monthly partitions would create thousands or hundreds of
files with a handful of rows each; yearly partitions give 38 files of about
365 rows. Contracting processes are published as one file per month of tender
publication, so the month is the partition. Partitioning by ingestion date
was rejected for both: it keeps every version the source ever returned, but
the same record would appear in many partitions and every reader would have
to deduplicate.

**Original file and Parquet copy side by side.** The original is what the
source actually sent, so the Parquet files can be rebuilt if the parser turns
out to be wrong, without calling the source again. The Parquet copy exists
because DuckDB and dbt read it directly and do not read XML or zip files.

**Bronze stores text, not types.** Dates and numbers are kept as the source
wrote them, and a contracting process is kept as the JSON text of its record.
Converting or flattening them is a transformation that can fail, and failures
belong in the silver layer, where they are tested and visible. Flattening the
JSON at ingestion was rejected for the same reason: a change in the structure
of the source would break the load instead of a test.

**Large files are read as a stream.** A month of contracting processes is up
to 260 MB of JSON. The job reads it in chunks and cuts it into records, so
the document is never held in memory as a whole, and each record is stored as
the exact text of the file rather than a re-encoded copy.

**Downloads are checked before anything is overwritten.** An exchange rate
response is rejected if it is not valid XML, if the number of records does
not match the count the service declares, if it is empty, or if it contains
dates from another year. A monthly file of contracting processes is rejected
if its SHA-256 differs from the one the source publishes, if it holds records
of another month, or if it is empty while bronze already has that month. A
rejected download leaves the stored partition untouched, so an outage at the
source cannot erase data that was already loaded.

**A month the source has not changed is skipped.** Guatecompras rewrites its
files as processes move forward, including those of past months, and
publishes a checksum for each. The job stores that checksum with the Parquet
object and downloads a month only when the published checksum differs. The
checksum goes on the object written last: if a run dies between the two
writes, the month does not look up to date and the next run loads it again.
This is not a record of previous runs; it is a comparison between the source
and what is stored.

**Retries are left to whoever runs the job.** Only connection failures are
retried in-process. Any other error stops the run with a non-zero exit code.
Since re-running is always safe, retry policy can live in the scheduler
instead of being reimplemented inside each job.

**Hand-written SOAP request.** The request is a ten-line XML template. A SOAP
library such as zeep would add a large dependency to generate the same text.

**A source that blocks automated clients is downloaded by hand.** The MINFIN
portal answers the pipeline's HTTP client with a bot challenge. Getting past
it by imitating a browser would be working around a protection the publisher
chose, and a pipeline that depends on that can break any day. So a person
downloads the workbooks in a browser into `landing/minfin/`, which Compose
mounts read-only into the ingestion container, and everything after that is
automated. The folder is ignored by git.

**The fiscal year comes from the content, not the file name.** Whoever
downloads a workbook names it, so the name cannot be trusted. The job reads
the `ejercicio` column, rejects a workbook that mixes years, and refuses to
load two files of the same year at once rather than guess which is the right
one. Every file is read and checked before anything is written.

**Only the latest workbook of each year is kept.** A new download of the
current year replaces the previous one, like every other partition. Keeping
each download as a snapshot was rejected: with downloads made by hand the
snapshots would fall on arbitrary dates, and every consumer would have to
pick one.

**A workbook bronze already holds is not written again.** The job computes
the SHA-256 of each workbook and compares it with the one stored with the
Parquet object, as the contracting processes job does with the checksum its
source publishes. The landing folder is never modified: deleting files there
is left to the person who put them.

**One image, jobs selected by name.** The three jobs live in one Python
package and one image; the first argument chooses the job. They share the
storage client, the HTTP client and the clock.

**Locked dependencies, fixed runtime.** `uv.lock` records the exact version
of every dependency. The job image installs from it using a fixed Python
minor version and a pinned uv version, so it does not depend on what is
installed on the machine that builds it.

## Transformation

**Silver is Parquet in its own bucket; DuckDB is only the engine.** dbt writes
each model to the silver bucket and DuckDB keeps nothing but a view over the
file. Storage stays separate from compute: any engine that reads Parquet can
use silver, and the DuckDB database file is disposable. Keeping the tables
inside a DuckDB file was rejected because the data would leave the object
store and only DuckDB could read it. A table format such as Iceberg was left
out for now: it would add a catalog before there is a single model to manage.

**Source anomalies are kept and documented, not fixed.** Silver changes types,
names and shape, never values. Missing days are not filled in and odd values
are not corrected, because a row the source never published is an invention.
Each known anomaly is declared next to a test that fails on any new one.
Where the data changes every day, the test is a rule or a share rather than a
fixed count.

**Strict conversions.** Dates and numbers are converted with casts that raise
an error on unexpected input, so a format change at the source stops the
build instead of producing nulls that surface later.

**Deduplicate only where the source repeats itself.** Exchange rates cannot
hold the same date twice in bronze by construction, so their model does not
deduplicate: a failing uniqueness test is more useful than a model that
silently picks one row. Guatecompras does repeat processes inside its files,
so its models keep the most recently updated copy, and the uniqueness tests
check the result.

**Models list the fields they read.** A contracting process is a large
nested document. Each silver model names the fields it parses out of it;
everything else, including contact details of people, stays in bronze. It
also keeps the models independent of fields they do not use.

**Entity codes stay text.** The code of a budget entity is an identifier
that two sources share, not a number to compute with, so it is kept as the
same eight-character text in both, which is what makes them join.

**Business dates are days in Guatemala.** A timestamp is turned into a date
with an explicit conversion to the time zone of Guatemala, not with the time
zone of the machine the engine runs on.

**Exact decimals.** Rates are `DECIMAL(10,6)`, matching the six decimals the
source uses, and amounts are `DECIMAL(18,2)`. Floating point would make the
comparison between buying and selling rates unreliable.

**Full rebuild on every run.** Every model is rebuilt from all of bronze each
time. It is simple and safe to repeat. The cost is time: re-reading 4.9 GB of
JSON takes most of the three minutes of a build.

**DuckDB works inside a memory limit.** The engine is capped below the memory
of its container and spills to disk beyond that, instead of being killed.

**dbt Core with dbt-duckdb, not dbt v2.** When this was written the DuckDB
adapter of the new Fusion engine was in beta and its bundled driver could not
load DuckDB extensions, including the one that reads S3.

**Layer folders, dbt model names.** Models live in folders named after the
lakehouse layers (`models/silver`, `models/gold`). Model names follow the dbt
conventions: `stg_<source>__<entity>` for a cleanup of a source table, which
is what dbt calls a staging model, and `fct_` and `dim_` for facts and
dimensions.

**The DuckDB database is kept in a volume, and is still disposable.** It
holds views over the Parquet files and the seeds, nothing else. Keeping it
between runs lets separate dbt commands, and the documentation site, see what
the last build produced. Deleting it loses nothing.

## Dimensional model

**Exchange rates: one row per currency and calendar day.** The source skips
five days. With a row for every day, any other fact finds the rate for its
own date with a plain join. The alternative, keeping only published days, was
rejected because every consumer would have to decide what to do on a day
without a rate, and they could decide differently.

**Gaps are filled in gold, not in silver.** Silver holds what the source
published. Carrying a rate over to a skipped day is a business rule, so it
lives in gold, and the rows it creates are flagged and say which day their
rate comes from.

**One reference rate for conversions.** Until 2006-12-01 the source publishes
different buying and selling rates. Gold adds `reference_rate`, their
midpoint, so that everything downstream converts with the same number. Since
2006-12-02 both rates are equal and the midpoint is the published rate; before
that it is a computed value, and the column description says so. It is
calculated with exact decimals, which needs one more decimal place than the
source uses.

**Awards: one row per award.** An award is the event that carries money: one
process, one supplier, one amount, one date. A row per process was rejected
because a process can be awarded to several suppliers, and the supplier would
be lost. The price is that processes never awarded are not in this table.

**Cancelled awards stay, flagged.** Removing them would make every sum
correct without a filter, but would hide how much is cancelled. They are kept
with `is_cancelled`, and the description of the table says that a total of
valid awards must filter on it.

**Amounts are converted once, in gold.** Each award carries its amount in
dollars, computed with the reference rate of the day of the award. Every
consumer gets the same figure, and the rate used is the one in
`fct_exchange_rates` for that day.

**A buyer is not a budget entity.** The entity code of the public sector's
institutional classifier is what the budget uses, and several buyers can
share one. The buyer dimension has one row per body that buys, identified by
its tax number, and keeps the entity code as an attribute.

**Budget: one row per budget line and fiscal year.** That is the grain of
the source, and the most detailed one: any summary by entity, program, item,
source or place is computed from it. Aggregating to entity, item and source
was rejected because program, executing unit and place could not be
recovered from gold.

**Classifiers with a hierarchy become dimensions; bare codes stay in the
fact.** The program path, the expenditure item with its subgroup and group,
the funding source and the place have names and hierarchies of their own.
Budget type, economic class and lending organism are just a code and a name
on each line, so they stay in the fact table as degenerate attributes.

**One entity dimension for budget and procurement.** `dim_entity` holds every
entity code either source mentions. The 19 central government entities take
their official names from the budget; the rest take the buyer name used in
most of their processes, and `name_source` says which is which. Keeping only
the 19 official entities was rejected, because most purchases are made by
municipalities and decentralized bodies.

**Buyers point to their entity.** `dim_buyer` carries `entity_key`, a link
from one dimension to another, so an award reaches its entity through its
buyer. The alternative, adding the entity to the awards fact table, would
have needed a placeholder entity for the buyers that never name theirs.

**Budget amounts stay in quetzales.** A budget accumulates over a year, so
there is no single day whose rate would convert it.

**Dimensions keep the latest description.** A buyer or supplier that changes
name appears with its most recent one, and earlier names are not kept. With
a full rebuild from the current state of the source there is no history to
keep.

**Surrogate keys.** Dimensions are keyed by a hash of their natural key, and
`dim_date` by the date as the integer YYYYMMDD. A hash is the same on every
rebuild, so it needs no counter, unlike sequential integers, which would have
to remember what was assigned before. It also lets a fact table compute its
foreign keys without joining the dimension; tests then check that every key
exists.

**The calendar does not depend on the facts.** `dim_date` is generated from a
fixed start to the end of the current year instead of from the dates present
in a fact table, so every fact table can share it. Awards use it twice, for
the day of the award and the day the tender was published.

**Documentation is served locally.** `dbt docs` is exposed as a Compose
service. Publishing it would need a CI workflow that runs the whole pipeline
and is left for later.

## Orchestration

**Airflow, not Dagster.** Dagster's model of assets and partitions fits this
project closely: every bronze partition and dbt model would be an asset with
lineage drawn for free. Airflow was chosen because it is the orchestrator
most teams run and most job descriptions ask for. The price is a task-based
view: Airflow knows the four tasks, not the tables they produce.

**Airflow schedules; the images do the work.** Each task starts the
ingestion or transform image as a container, exactly like `docker compose
run`. Installing the jobs and dbt inside the Airflow image was rejected: three
sets of dependencies would share one environment and could clash, and the
jobs would no longer run the same way with or without Airflow. The price is
the Docker socket, mounted into the scheduler.

**One DAG, one dbt task.** The three ingestion tasks run in parallel, since
they share nothing, and `dbt build` runs once all of them succeed. dbt
already orders models and tests, so it runs as a single task; splitting it
into one Airflow task per model (with Cosmos) would add a dbt parse inside
Airflow for little gain at this size.

**The full range, every day.** Each run loads the exchange rates of the
current year, Guatecompras from January 2025 and whatever is in the landing
folder. A shorter daily window with a weekly full refresh was rejected as two
schedules to reason about.

**Retries live in Airflow.** Every job can be repeated safely, so a failed
task is retried twice, ten minutes apart. Missed days are not caught up
(`catchup=False`) and only one run is active at a time, because each run
already refreshes everything.

**Lightweight setup.** The local executor runs tasks inside the scheduler, so
there is no Celery or Redis; Postgres holds Airflow's own state. The storage
key pair reaches the containers through `private_environment`, which Airflow
does not show in its interface or write to its logs.

## Dashboard

**Streamlit.** A light Python app whose pages are code in this repository,
reviewed and tested like the rest. Evidence was the closest alternative:
pages written in SQL and Markdown and built into a static site, cheap to
host. It was rejected because the site has to be rebuilt after every dbt run,
and the data it shows is shipped to the viewer's browser. Metabase and
Superset are full BI tools, but they keep their dashboards in their own
database instead of in git, and they need more memory and services (a JVM;
Postgres, Redis and workers) than this machine has to spare.

**Read gold where it is.** DuckDB, the engine that builds the lakehouse, reads
the Parquet files of gold straight from the bucket. Copying gold into a
database for the dashboard was rejected as a second copy to keep in step; the
price is that a query reads the files over the network, which an hour of
caching makes rare. Results are at most an hour older than the last build.

**Queries in the dashboard, not in dbt.** Each page asks gold its own
questions, in SQL kept in one module. Models built only for the dashboard
were left out until a question repeats across pages or consumers; then it
belongs in dbt, where it is tested and documented.

**Its own read-only key.** The dashboard gets a key pair that can read prod
gold and nothing else, so even a flaw in the app cannot reach silver, where
the personal data is in the clear. Streamlit is also kept from contacting
outside services: no usage statistics, and no lookup of the machine's public
IP at start.

## Infrastructure

**Terraform for storage and permissions only.** The configuration covers
what the code depends on: the buckets and what each job may do in them.
Images, scheduled tasks and the dashboard service were left as a written
design, because running them costs money and an emulator cannot show that
they work.

**An emulator, not an AWS account.** Applying the configuration to AWS would
create billable resources. It is applied instead to Moto, an open source
emulator of the AWS APIs that runs in a container without an account.
LocalStack, the better known emulator, was rejected because since March 2026
it requires an account and a token even on its free plan, which is limited
to non-commercial use. The price is that Moto does not enforce IAM policies.

**Roles, not users with keys.** Each job gets an IAM role to be assumed by
its ECS task, so its credentials are temporary and rotate on their own. IAM
users with access keys would have mirrored the local key pairs exactly, but
long-lived keys are what a security review flags first. The jobs had to
change for this: they used to require a key pair, and now use the standard
AWS credential chain when none is given. In dbt the secret is created by a
plugin, because the profile cannot leave out a setting depending on the
environment, and a key given at all, even empty, overrides the chain.

**Keys managed by S3.** Every bucket is encrypted with SSE-S3. A customer
managed KMS key would add a monthly cost and a charge per request, for data
that is public.

**Versioning only where data cannot be rebuilt.** Bronze keeps previous
versions for 90 days, because the sources do not keep their history and an
overwrite by a bad load would otherwise be final. Silver and gold are
rebuilt from bronze on every run, so versioning them would only add cost.

**The same configuration for the emulator and for AWS.** The emulator is
reached through `AWS_ENDPOINT_URL`, a standard variable, and the only
differences are in `emulator.tfvars`: path-style addresses, and the TLS-only
bucket policy turned off because the emulator serves plain HTTP.

**Terraform in a container.** Like every other tool in the project it runs
through Compose, pinned to one version, so nothing has to be installed.
