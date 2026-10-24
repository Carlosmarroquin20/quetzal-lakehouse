{#
    A model's custom schema is used as it is, not appended to the target's
    schema: gold is built in gold.staging, not gold.main_staging.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
