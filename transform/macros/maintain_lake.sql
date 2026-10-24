{#
    Keeps the DuckLake catalogs from growing without end. Every build writes
    new files and keeps the old ones, which is what lets a query read a table
    as it was on an earlier day. This forgets the versions older than
    `keep_days` and deletes the files only they used.

        dbt run-operation maintain_lake --args '{keep_days: 30}'
#}
{% macro maintain_lake(keep_days=30) %}
    {%- set older_than = "now() - interval '" ~ (keep_days | int) ~ " days'" -%}
    {%- for catalog in ["silver", "gold"] -%}
        {%- do run_query(
            "call ducklake_expire_snapshots('" ~ catalog ~ "', older_than => " ~ older_than ~ ")"
        ) -%}
        {%- do run_query("call ducklake_cleanup_old_files('" ~ catalog ~ "', cleanup_all => true)") -%}
        {{ log("Kept " ~ keep_days ~ " days of versions in " ~ catalog, info=True) }}
    {%- endfor -%}
{% endmacro %}
