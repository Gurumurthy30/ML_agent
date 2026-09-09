"""
Representative benchmark prompts for each agent role in the MLE multi-agent system.
Used by benchmark/run_benchmark.py to measure token throughput (tok/s), latency, and TTFT.
"""

DATA_EXPLORER_PROMPT = {
    "role": "data_explorer",
    "system": "You are the Data Explorer Agent in an autonomous ML engineering system. Analyze raw dataset info and produce structured task_context JSON.",
    "user": """Analyze the following dataset information and output structured task_context JSON:
Dataset Name: Kaggle Customer Churn Benchmark
Modality: Tabular
Rows: 10,000 train, 2,500 test
Target Column: churn (Binary classification)
Metric: ROC-AUC
Features: 25 numerical/categorical features including tenure, monthly_charges, total_charges, contract_type.
Identify missing values, imbalance, and data leakage risks."""
}

PLANNER_PROMPT = {
    "role": "planner",
    "system": "You are the strategic Planner Agent in an autonomous ML engineering system. Design the next experiment spec as valid JSON.",
    "user": """Design experiment exp_001 for Kaggle Customer Churn Benchmark.
Modality: Tabular
Target: churn (ROC-AUC)
Reasoning Mode: ToT (Tree-of-Thought)
Formulate 3 candidate directions (Feature Engineering, Model Selection, Hyperparameter Tuning), score each, and elaborate the winner into a full experiment spec JSON."""
}

CODER_PROMPT = {
    "role": "coder",
    "system": "You are the Coder Agent. Implement Planner's spec into validated executable Python code with 5-fold StratifiedKFold CV.",
    "user": """Implement Python code for experiment exp_001:
Model Family: LightGBM
Modality: Tabular
Feature Engineering: Target encoding for categorical columns, ratio features (total_charges / tenure).
CV: 5-Fold StratifiedKFold. Save submission.csv."""
}

SELECTOR_PROMPT = {
    "role": "selector",
    "system": "You are the Selector Agent. Analyze experiment_log.jsonl and output a redirect JSON or convergence verdict JSON.",
    "user": """Evaluate the following experiment log:
[
  {"experiment_id": "exp_001", "model_type": "LightGBM", "cv_mean": 0.820, "cv_std": 0.005, "submission_score": 0.815},
  {"experiment_id": "exp_002", "model_type": "CatBoost", "cv_mean": 0.845, "cv_std": 0.004, "submission_score": 0.841},
  {"experiment_id": "exp_003", "model_type": "XGBoost", "cv_mean": 0.852, "cv_std": 0.005, "submission_score": 0.848},
  {"experiment_id": "exp_004", "model_type": "LightGBM_tuned", "cv_mean": 0.853, "cv_std": 0.004, "submission_score": 0.849},
  {"experiment_id": "exp_005", "model_type": "LightGBM_fe", "cv_mean": 0.8532, "cv_std": 0.004, "submission_score": 0.8491}
]
Check plateau rule (N=3, relative epsilon=0.005). Return JSON verdict."""
}

BENCHMARK_PROMPTS = [
    DATA_EXPLORER_PROMPT,
    PLANNER_PROMPT,
    CODER_PROMPT,
    SELECTOR_PROMPT
]
