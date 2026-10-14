{{
    config(
        location="s3://" ~ env_var("S3_BUCKET_SILVER") ~ "/minfin/central_government_expenditure/central_government_expenditure.parquet"
    )
}}

with source as (

    select * from {{ source('bronze_minfin', 'central_government_expenditure') }}

)

-- The casts are strict: a code or amount the ministry writes in an
-- unexpected way stops the build instead of becoming a null. The row number
-- of the workbook (id) is dropped; the fifteen codes identify a line.
select
    ejercicio::integer as fiscal_year,
    -- Kept as text: it joins with the entity codes of other sources.
    codigoEntidad as entity_code,
    entidad as entity_name,
    codigoUnidadEjecutora::integer as executing_unit_code,
    unidadEjecutora as executing_unit_name,
    codigoPrograma::integer as program_code,
    programa as program_name,
    codigoSubProg::integer as subprogram_code,
    subPrograma as subprogram_name,
    codigoProyecto::integer as project_code,
    proyecto as project_name,
    codigoActividad::integer as activity_code,
    actividad as activity_name,
    codigoObra::integer as work_code,
    obra as work_name,
    codigoDepto::integer as department_code,
    departamento as department_name,
    codigoMunicipio::integer as municipality_code,
    municipio as municipality_name,
    codigoTipoPresupuesto::integer as budget_type_code,
    tipoPresupuesto as budget_type_name,
    codigoGrupoGasto::integer as expenditure_group_code,
    grupoGasto as expenditure_group_name,
    codigoSubGrpGasto::integer as expenditure_subgroup_code,
    subGrupoGasto as expenditure_subgroup_name,
    codigoRenglon::integer as expenditure_item_code,
    renglon as expenditure_item_name,
    codigoEconomico::integer as economic_code,
    economico as economic_name,
    codigoFuente::integer as funding_source_code,
    fuente as funding_source_name,
    codigoOrganismo::integer as organism_code,
    organismo as organism_name,
    correlativo::integer as correlative,
    asignado::decimal(18, 2) as initial_budget,
    modificado::decimal(18, 2) as budget_changes,
    vigente::decimal(18, 2) as current_budget,
    preComprometido::decimal(18, 2) as pre_committed,
    comprometido::decimal(18, 2) as committed,
    devengado::decimal(18, 2) as accrued,
    pagado::decimal(18, 2) as paid,
    _source_file as source_file,
    _ingested_at as ingested_at
from source
