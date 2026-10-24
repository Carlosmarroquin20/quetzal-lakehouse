#!/bin/sh
# Creates the DuckLake catalogs of the lakehouse and one login per role, and
# grants each only what its role needs. The catalog-init service runs this on
# every start; running it again changes nothing, and it keeps the passwords
# in step with .env.
#
# Each dbt environment owns the catalogs of its own layers and cannot connect
# to the other's, as with the key pairs of the object store. The dashboard
# and the digest can only read the prod gold catalog. The data the catalogs
# describe stays in the silver and gold buckets.
set -eu

export PGPASSWORD="$POSTGRES_PASSWORD"
run() {
    psql -v ON_ERROR_STOP=1 --quiet --host catalog --username "$POSTGRES_USER" "$@"
}

# Logins. The passwords come from the environment, so this output is kept
# quiet and never echoes the statements.
run --dbname postgres <<SQL
do \$\$
declare
    login record;
begin
    for login in
        select * from (values
            ('lake_prod', '$LAKE_CATALOG_PROD_PASSWORD'),
            ('lake_dev', '$LAKE_CATALOG_DEV_PASSWORD'),
            ('lake_dashboard', '$LAKE_CATALOG_DASHBOARD_PASSWORD'),
            ('lake_notifications', '$LAKE_CATALOG_NOTIFICATIONS_PASSWORD')
        ) as t(name, password)
    loop
        if not exists (select from pg_roles where rolname = login.name) then
            execute format('create role %I login', login.name);
        end if;
        execute format('alter role %I password %L', login.name, login.password);
    end loop;
end
\$\$;
SQL

# Catalogs, each owned by the dbt login of its environment.
for pair in lake_silver:lake_prod lake_gold:lake_prod lake_silver_dev:lake_dev lake_gold_dev:lake_dev; do
    db=${pair%%:*}
    owner=${pair#*:}
    if [ -z "$(run --dbname postgres -tAc "select 1 from pg_database where datname = '$db'")" ]; then
        run --dbname postgres -c "create database $db owner $owner"
    fi
    # Nobody but the owner, and the administrator, may connect by default.
    run --dbname postgres -c "revoke connect on database $db from public"
done

# The readers of gold: connect to the prod gold catalog and read its tables,
# including those its owner creates later. Nothing else.
for reader in lake_dashboard lake_notifications; do
    run --dbname postgres -c "grant connect on database lake_gold to $reader"
    run --dbname lake_gold <<SQL
grant usage on schema public to $reader;
grant select on all tables in schema public to $reader;
alter default privileges for role lake_prod in schema public grant select on tables to $reader;
SQL
done

echo "catalog roles applied: lake_prod, lake_dev, lake_dashboard, lake_notifications"
