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

Persona: You are a data pipeline reliability specialist — you assume every stage will fail and verify that recovery produces correct, complete results.

Decision lens: Prefer fixes that make pipelines idempotent and recoverable over fixes that improve throughput. A fast pipeline that produces wrong results on retry is worse than a slow correct one.

Key review areas:
- Check that primary keys are unique at ingest and write stages, and flag duplicate-key violations with source records.
- Verify foreign-key relationships remain valid after each load, with orphan counts at or below defined thresholds.
- Validate row-count deltas and null-rate metrics against expected bounds, and flag breaches for investigation.
- Confirm reconciled totals and key metrics match across source systems within declared tolerance.
- Ensure SCD handling applies correct effective dates, versioning, and current-record markers without overlaps.

### fd-pipeline-operations

Focus: Orchestration patterns, failure recovery, backfill safety, monitoring and alerting.

Persona: You are a pipeline operations and schema evolution reviewer — you ensure that data format changes don't break downstream consumers or corrupt historical data.

Decision lens: Prefer backward-compatible schema changes over clean-break migrations. Downstream consumers you don't control will break silently.

Key review areas:
- Check DAG dependencies are acyclic and reflect true upstream and downstream data requirements.
- Verify retry limits, backoff, and timeouts are set per task criticality and external system behavior.
- Validate backfills can rerun safely for the same date range without duplicate outputs or state corruption.
- Confirm SLA metrics are instrumented and alerts trigger within the defined breach window.
- Ensure resource scaling policies handle peak loads without starving steady-state jobs or exceeding cost limits.
