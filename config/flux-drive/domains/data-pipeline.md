# Data Pipeline Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `etl/`, `pipeline/`, `ingestion/`, `transform/`, `dags/`, `warehouse/`
- Files: `dbt_project.yml`, `*.sql`, `dagster.*`, `prefect.*`, `*.parquet`, `*.avro`
- Frameworks: Airflow, Dagster, Prefect, dbt, Spark, Flink, Kafka, Beam, Fivetran
- Keywords: `ETL`, `ELT`, `transform`, `ingestion`, `warehouse`, `schema_evolution`, `backfill`, `idempotent`

Secondary signals (supporting):
- Directories: `staging/`, `marts/`, `seeds/`, `snapshots/`, `macros/`
- Files: `profiles.yml` (dbt), `docker-compose.yml` (with broker/worker services), `*.yaml` (DAG definitions)
- Keywords: `exactly_once`, `at_least_once`, `dead_letter`, `partition`, `watermark`, `late_data`, `SCD`

## Injection Criteria

When `data-pipeline` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that pipeline stages are independently deployable and testable (not a monolithic script that does extract+transform+load)
- Verify clear separation between orchestration (scheduling, retries, dependencies) and business logic (transformations)
- Flag missing schema registry or contract — upstream schema changes shouldn't silently break downstream consumers
- Check that the pipeline supports both full-refresh and incremental modes (not just one or the other)
- Verify that staging/intermediate data is persisted between stages (failure mid-pipeline shouldn't require full restart)

### fd-safety

- Check that credentials for data sources and sinks are managed through secrets managers, not in DAG code or config files
- Verify that PII columns are tagged and handled according to retention policies (anonymization, encryption, or exclusion)
- Flag missing access controls on data warehouse tables — not everyone should read raw customer data
- Check that backfill operations are bounded and auditable (who ran it, what date range, what was overwritten)
- Verify that dead-letter queues or error tables capture failed records with context (not silently dropped)

### fd-correctness

- Check that transformations are idempotent — re-running the same date range should produce the same result without duplicates
- Verify that late-arriving data is handled correctly (watermarks, grace periods, or reprocessing triggers)
- Flag missing uniqueness constraints or deduplication in target tables (ingestion retries = duplicate rows)
- Check that timezone handling is consistent across all pipeline stages (UTC everywhere, convert only at presentation)
- Verify that type coercions are explicit — implicit string-to-number conversions hide data quality issues

### fd-quality

- Check that SQL transformations follow a consistent style (CTEs over subqueries, explicit column lists over SELECT *)
- Verify that each model/table has a description and column-level documentation (dbt docs or equivalent)
- Flag business logic buried in orchestration code — transformation rules belong in SQL/Python models, not in DAG definitions
- Check that data tests exist for critical business rules (not null, unique, accepted values, referential integrity)
- Verify that naming conventions are consistent (snake_case, prefixed by layer: stg_, int_, fct_, dim_)

### fd-performance

- Check that incremental models use proper partitioning and merge keys (full table scans on each run = cost explosion)
- Flag Cartesian joins or missing join conditions in SQL transformations
- Verify that data serialization format matches query patterns (Parquet for analytics, Avro for streaming, not CSV for everything)
- Check that pipeline parallelism is configured — independent branches should run concurrently, not sequentially
- Flag missing partition pruning — queries should filter on partition columns to avoid scanning entire tables

### fd-user-product

- Check that pipeline failures produce alerts with actionable context (which stage, what data, how to resume)
- Verify that data freshness SLAs are documented and monitored (consumers should know when to expect updated data)
- Flag missing data lineage — stakeholders should be able to trace a dashboard metric back to its source tables
- Check that self-service access is available for analysts (documented tables, query examples, known caveats)
- Verify that schema changes are communicated to downstream consumers before deployment (not discovered via broken dashboards)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for data pipeline projects. They complement (not replace) the core fd-* agents.

### fd-data-integrity

Focus: Data quality validation, schema enforcement, deduplication, consistency checks across pipeline stages.

Key review areas:
- Primary key uniqueness enforcement
- Referential integrity across tables
- Data completeness checks (row counts, null rates)
- Cross-source reconciliation
- Slowly changing dimension correctness

### fd-pipeline-operations

Focus: Orchestration patterns, failure recovery, backfill safety, monitoring and alerting.

Key review areas:
- DAG dependency correctness and cycle detection
- Retry and timeout configuration
- Backfill idempotency and date range handling
- SLA monitoring and breach alerting
- Resource scaling for peak vs steady-state loads
