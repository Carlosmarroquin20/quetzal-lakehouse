# Governance

[Back to the README](../README.md)

Natural persons are pseudonymized in gold, every job has a key pair that only
reaches its own buckets, dbt runs in a dev and a prod environment, the
lineage from each source to its consumers is documented, and the
notifications that leave the lakehouse show no more than the dashboard does.

## Personal data

Guatecompras is public data under an open license, and it names people: 7,794
of the 13,138 suppliers awarded since January 2025 are natural persons, and
each process lists contact names, emails, phone numbers and addresses of its
parties, as well as the members of award committees.

| Layer | What it holds | Who can read it |
|---|---|---|
| Bronze | The files as published, with all of it. | Ingestion and both dbt environments. |
| Silver | Only what a model uses: the supplier's tax number, name and legal type. Contact details and committee members are never read out of bronze, because the models list the fields they parse. | The dbt role of its environment. |
| Gold | Natural persons pseudonymized: no tax number, no name. | Anyone who consumes the lakehouse. The dashboard and the daily digest read it, each with its own key pair that can read nothing else. |
| Notifications | A few figures of gold, sent to a Telegram chat and an email address outside the lakehouse. | Whoever receives them. |

In `dim_supplier`, a natural person, and a supplier whose legal type is
unknown, keeps no identifier and is named "Natural person" or "Supplier of
unknown legal type"; `is_masked` says which rows are. Companies keep their
identifier and name. The key of every supplier is an HMAC-SHA256 of its
identifier with a secret key, so every award of the same supplier still
shares it but nobody without the key can compute it from a tax number.

The silver columns that hold personal data are tagged `personal_data` in the
dbt documentation, and two tests guard gold: one checks that masked rows show
no identity, the other compares gold with silver and fails if the tax number
or name of any such supplier appears in gold.

The dashboard shows masked suppliers only as a group. Its ranking of the
suppliers awarded the most includes legal entities only: ranking masked
suppliers one by one would single out individuals by their amounts, even
without a name.

The daily digest follows the same rules, and it is stricter because it
leaves the lakehouse (see [Notifications](notifications.md)). Its largest
awards are those to legal entities, with their process identifier; awards to
masked suppliers appear as a number and a total. When one of them passes the
alert threshold the message says so without the amount or the buyer: on real
data the largest award of a day went to a natural person of a named
municipality, and its buyer, day and amount were enough to find the process,
and the name, in Guatecompras. The chat and the addresses that receive the
messages are in `.env`, never in the exported workflows, and the export is
checked for personal addresses before it is written.

## Design decisions

**Pseudonymize in gold; silver stays restricted.** Gold is the layer others
consume, so that is where natural persons stop being identifiable. Silver
keeps the original values, readable only by the dbt role of its environment,
so the data team can still check a specific case. Masking already in silver
was rejected because it would leave no layer short of raw JSON to do that.
Showing clear or masked values depending on who asks (dynamic masking) needs
users and roles in the query engine, which DuckDB does not have.

**A keyed hash, not a plain one.** The supplier key used to be an MD5 of the
tax number. Tax numbers are few enough to hash every possible one, so that
key revealed the person behind it even with the name hidden. The key is now
an HMAC-SHA256 with a secret key per environment.

**The secret stays out of SQL.** DuckDB has no HMAC and cannot read
environment variables, and a key written into a model would appear in the
compiled SQL and on the documentation site. A dbt-duckdb plugin
(`transform/plugins/pseudonymization.py`) registers `pseudonymize()` on every
connection and reads the key from the environment. The function receives
values in batches: called once per row it cost about 5 ms a row, which made
the awards table take hours; in batches it takes seconds.

**Unknown means masked.** A supplier whose legal type the source does not
give could be a person, so it is masked like one.

**One key pair per role.** The store has an identity per role, created at
start by `storage-init`: ingestion can read and write bronze only; dbt in
prod can read bronze and write prod silver and gold; dbt in dev can read
bronze and write dev silver and gold, and cannot even read prod; the
dashboard can read prod gold and nothing else, and so can the daily digest,
with a key pair of its own. This is what the bucket per layer was chosen for
in the first place. The administrator key is not used by any job. On AWS the
same five roles are IAM roles with the same access and no long-lived keys;
see [AWS](aws.md).

**One catalog login per role, too.** The DuckLake catalogs follow the same
lines: dbt in prod owns the prod catalogs, dbt in dev the dev ones, and
neither can connect to the other's. The dashboard and the digest each have a
login that can only read the prod gold catalog: they can neither change it
nor connect to silver. Postgres enforces it, and the readers also attach the
catalog read-only.

**The digest has its own role.** It reads exactly what the dashboard reads,
and could have reused its key pair. A separate one means that each consumer
of gold can be told apart in the store and revoked without stopping the
other, and that a leak of the key in Airflow, where the digest task runs,
does not expose the dashboard's.

**Notifications carry their own secret.** The webhooks of n8n accept only
requests with the secret shared in `NOTIFICATIONS_WEBHOOK_SECRET`. Airflow
passes it to the digest task through `private_environment`, like the storage
keys, and n8n keeps it as an encrypted credential. The Telegram token and the
mail password exist only as n8n credentials, created by hand.

**Two environments, one bronze.** Bronze is the same for both, because
downloading the sources twice would add nothing. Silver and gold have a
bucket per environment, and the dbt targets `dev` and `prod` differ only in
what their Compose services pass in: buckets, key pair and pseudonymization
key. dbt defaults to dev, and Airflow runs prod. Two complete stacks were
rejected as double downloads, disk and memory on one machine; prefixes inside
shared buckets, for the same reason buckets were chosen per layer.

**Lineage at three levels.** Each source declares where its data comes from,
which job loads it, where the original files are, how often it refreshes and
whether it holds personal data. dbt draws the graph from sources to models,
and exposures declare the dashboard, the daily digest and the analyses that
consume gold, so the graph shows what a change would affect. Each silver row keeps the bronze file it came
from and when it was loaded. Emitting OpenLineage events to a Marquez server
was left out: it would add services to a machine that already runs Airflow,
for a graph dbt already draws.
