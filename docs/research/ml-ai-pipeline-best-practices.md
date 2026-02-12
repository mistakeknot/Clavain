# ML/AI Pipeline Development: Code Review Checklist

> **Research Date:** 2026-02-12
> **Focus:** PyTorch, Transformers, LangChain production codebases
> **Sources:** Industry best practices, official documentation, community consensus

This checklist provides concrete, checkable review criteria for ML/AI pipeline development across five review dimensions: Architecture, Correctness, Performance, Safety, and Quality.

---

## 1. Architecture Review

### Training vs Inference Separation

**✓ Check: Pipeline isolation**
- [ ] Training code lives in separate modules/directories from inference code
- [ ] Shared preprocessing logic is extracted into reusable modules (not copy-pasted)
- [ ] Training scripts never import from serving modules (prevents production dependencies in training)
- [ ] Each pipeline runs in its own container (containerized isolation)

**✓ Check: Model registry pattern**
- [ ] Models are versioned and stored in a central registry (MLflow, Weights & Biases, or similar)
- [ ] Model artifacts include metadata: training dataset hash, hyperparameters, evaluation metrics
- [ ] Model lifecycle stages are tracked (staging, production, archived)
- [ ] Model aliasing is used for production references (not hardcoded paths or versions)
- [ ] Registry provides lineage tracking (which experiment/run produced the model)

