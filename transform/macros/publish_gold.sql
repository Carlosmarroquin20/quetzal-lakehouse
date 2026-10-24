{#
    Publishes gold: replaces every table of gold.main with its counterpart
    in gold.staging, all in one DuckLake transaction. Readers of gold.main see
    either the previous version of every table or the new version of every
    table, never a mix.

    It refuses unless the last build of gold.staging passed: the build
    leaves a mark there only if every model and test passed, and empties
    staging when it starts. The Airflow DAG also runs it only after a build
    that passed. Either way, gold.main keeps the last version that passed.

    Each table of gold.main is created from its model's contract, with the
    declared types and not-null constraints, and then filled by column name.
    A copy made with `create table ... as select` would keep the types but
    drop the constraints, and gold.main is the table consumers read.

        dbt run-operation publish_gold
#}
{% macro publish_gold() %}
    {%- set nodes = {} -%}
    {%- for node in graph.nodes.values()
            if node.resource_type == "model" and node.database == "gold" -%}
        {%- do nodes.update({node.alias: node}) -%}
    {%- endfor -%}
    {%- if not nodes -%}
        {{ exceptions.raise_compiler_error("No gold models to publish.") }}
    {%- endif -%}
    {%- set models = nodes.keys() | sort -%}

    {%- set staged = run_query(
        "select table_name from duckdb_tables()"
        ~ " where database_name = 'gold' and schema_name = 'staging'"
    ).columns[0].values() -%}

    {#- Refuse to publish data that failed a test. -#}
    {%- if "_build_passed" not in staged -%}
        {{ exceptions.raise_compiler_error(
            "Not publishing: the last build of gold.staging did not pass."
        ) }}
    {%- endif -%}

    {#- Refuse to publish a partial build: every model must be in staging. -#}
    {%- set missing = models | reject("in", staged) | list -%}
    {%- if missing -%}
        {{ exceptions.raise_compiler_error(
            "Not publishing: these gold models are missing from gold.staging: "
            ~ missing | join(", ")
        ) }}
    {%- endif -%}

    {%- set statements = ["begin transaction", "create schema if not exists gold.main"] -%}
    {%- for model in models -%}
        {%- set columns = [] -%}
        {%- for column in nodes[model].columns.values() -%}
            {%- set not_null = column.constraints
                | selectattr("type", "equalto", "not_null") | list -%}
            {%- do columns.append(
                adapter.quote(column.name) ~ " " ~ column.data_type
                ~ (" not null" if not_null else "")
            ) -%}
        {%- endfor -%}
        {%- do statements.append(
            "create or replace table gold.main." ~ model
            ~ " (" ~ columns | join(", ") ~ ")"
        ) -%}
        {%- do statements.append(
            "insert into gold.main." ~ model
            ~ " by name select * from gold.staging." ~ model
        ) -%}
    {%- endfor -%}
    {%- do statements.append("commit") -%}
    {%- do run_query(statements | join(";\n")) -%}
    {{ log("Published " ~ models | length ~ " gold tables: " ~ models | join(", "), info=True) }}
{% endmacro %}
