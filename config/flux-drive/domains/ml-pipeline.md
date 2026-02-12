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

Key review areas:
- Train/test split contamination
- Random seed propagation across libraries
- Metric calculation correctness
- Experiment metadata completeness
- Checkpoint and artifact versioning

### fd-data-quality

Focus: Data pipeline validation, schema enforcement, distribution monitoring, feature engineering correctness.

Key review areas:
- Input schema validation at pipeline boundaries
- Feature computation consistency (training vs inference)
- Missing value and outlier handling
- Data drift detection and alerting
- Lineage tracking from raw data to features

### fd-model-serving

Focus: Inference optimization, deployment patterns, model lifecycle management, A/B testing infrastructure.

Key review areas:
- Model loading and warm-up patterns
- Batching and concurrency configuration
- Canary deployment and traffic splitting
- Resource sizing (GPU memory, CPU threads)
- Graceful degradation under load