**Source:** [MLflow Model Registry](https://mlflow.org/docs/latest/model-registry/), [ML Model Versioning with MLflow](https://dasroot.net/posts/2026/02/ml-model-versioning-experiment-tracking-mlflow/)

### Feature Stores

**✓ Check: Feature computation contract**
- [ ] Features computed for training use identical logic to features computed for inference
- [ ] Point-in-time correctness: training features use only data available at the feature timestamp
- [ ] Feature schemas are versioned and validated (fail fast on schema mismatch)
- [ ] Feature backfills are tested for temporal consistency (no future data leakage)

**Source:** [The Data Letter - Top 3 Data Failures of 2025](https://www.thedataletter.com/p/year-in-review-top-3-data-failures)

### Pipeline DAGs

**✓ Check: Orchestration structure**
- [ ] Each pipeline step has explicit inputs and outputs (no hidden global state)
- [ ] Steps can be developed and tested independently
- [ ] Pipeline uses an orchestrator (Airflow, Prefect, Kubeflow Pipelines) for reproducibility
- [ ] Pipeline artifacts are versioned and tracked (data, models, metrics)
- [ ] Failure recovery is explicit (retry policies, checkpointing)

**Source:** [MLOps Architecture Best Practices](https://apprecode.com/blog/mlops-architecture-mlops-diagrams-and-best-practices), [Orchestrating PyTorch Workflows on Vertex AI](https://cloud.google.com/blog/topics/developers-practitioners/orchestrating-pytorch-ml-workflows-vertex-ai-pipelines)

---

## 2. Correctness Review

### Data Leakage Prevention

**✓ Check: Train-test contamination**
- [ ] Test set is completely isolated until final evaluation (never seen during development)
- [ ] Cross-validation folds are stratified and respect temporal ordering (for time series)
- [ ] No shared identifiers between train and test (validated via hash-based filtering)
- [ ] Automated split validation tests exist (checks for overlapping records)

**✓ Check: Preprocessing leakage**
- [ ] Global statistics (mean, std, min, max) are computed ONLY on training data
- [ ] Normalization/scaling uses training statistics for both train and test transforms
- [ ] Feature selection happens ONLY on training data
- [ ] Imputation strategies are fitted on training data, applied to test data
- [ ] Pipeline classes (scikit-learn Pipeline) enforce correct fit/transform order

**Code Pattern (GOOD):**
```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest

# Correct: Pipeline ensures fit on train, transform on both
pipeline = Pipeline([
    ('scaler', StandardScaler()),          # Fitted on X_train only
    ('selector', SelectKBest(k=10)),       # Fitted on X_train only
    ('model', RandomForestClassifier())
])

pipeline.fit(X_train, y_train)             # Learns from train
predictions = pipeline.predict(X_test)     # Applies learned transforms
```

**Code Pattern (BAD):**
```python
# WRONG: Global normalization before split
scaler = StandardScaler()
X_normalized = scaler.fit_transform(X_full)  # Leaks test statistics!
X_train, X_test = train_test_split(X_normalized)
```

**Source:** [Preventing Training Data Leakage](https://www.tonic.ai/blog/prevent-training-data-leakage-ai), [scikit-learn Common Pitfalls](https://scikit-learn.org/stable/common_pitfalls.html), [Prevent Data Leakage in ML Pipelines](https://blog.dailydoseofds.com/p/prevent-data-leakage-in-ml-pipelines)

### Label Drift Detection

**✓ Check: Label distribution monitoring**
- [ ] Training label distribution is logged and versioned
- [ ] Production predictions are monitored for distribution shift
- [ ] Alerts trigger when prediction distribution deviates from training baseline
- [ ] Label drift is tracked separately from feature drift

**Source:** [How to Detect Model Drift](https://towardsdatascience.com/how-to-detect-model-drift-in-mlops-monitoring-7a039c22eaf9/), [Understanding Data Drift and Model Drift](https://www.datacamp.com/tutorial/understanding-data-drift-model-drift)

### Numerical Stability

**✓ Check: Mixed precision training**
- [ ] Uses `torch.autocast` for automatic precision casting
- [ ] Uses `torch.amp.GradScaler` for gradient scaling (prevents underflow)
- [ ] Gradient clipping happens on UNSCALED gradients (call `scaler.unscale_()` before `clip_grad_norm_`)
- [ ] Batch normalization layers run in full precision (fp32) when needed

**Code Pattern (CORRECT):**
```python
from torch.amp import autocast, GradScaler

scaler = GradScaler()

for batch in dataloader:
    optimizer.zero_grad()

    # Forward pass with autocasting
    with autocast(device_type='cuda', dtype=torch.float16):
        outputs = model(inputs)
        loss = criterion(outputs, targets)

    # Backward pass with scaling
    scaler.scale(loss).backward()

    # CRITICAL: Unscale before clipping
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

    scaler.step(optimizer)
    scaler.update()
```

**Source:** [PyTorch Automatic Mixed Precision](https://docs.pytorch.org/docs/stable/notes/amp_examples.html), [What Every User Should Know About Mixed Precision](https://medium.com/data-scientists-diary/what-every-user-should-know-about-mixed-precision-training-in-pytorch-63c6544e5a05), [Stabilizing LLM Training](https://www.rohan-paul.com/p/stabilizing-llm-training-techniques)

### Reproducibility

**✓ Check: Random seed management**
- [ ] Seeds are set for Python, NumPy, and PyTorch at script start
- [ ] CuDNN deterministic mode is enabled: `torch.backends.cudnn.deterministic = True`
- [ ] CuDNN benchmark is disabled: `torch.backends.cudnn.benchmark = False`
- [ ] DataLoader uses `worker_init_fn` to seed each worker process
- [ ] DataLoader uses `generator` argument with fixed seed
- [ ] Seeds are logged in experiment tracking (for reproducibility)

**Code Pattern (CORRECT):**
```python
import torch
import numpy as np
import random

def set_seed(seed: int = 42):
    """Set seeds for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def seed_worker(worker_id):
    """Seed each DataLoader worker."""
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)

# Usage
set_seed(42)

g = torch.Generator()
g.manual_seed(42)

dataloader = DataLoader(
    dataset,
    batch_size=32,
    worker_init_fn=seed_worker,
    generator=g,
    num_workers=4
)
```

**⚠️ Limitations:**
- Results are NOT guaranteed across PyTorch versions, platforms, or CPU/GPU
- Document the exact environment (PyTorch version, CUDA version, hardware)

**Source:** [PyTorch Reproducibility Guide](https://docs.pytorch.org/docs/stable/notes/randomness.html), [Reproducibility in PyTorch](https://www.geeksforgeeks.org/deep-learning/reproducibility-in-pytorch/), [PyTorch Reproducibility Practical Guide](https://medium.com/@heyamit10/pytorch-reproducibility-a-practical-guide-d6f573cba679)

---

## 3. Performance Review

### GPU Utilization

**✓ Check: Batch size optimization**
- [ ] Batch size is tuned to maximize GPU memory without OOM errors
- [ ] Batch dimensions are divisible by 8 (optimal for Tensor Cores)
- [ ] Gradient accumulation is used if batch size is limited by memory
- [ ] GPU utilization is monitored (aim for >80% during training)

**✓ Check: Memory optimization**
- [ ] Gradient checkpointing is enabled for large models (trades 20-30% speed for >15x batch size)
- [ ] Mixed precision training (fp16/bf16) is used to fit ~2x larger batches
- [ ] Activation checkpointing is applied to memory-intensive layers
- [ ] Model parameters and optimizer states use bf16 when possible

**Code Pattern:**
```python
# Enable gradient checkpointing
from torch.utils.checkpoint import checkpoint

class MyModel(nn.Module):
    def forward(self, x):
        # Checkpoint expensive layer
        x = checkpoint(self.expensive_layer, x, use_reentrant=False)
        return x

# Combined optimizations
model.gradient_checkpointing_enable()  # For transformers models

# Use mixed precision
with autocast(device_type='cuda', dtype=torch.bfloat16):
    outputs = model(inputs)
```

**Source:** [Memory Optimization with torchtune](https://docs.pytorch.org/torchtune/0.5/tutorials/memory_optimizations.html), [Gradient Checkpointing Guide](https://www.gilesthomas.com/2024/09/fine-tuning-9), [HuggingFace Performance Guide](https://huggingface.co/docs/transformers/v4.18.0/en/performance)

### Data Loading Bottlenecks

**✓ Check: DataLoader configuration**
- [ ] `num_workers` is tuned (start with `num_workers = 4 * num_gpus`)
- [ ] `pin_memory=True` for GPU training (faster host-to-device transfer)
- [ ] `persistent_workers=True` to avoid worker restart overhead
- [ ] Data augmentation happens on CPU (in DataLoader workers), not on GPU
- [ ] Prefetching is enabled to overlap data loading with training

**Code Pattern:**
```python
dataloader = DataLoader(
    dataset,
    batch_size=64,
    num_workers=8,              # 4 * num_gpus
    pin_memory=True,            # Faster GPU transfer
    persistent_workers=True,    # Reuse workers
    prefetch_factor=2,          # Prefetch batches
)
```

**Source:** [PyTorch DataLoader Best Practices](https://thelinuxcode.com/how-i-use-pytorch-dataloader-for-fast-reliable-training-pipelines-in-2026/)

### Inference Latency

**✓ Check: Model serving optimization**
- [ ] Dynamic batching is enabled (processes multiple requests together)
- [ ] Quantization is applied (INT8 = 4x smaller, faster inference)
- [ ] Time-to-first-token (TTFT) and time-per-output-token (TPOT) are measured for LLMs
- [ ] P50, P95, P99 latencies are tracked (not just mean)
- [ ] Model is compiled with `torch.compile()` for 2-3x speedup

**✓ Check: Serving framework**
- [ ] Use a production-grade server (NVIDIA Triton, TorchServe, BentoML)
- [ ] Dynamic batching is configured (Triton provides this out-of-the-box)
- [ ] Model concurrency is tuned (multiple model instances per GPU)
- [ ] Memory Bandwidth Utilization (MBU) is monitored and optimized

**Source:** [LLM Inference Performance Best Practices](https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices), [Serving ML Models at Scale](https://sealos.io/blog/serving-machine-learning-models-at-scale-a-guide-to-inference-optimization), [NVIDIA LLM Inference Optimization](https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization)

---

## 4. Safety Review

### Model Access Control

**✓ Check: Authentication and authorization**
- [ ] Model endpoints require authentication (API keys, OAuth)
- [ ] Role-based access control (RBAC) limits who can deploy/access models
- [ ] Model registry uses ACLs (access control lists) to restrict model downloads
- [ ] Audit logs track all model access and predictions

**Source:** [MLflow Model Registry ACLs](https://dasroot.net/posts/2026/02/ml-model-versioning-experiment-tracking-mlflow/)

### PII in Training Data

**✓ Check: Data sanitization**
- [ ] PII detection runs on training data before model training
- [ ] PII is anonymized or redacted (not just masked)
- [ ] Training data access is restricted (not world-readable)
- [ ] Data retention policies are enforced (delete after N days)

**✓ Check: Model output filtering**
- [ ] Output is scanned for PII before returning to users
- [ ] Regex patterns detect emails, phone numbers, SSNs, credit cards
- [ ] Named entity recognition (NER) models detect names, addresses

**Source:** [LLM Security and Guardrails](https://langfuse.com/docs/security-and-guardrails)

### Prompt Injection (LLMs)

**✓ Check: Input sanitization**
- [ ] User prompts are sanitized before passing to LLM
- [ ] System prompts are protected from user-controlled text
- [ ] Prompt templates use parameter binding (not string concatenation)
- [ ] Malicious instruction detection runs on user input

**✓ Check: Guardrail models**
- [ ] A secondary "guardrail" model inspects LLM outputs
- [ ] Guardrail model checks for: hidden instructions, malicious scripts, PII
- [ ] Defense in depth: two independent models must both fail for attack to succeed

**Code Pattern:**
```python
from langchain.prompts import PromptTemplate

# GOOD: Use templates with parameters
template = PromptTemplate(
    input_variables=["user_query"],
    template="System: You are a helpful assistant.\n\nUser: {user_query}\n\nAssistant:"
)
prompt = template.format(user_query=sanitized_input)

# BAD: String concatenation
prompt = f"System: You are a helpful assistant.\n\nUser: {user_input}\n\nAssistant:"  # Vulnerable!
```

**Source:** [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/), [LLM Security Risks 2026](https://sombrainc.com/blog/llm-security-risks-2026), [Monitor LLM Prompt Injection Attacks](https://www.datadoghq.com/blog/monitor-llm-prompt-injection-attacks/)

### Output Filtering

**✓ Check: Content safety**
- [ ] Toxicity detection runs on LLM outputs
- [ ] Bias detection flags problematic content
- [ ] Factual consistency checks verify generated claims (for RAG systems)
- [ ] Malicious URL blocking prevents phishing links
- [ ] Secrets detection prevents API keys/passwords in outputs

**Tool Recommendation:** LLM Guard (open-source, 2026)
- Prompt injection detection
- PII anonymization
- Toxicity filtering
- Secrets detection
- Malicious URL blocking
- Bias detection
- Factual consistency checking
- Data leakage prevention

**Source:** [LLM Guard 2026](https://appsecsanta.com/llm-guard), [LLM Security Best Practices](https://www.oligo.security/academy/llm-security-in-2025-risks-examples-and-best-practices)

---

## 5. Quality Review

### Experiment Tracking

**✓ Check: Metadata logging**
- [ ] Every experiment logs: hyperparameters, dataset version, model architecture
- [ ] Training metrics are logged every N steps (loss, accuracy, learning rate)
- [ ] System metrics are logged (GPU utilization, memory usage, throughput)
- [ ] Artifacts are versioned (model checkpoints, config files, preprocessors)
- [ ] Git commit hash is logged with each experiment

**✓ Check: Experiment comparison**
- [ ] Experiment tracking tool supports comparison UI (MLflow, Weights & Biases, TensorBoard)
- [ ] Hyperparameter sweeps are tracked and visualized
- [ ] Best model selection is automated based on validation metrics

**Source:** [MLOps Tools 2026](https://lakefs.io/mlops/mlops-tools/), [ML Model Versioning with MLflow](https://dasroot.net/posts/2026/02/ml-model-versioning-experiment-tracking-mlflow/)

### A/B Testing

**✓ Check: Model deployment strategy**
- [ ] Shadow mode testing: new model runs alongside old model without user impact
- [ ] Canary deployment: new model serves small % of traffic initially
- [ ] A/B testing framework tracks per-model metrics (accuracy, latency, user satisfaction)
- [ ] Statistical significance tests determine when to promote new model

**Source:** [Continuous Delivery for ML](https://martinfowler.com/articles/cd4ml.html)

### Model Monitoring

**✓ Check: Drift detection**
- [ ] Feature drift is monitored (input distribution vs training baseline)
- [ ] Prediction drift is monitored (output distribution vs training baseline)
- [ ] Concept drift is monitored (relationship between features and target)
- [ ] Statistical tests detect drift (KS test, Chi-square, PSI)

**✓ Check: Alerting**
- [ ] Alerts trigger when drift exceeds threshold (e.g., PSI > 0.2)
- [ ] Alerts integrate with communication tools (Slack, PagerDuty, email)
- [ ] Alerts include context (which features drifted, by how much)
- [ ] Runbooks define response procedures (retrain? investigate? rollback?)

**✓ Check: Automated retraining**
- [ ] Drift triggers automated data validation pipeline
- [ ] New data is validated for quality, completeness, consistency
- [ ] Retraining pipeline runs with new data
- [ ] New model is evaluated before deployment
- [ ] Orchestration tool schedules and manages retraining (Airflow, Prefect, Kubeflow)

**Code Pattern (Drift Detection with Evidently):**
```python
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

# Compare production data to training baseline
report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=train_df, current_data=production_df)

# Check drift
drift_results = report.as_dict()
if drift_results['metrics'][0]['result']['dataset_drift']:
    send_alert("Data drift detected!")
    trigger_retraining_pipeline()
```

**Source:** [Advanced ML Model Monitoring](https://enhancedmlops.com/advanced-ml-model-monitoring-drift-detection-explainability-and-automated-retraining/), [How to Detect Model Drift](https://towardsdatascience.com/how-to-detect-model-drift-in-mlops-monitoring-7a039c22eaf9/), [Evidently MLOps Tool](https://www.evidentlyai.com/blog/mlops-monitoring)

### Evaluation Metrics

**✓ Check: Metric selection**
- [ ] Metrics align with business objectives (not just accuracy)
- [ ] Class imbalance is addressed (use F1, precision/recall, not just accuracy)
- [ ] Regression tasks use multiple metrics (MAE, RMSE, R²)
- [ ] LLM tasks use domain-specific metrics (BLEU, ROUGE, BERTScore, human eval)

**✓ Check: Holdout test set**
- [ ] Final evaluation uses a completely unseen test set
- [ ] Test set is stratified and representative
- [ ] Test set results are reported with confidence intervals
- [ ] No hyperparameter tuning on test set (use validation set for tuning)

---

## Summary: Quick Reference Checklist

### Must-Have (P0)
- [ ] No train-test contamination (preprocessing fitted on train only)
- [ ] Reproducibility: seeds set for Python, NumPy, PyTorch, DataLoader workers
- [ ] Gradient clipping happens on unscaled gradients (mixed precision)
- [ ] Model registry tracks versions, metadata, and lineage
- [ ] PII detection and anonymization before training
- [ ] Prompt injection defenses (for LLMs)
- [ ] Drift detection and alerting in production

### Recommended (P1)
- [ ] Gradient checkpointing for large models
- [ ] Mixed precision training (fp16/bf16)
- [ ] Dynamic batching for inference
- [ ] Quantization for production models
- [ ] Experiment tracking with MLflow or W&B
- [ ] A/B testing framework
- [ ] Automated retraining pipeline

### Optional (P2)
- [ ] Feature store for feature consistency
- [ ] Guardrail models for LLM output safety
- [ ] Shadow mode testing before deployment
- [ ] Advanced monitoring (Prometheus + Grafana)
- [ ] Model compilation with torch.compile()

---

## Sources

### Architecture & MLOps
- [MLflow Model Registry](https://mlflow.org/docs/latest/model-registry/)
- [ML Model Versioning with MLflow](https://dasroot.net/posts/2026/02/ml-model-versioning-experiment-tracking-mlflow/)
- [MLOps Tools 2026](https://lakefs.io/mlops/mlops-tools/)
- [MLOps Architecture Best Practices](https://apprecode.com/blog/mlops-architecture-mlops-diagrams-and-best-practices)
- [Orchestrating PyTorch Workflows on Vertex AI](https://cloud.google.com/blog/topics/developers-practitioners/orchestrating-pytorch-ml-workflows-vertex-ai-pipelines)

### Data Leakage & Correctness
- [Preventing Training Data Leakage](https://www.tonic.ai/blog/prevent-training-data-leakage-ai)
- [scikit-learn Common Pitfalls](https://scikit-learn.org/stable/common_pitfalls.html)
- [Prevent Data Leakage in ML Pipelines](https://blog.dailydoseofds.com/p/prevent-data-leakage-in-ml-pipelines)
- [The Data Letter - Top 3 Data Failures of 2025](https://www.thedataletter.com/p/year-in-review-top-3-data-failures)

### Reproducibility & Numerical Stability
- [PyTorch Reproducibility Guide](https://docs.pytorch.org/docs/stable/notes/randomness.html)
- [Reproducibility in PyTorch](https://www.geeksforgeeks.org/deep-learning/reproducibility-in-pytorch/)
- [PyTorch Reproducibility Practical Guide](https://medium.com/@heyamit10/pytorch-reproducibility-a-practical-guide-d6f573cba679)
- [PyTorch Automatic Mixed Precision](https://docs.pytorch.org/docs/stable/notes/amp_examples.html)
- [What Every User Should Know About Mixed Precision](https://medium.com/data-scientists-diary/what-every-user-should-know-about-mixed-precision-training-in-pytorch-63c6544e5a05)
- [Stabilizing LLM Training](https://www.rohan-paul.com/p/stabilizing-llm-training-techniques)

### Performance Optimization
- [Memory Optimization with torchtune](https://docs.pytorch.org/torchtune/0.5/tutorials/memory_optimizations.html)
- [Gradient Checkpointing Guide](https://www.gilesthomas.com/2024/09/fine-tuning-9)
- [HuggingFace Performance Guide](https://huggingface.co/docs/transformers/v4.18.0/en/performance)
- [PyTorch DataLoader Best Practices](https://thelinuxcode.com/how-i-use-pytorch-dataloader-for-fast-reliable-training-pipelines-in-2026/)
- [LLM Inference Performance Best Practices](https://www.databricks.com/blog/llm-inference-performance-engineering-best-practices)
- [Serving ML Models at Scale](https://sealos.io/blog/serving-machine-learning-models-at-scale-a-guide-to-inference-optimization)
- [NVIDIA LLM Inference Optimization](https://developer.nvidia.com/blog/mastering-llm-techniques-inference-optimization)

### Security & Safety
- [OWASP LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [LLM Security Risks 2026](https://sombrainc.com/blog/llm-security-risks-2026)
- [Monitor LLM Prompt Injection Attacks](https://www.datadoghq.com/blog/monitor-llm-prompt-injection-attacks/)
- [LLM Guard 2026](https://appsecsanta.com/llm-guard)
- [LLM Security Best Practices](https://www.oligo.security/academy/llm-security-in-2025-risks-examples-and-best-practices)
- [LLM Security and Guardrails](https://langfuse.com/docs/security-and-guardrails)

### Monitoring & Drift Detection
- [Advanced ML Model Monitoring](https://enhancedmlops.com/advanced-ml-model-monitoring-drift-detection-explainability-and-automated-retraining/)
- [How to Detect Model Drift](https://towardsdatascience.com/how-to-detect-model-drift-in-mlops-monitoring-7a039c22eaf9/)
- [Understanding Data Drift and Model Drift](https://www.datacamp.com/tutorial/understanding-data-drift-model-drift)
- [Evidently MLOps Tool](https://www.evidentlyai.com/blog/mlops-monitoring)
- [What is Model Drift? Types & Solutions](https://research.aimultiple.com/model-drift/)

### LangChain & Transformers Production
- [Building Production RAG Systems 2026](https://brlikhon.engineer/blog/building-production-rag-systems-in-2026-complete-tutorial-with-langchain-pinecone)
- [Lessons Learned from Upgrading to LangChain 1.0](https://towardsdatascience.com/lessons-learnt-from-upgrading-to-langchain-1-0-in-production/)
- [Deploy LangChain Applications to Production](https://langchain-tutorials.github.io/deploy-langchain-production-2026/)

---

**Last Updated:** 2026-02-12
**Maintained by:** Clavain best-practices-researcher agent
**Review Frequency:** Quarterly (or when major framework updates occur)
