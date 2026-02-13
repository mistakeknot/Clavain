# ML Pipeline Domain Profile

## Detection Signals

Primary signals (strong indicators):
- Directories: `models/`, `training/`, `inference/`, `datasets/`, `notebooks/`, `experiments/`, `pipelines/`
- Files: `*.ipynb`, `dvc.yaml`, `mlflow.*`, `wandb.*`, `*.onnx`, `*.pt`, `*.h5`, `*.safetensors`
- Frameworks: PyTorch, TensorFlow, Keras, scikit-learn, HuggingFace, Transformers, MLflow, W&B, DVC, Ray, Airflow
- Keywords: `model.train`, `optimizer`, `loss_function`, `batch_size`, `epoch`, `learning_rate`, `embedding`

Secondary signals (supporting):
- Directories: `features/`, `checkpoints/`, `configs/`, `evaluation/`
- Files: `requirements.txt`, `pyproject.toml`, `Dockerfile` (with CUDA/GPU references)
- Keywords: `gradient`, `backpropagation`, `tokenizer`, `fine_tune`, `hyperparameter`, `inference`, `checkpoint`

## Injection Criteria

When `ml-pipeline` is detected, inject these domain-specific review bullets into each core agent's prompt.

### fd-architecture

- Check that training, evaluation, and inference pipelines share model definitions (no copy-pasted model code that drifts)
- Verify configuration management separates hyperparameters from infrastructure config (model config vs. cluster config)
- Flag missing experiment tracking integration — training runs without logged params/metrics are unreproducible
- Check that feature engineering is a shared pipeline stage, not duplicated between training and inference
- Verify model artifacts have versioned storage with metadata (not loose files in a shared directory)

### fd-safety

- Check that training data pipelines don't accidentally include PII or sensitive data without anonymization
- Verify model artifacts are checksummed — corrupted weights should fail loudly at load time, not silently produce wrong predictions
- Flag hardcoded credentials for data sources, model registries, or cloud storage in training scripts
- Check that inference endpoints validate input shapes and types before passing to models (malformed tensors shouldn't crash)
- Verify that model serving doesn't expose internal architecture details through error messages

### fd-correctness

- Check for train/test data leakage — features computed on the full dataset before splitting, or test data in training batches
- Verify random seed handling is deterministic for reproducibility (numpy, torch, python hash seed all pinned)
- Flag silent shape mismatches — broadcasting rules can mask bugs where tensors have wrong dimensions
- Check that evaluation metrics match the actual loss function used in training (optimizing for A, measuring B)
- Verify data preprocessing is identical in training and inference (different normalization = silent accuracy drop)

### fd-quality

- Check that notebook code is refactored into importable modules before deployment (no production notebooks)
- Verify experiment configs are structured (YAML/TOML) with schema validation, not ad-hoc argparse with 50 flags
- Flag magic numbers in model architecture (hidden_size=768) without named constants or config references
- Check that data pipeline stages have clear ownership — who maintains each transformation, who validates outputs
- Verify test coverage includes data validation (schema checks, distribution drift, null handling) not just model accuracy

### fd-performance

- Check that data loading is not the bottleneck — verify prefetching, parallel workers, and memory-mapped access
- Flag full-dataset loading into memory when streaming or batched loading would work
- Verify GPU utilization during training (common: GPU starved by slow data loading or CPU preprocessing)
- Check that inference batch sizes are tuned for throughput vs latency trade-off requirements
- Flag unnecessary model reloading — weights should be loaded once and reused across requests

### fd-user-product

- Check that model outputs include confidence scores or uncertainty estimates, not just bare predictions
- Verify that model behavior is explainable to stakeholders (feature importance, attention visualization, SHAP values)
- Flag missing monitoring for model performance degradation in production (accuracy drift, latency spikes)
- Check that training pipeline failures produce actionable error messages (not just "OOM" — which operation, what batch size)
- Verify that model updates have a rollback mechanism (bad model deploy shouldn't require code changes to revert)

## Agent Specifications

These are domain-specific agents that `/flux-gen` can generate for ML pipeline projects. They complement (not replace) the core fd-* agents.

### fd-experiment-integrity

Focus: Reproducibility, data leakage detection, metric validity, experiment tracking hygiene.

Persona: You are an experiment integrity auditor — you ensure that when someone says 'the model improved by 3%', that number is real and reproducible.

Decision lens: Prefer fixes that make results reproducible and comparable over fixes that speed up training. A fast experiment you can't trust is worse than a slow one you can.

Key review areas:
- Check train, validation, and test splits are isolated with no leakage by entity, time, or feature derivation path.
- Verify random seeds are set and propagated across all libraries and components that affect stochastic behavior.
- Validate metric definitions and implementations match task objectives and handle edge cases correctly.
- Confirm each run records required metadata (code version, data snapshot, params, environment) for reproducibility.
- Ensure checkpoints and artifacts are versioned, immutable, and linked to the exact experiment run.

### fd-data-quality

Focus: Data pipeline validation, schema enforcement, distribution monitoring, feature engineering correctness.

Persona: You are a data quality and provenance detective — you trace every feature, label, and sample back to its source and flag the moment lineage goes dark.

Decision lens: Prefer fixes that restore traceability and auditability over fixes that improve pipeline throughput. You can't debug what you can't trace.

Key review areas:
- Check input schema is validated at each pipeline boundary, and reject or route records that violate contracts.
- Verify feature transformations are identical between training and inference paths.
- Validate missing-value and outlier handling rules are explicit, consistent, and monitored for drift.
- Confirm drift metrics and alert thresholds are defined per critical feature and trigger actionable alerts.
- Ensure lineage traces each feature back to raw sources and transformation steps.

### fd-model-serving

Focus: Inference optimization, deployment patterns, model lifecycle management, A/B testing infrastructure.

Persona: You are a model operations reviewer — you bridge the gap between 'it works in notebooks' and 'it works in production at scale'.

Decision lens: Prefer fixes that improve deployment safety and rollback capability over fixes that optimize serving latency. A model you can safely roll back beats one that's 10ms faster.

Key review areas:
- Check model loading and warm-up complete before traffic cutover and meet startup latency targets.
- Verify batching and concurrency settings balance latency SLOs with throughput goals.
- Validate canary rollouts use controlled traffic splits with automatic rollback on degradation.
- Confirm CPU and GPU sizing meets p95 and p99 latency goals with required memory headroom under expected load.
- Ensure overload behavior degrades gracefully (queueing, shedding, fallback) without cascading failures.
