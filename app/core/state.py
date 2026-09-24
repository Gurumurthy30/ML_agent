from enum import Enum
from typing import Literal, TypedDict, Any
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    BINARY_CLASSIFICATION = "binary_classification"
    MULTICLASS_CLASSIFICATION = "multiclass_classification"
    REGRESSION = "regression"
    AMBIGUOUS = "ambiguous"


class ProjectState(TypedDict):
    project_id: str
    run_id: str
    user_goal: str
    target_column: str | None
    target_metric: str | None          # e.g. "f1", "roc_auc", "rmse", "r2"
    description: str | None
    constraints: dict

    dataset_id: str
    dataset_version: str

    task_type: TaskType | None

    profile_summary: dict
    eda_findings: dict
    feature_summary: dict
    model_summary: dict
    evaluation_summary: dict

    current_stage: str
    iteration: int
    max_iterations: int

    best_experiment_id: str | None     # MLflow run_id
    best_metric_value: float | None

    supervisor_memory: dict
    artifacts: list[dict]              # references only, never raw content

    next_action: str | None
    status: Literal["SUCCESS", "FAILED", "NEEDS_INPUT", "RETRY", "RUNNING"]


# --- Structured Output Models for Agents ---

from pydantic import BaseModel, Field, field_validator


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    missing_count: int
    missing_pct: float
    unique_count: int
    is_constant: bool
    sample_values: list[Any] = Field(default_factory=list)


class ProfileSummary(BaseModel):
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    target_column: str | None = None
    task_type_guess: TaskType
    duplicates_count: int
    missing_total_pct: float
    target_distribution: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class EDAFindingItem(BaseModel):
    category: str = Field(description="e.g. correlation, skewness, outliers, leakage, class_imbalance")
    finding: str = Field(description="Clear statement of what was discovered")
    evidence: str = Field(description="Numerical statistics or evidence supporting the finding")
    implication: str = Field(description="Impact on modeling or feature engineering")
    recommendation: str = Field(description="Actionable suggestion for feature engineering")


class EDAOutput(BaseModel):
    executive_summary: str
    findings: list[EDAFindingItem]
    leakage_risks: list[str] = Field(default_factory=list)
    suggested_feature_ideas: list[str] = Field(default_factory=list)

    @field_validator("leakage_risks", "suggested_feature_ideas", mode="before")
    @classmethod
    def coerce_to_strings(cls, v):
        if isinstance(v, list):
            coerced = []
            for item in v:
                if isinstance(item, dict):
                    coerced.append(" | ".join(f"{k}: {val}" for k, val in item.items()))
                else:
                    coerced.append(str(item))
            return coerced
        return v



class FeatureMetadataItem(BaseModel):
    feature_name: str
    source_columns: list[str]
    transformation: str
    reason: str
    eda_evidence: str
    leakage_check: str
    inference_available: bool = True


class FeatureEngineeringOutput(BaseModel):
    version: str
    created_features: list[FeatureMetadataItem]
    pipeline_file: str
    data_file: str
    schema_file: str
    notes: str


class TrainedModelResult(BaseModel):
    model_name: str
    model_family: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    train_score: float
    val_score: float
    metrics: dict[str, float] = Field(default_factory=dict)
    mlflow_run_id: str
    model_path: str


class ModelStageOutput(BaseModel):
    validation_strategy: str
    target_metric: str
    trained_models: list[TrainedModelResult]
    best_model_name: str
    best_mlflow_run_id: str
    best_score: float
    summary: str


from pydantic import BaseModel, Field, field_validator, model_validator


class EvaluatorIssue(BaseModel):
    check_name: str = "general_check"
    severity: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    description: str = ""
    suggested_fix: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_issue(cls, data: Any) -> Any:
        if isinstance(data, dict):
            c_name = data.get("check_name") or data.get("issue") or data.get("name") or "model_check"
            sev = str(data.get("severity", "MEDIUM")).upper()
            if sev not in ("HIGH", "MEDIUM", "LOW"):
                sev = "MEDIUM"
            desc = data.get("description") or data.get("issue") or data.get("details") or str(data)
            fix = data.get("suggested_fix") or data.get("fix") or data.get("recommendation") or "Apply regularization or review features."
            return {
                "check_name": str(c_name),
                "severity": sev,
                "description": str(desc),
                "suggested_fix": str(fix),
            }
        elif isinstance(data, str):
            return {
                "check_name": "check",
                "severity": "MEDIUM",
                "description": data,
                "suggested_fix": "Review model",
            }
        return data


class EvaluatorOutput(BaseModel):
    verdict: Literal["PASS", "IMPROVE"] = "PASS"
    target_metric: str = "metric"
    primary_metric_value: float = 0.0
    issues_found: list[EvaluatorIssue] = Field(default_factory=list)
    recommended_next_stage: Literal["feature_engineering", "model"] = "feature_engineering"
    reasoning: str = ""


class ReportSummaryOutput(BaseModel):
    project_id: str
    objective: str
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    best_model_name: str = "best_model"
    best_score: float | None = 0.0
    metric_name: str = "metric"
    iterations_run: int | None = 1
    key_findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def clean_report_summary(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if data.get("best_score") is None:
                data["best_score"] = 0.0
            if data.get("iterations_run") is None:
                data["iterations_run"] = 1
        return data

    @field_validator("key_findings", "recommendations", "limitations", mode="before")
    @classmethod
    def coerce_to_strings(cls, v):
        if isinstance(v, list):
            coerced = []
            for item in v:
                if isinstance(item, dict):
                    coerced.append(" | ".join(f"{k}: {val}" for k, val in item.items()))
                else:
                    coerced.append(str(item))
            return coerced
        return v



class SupervisorReview(BaseModel):
    action: Literal["PROCEED", "RETRY", "IMPROVE", "COMPLETE", "FAIL"]
    next_stage: str
    reasoning: str
    instructions_for_next_stage: str
