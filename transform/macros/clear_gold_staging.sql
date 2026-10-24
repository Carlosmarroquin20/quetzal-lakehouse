{#
    Empties gold.staging when a build or run starts, the mark of a passed
    build included, so that afterwards it holds only what this invocation
    built. publish_gold refuses to publish if any gold model is missing from
    it, so a build that stopped part way, or that built only some models,
    can never be published as a whole.
    Other commands, such as dbt test or the publish operation itself, leave
    staging as it is.
#}
{% macro clear_gold_staging() %}
    {%- if execute and flags.WHICH in ("build", "run") -%}
        {%- set tables = run_query(
            "select table_name from duckdb_tables()"
            ~ " where database_name = 'gold' and schema_name = 'staging'"
        ).columns[0].values() -%}
        {#- Through the adapter, so dbt's cache of existing relations forgets
            them too; otherwise a model would try to back up a dropped table. -#}
        {%- for table in tables -%}
            {%- do adapter.drop_relation(api.Relation.create(
                database="gold", schema="staging", identifier=table, type="table"
            )) -%}
        {%- endfor -%}
    {%- endif -%}
{% endmacro %}
