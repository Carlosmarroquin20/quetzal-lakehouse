{#
    Leaves a mark in gold.staging when a build ends with every model built
    and every test passed. A test that only warns still passes, and nodes
    with nothing to run, such as exposures, report "no-op".
    publish_gold refuses to run without it, so data that failed a test can
    never be published, whoever runs the publish. clear_gold_staging removes
    the mark when the next build starts.
#}
{% macro mark_build_passed(results) %}
    {%- if execute and flags.WHICH == "build" -%}
        {%- set failed = results
            | rejectattr("status", "in", ["success", "pass", "warn", "no-op"])
            | list -%}
        {%- if failed -%}
            {{ log("Build did not pass (" ~ failed | length ~ " failed or skipped); gold will not be published.", info=True) }}
        {%- else -%}
            {%- do run_query(
                "create or replace table gold.staging._build_passed as"
                ~ " select now() as passed_at"
            ) -%}
        {%- endif -%}
    {%- endif -%}
{% endmacro %}
