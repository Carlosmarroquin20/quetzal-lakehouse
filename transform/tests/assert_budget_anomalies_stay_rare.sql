-- Two inconsistencies appear in the published budget and are accepted while
-- they stay rare. When this was written, 13 lines of 2025 had more accrued
-- than committed (0.01 %), and 1,469 lines of 2026 had more committed than
-- the current budget (0.9 %). Returns the fiscal years where either share
-- grows past its limit.

select
    fiscal_year,
    count(*) as budget_lines,
    count(*) filter (where accrued > committed) as accrued_above_committed,
    count(*) filter (where committed > current_budget) as committed_above_current_budget
from {{ ref('stg_minfin__central_government_expenditure') }}
group by fiscal_year
having count(*) filter (where accrued > committed) > 0.001 * count(*)
    or count(*) filter (where committed > current_budget) > 0.02 * count(*)
