{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_GOLD") ~ "/dim_date/dim_date.parquet"
    )
}}

-- The calendar does not depend on any fact table. It starts in the first year
-- with data and always runs to the end of the current year, so every fact
-- can find its date.
with days as (

    select
        unnest(
            generate_series(
                date '1989-01-01',
                date_trunc('year', current_date) + interval '1 year' - interval '1 day',
                interval '1 day'
            )
        )::date as date_day

)

select
    strftime(date_day, '%Y%m%d')::integer as date_key,
    date_day,
    year(date_day)::integer as year,
    quarter(date_day)::integer as quarter,
    month(date_day)::integer as month,
    monthname(date_day) as month_name,
    day(date_day)::integer as day_of_month,
    isodow(date_day)::integer as day_of_week,
    dayname(date_day) as day_name,
    isodow(date_day) in (6, 7) as is_weekend,
    date_trunc('month', date_day)::date as first_day_of_month
from days
order by date_day
