# AWS

[Back to the README](../README.md)

`infra/aws/` describes in Terraform the AWS storage and permissions the
lakehouse would run on. It has been applied only to a local emulator of the
AWS APIs, never to an AWS account: it costs nothing to try and needs no
account.

## What it creates

| Resource | Detail |
|---|---|
| Five S3 buckets | `<prefix>-bronze`, `-silver`, `-gold`, `-silver-dev` and `-gold-dev`, the same layout as the local stack. |
| On every bucket | Public access blocked, object ACLs disabled, encryption with keys managed by S3, requests without TLS refused, and unfinished multipart uploads removed after seven days. |
| On bronze only | Versioning, with previous versions kept for 90 days. |
| Five IAM roles | `ingestion`, `transform-prod`, `transform-dev`, `dashboard` and `notifications`, each with the same access as its local identity, to be assumed by ECS tasks. |

| Role | List and read | Write |
|---|---|---|
| `ingestion` | bronze | bronze |
| `transform-prod` | bronze, silver, gold | silver, gold |
| `transform-dev` | bronze, silver-dev, gold-dev | silver-dev, gold-dev |
| `dashboard` | gold | nothing |
| `notifications` | gold | nothing |

## The same code on both

The jobs and the dashboard read their storage settings from the environment.
Locally, Compose gives them the endpoint of SeaweedFS and the key pair of
their role. On AWS they would get neither: without `S3_ENDPOINT_URL` they use
AWS S3, and without `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` they take
the temporary credentials of their role, found the standard AWS way (boto3
for ingestion, the `aws` extension of DuckDB for dbt and the dashboard).

| Variable | Local stack | AWS |
|---|---|---|
| `S3_ENDPOINT_URL` | `http://storage:8333` | not set |
| `S3_REGION` | `us-east-1` | the region of the buckets |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | the key pair of the role | not set |
| `S3_BUCKET_*` | the local buckets | the `buckets` output of Terraform |

## Trying it against the emulator

The emulator is [Moto](https://github.com/getmoto/moto) in server mode, and
Terraform runs in a container, so neither has to be installed.

1. Start the emulator and create everything in it:

   ```bash
   docker compose --profile aws up -d aws-emulator
   docker compose --profile aws run --rm terraform init
   docker compose --profile aws run --rm terraform apply -var-file=emulator.tfvars
   ```

   The apply creates 36 resources and prints the bucket and role names. The
   emulator keeps everything in memory, so restarting it starts over (delete
   `infra/aws/terraform.tfstate` too).

2. Run a job the way ECS would: with temporary credentials of its role and
   no project key pair. This asks the emulator for credentials of the
   ingestion role and loads the exchange rates into the emulator's bronze:

   ```bash
   docker compose run --rm --no-deps --entrypoint python \
     -e AWS_ACCESS_KEY_ID=emulator -e AWS_SECRET_ACCESS_KEY=emulator \
     ingestion -c "import boto3; c = boto3.client('sts', endpoint_url='http://aws-emulator:5000', region_name='us-east-1').assume_role(RoleArn='arn:aws:iam::123456789012:role/quetzal-emulator-ingestion', RoleSessionName='try')['Credentials']; print(c['AccessKeyId'], c['SecretAccessKey'], c['SessionToken'])"
   ```

   ```bash
   docker compose run --rm --no-deps \
     -e S3_ENDPOINT_URL=http://aws-emulator:5000 \
     -e S3_BUCKET_BRONZE=quetzal-emulator-bronze \
     -e S3_ACCESS_KEY_ID= -e S3_SECRET_ACCESS_KEY= \
     -e AWS_ACCESS_KEY_ID=<key> -e AWS_SECRET_ACCESS_KEY=<secret> -e AWS_SESSION_TOKEN=<token> \
     ingestion exchange-rates --from-year 1989
   ```

   The same works for dbt with the `transform-prod` role and the silver and
   gold buckets of the emulator, and for the dashboard with the `dashboard`
   role.

3. Stop it:

   ```bash
   docker compose --profile aws down
   ```

What was checked on 2026-10-15, with the role credentials of each job:

- The ingestion job loaded the full exchange rate history into the
  emulator's bronze.
- dbt built the exchange rate models, silver and gold, with their seeds and
  tests: `PASS=52 ERROR=0`.
- The dashboard's connection read `fct_exchange_rates` from the emulator's
  gold.
- The local stack, with key pairs, still runs as before: the full prod build
  ended with `PASS=223 ERROR=0`.
- The `notifications` role, added afterwards, was created with read access
  to gold only, and the emulator issued temporary credentials for it. The
  digest itself was not run against the emulator.

The emulator does not enforce IAM policies, so it does not prove that each
role is limited to its buckets; the same rules were checked against
SeaweedFS, where they are enforced (see [Governance](governance.md)). It does
evaluate bucket policies: with the TLS-only policy on, the first write of the
ingestion job over its plain HTTP was refused with a 403, which is why
`emulator.tfvars` turns that policy off.

## What a deployment would add

Not written, because they cost money to run and the emulator cannot test
them in a meaningful way:

- **Images in ECR**, built from the same Dockerfiles.
- **Jobs as ECS Fargate tasks**, each with the role of its job as task role,
  started by EventBridge Scheduler in the order the Airflow DAG uses, or by
  Amazon MWAA (managed Airflow) running the existing DAG with the ECS
  operator instead of the Docker one. MWAA keeps the DAG as it is but has a
  fixed monthly cost; the scheduler is much cheaper for six tasks a day.
- **The dashboard as an ECS service** behind a load balancer with
  authentication, since Streamlit has no login.
- **Secrets in AWS Secrets Manager**: the pseudonymization keys, read by the
  dbt tasks.
- **Terraform state in an S3 bucket** with locking, instead of a local file.
- **The MINFIN workbooks** uploaded by hand to a landing prefix instead of a
  local folder.
