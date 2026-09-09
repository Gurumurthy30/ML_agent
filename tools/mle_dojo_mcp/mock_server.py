import ast
import random
import time
from typing import Dict, Any, List

class MLEDojoMockServer:
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.step_count = 0
        self.base_cv = 0.800

    def request_info(self) -> Dict[str, Any]:
        """Returns synthetic dataset and task context info."""
        return {
            "task_id": "kaggle_tabular_mock_01",
            "task_name": "Customer Churn Prediction Benchmark",
            "modality": "tabular",
            "target_column": "churn",
            "metric": "roc_auc",
            "train_shape": [10000, 25],
            "test_shape": [2500, 24],
            "features": {
                "numerical": ["tenure", "monthly_charges", "total_charges", "num_support_tickets"],
                "categorical": ["contract_type", "payment_method", "internet_service"],
                "binary": ["senior_citizen", "partner", "dependents"]
            },
            "sample_submission_format": {
                "id_column": "customer_id",
                "pred_column": "churn"
            },
            "description": "Synthetic benchmark task for predicting customer churn. Metric is ROC-AUC."
        }

    def validate_code(self, code: str) -> Dict[str, Any]:
        """Performs static AST syntax validation on python code."""
        if not code or not code.strip():
            return {"valid": False, "error": "Code string is empty."}
        try:
            ast.parse(code)
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {
                "valid": False,
                "error": f"SyntaxError on line {e.lineno}, col {e.offset}: {e.msg}"
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def execute_code(self, code: str) -> Dict[str, Any]:
        """Simulates code execution on MLE-Dojo environment and returns benchmark score."""
        val_res = self.validate_code(code)
        if not val_res["valid"]:
            result = {
                "status": "error",
                "cv_mean": 0.0,
                "cv_std": 0.0,
                "submission_score": 0.0,
                "error": val_res["error"],
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            self.history.append(result)
            return result

        self.step_count += 1
        
        # Simulate convergence plateau after a few steps
        if self.step_count == 1:
            cv_mean = 0.820
        elif self.step_count == 2:
            cv_mean = 0.845
        elif self.step_count == 3:
            cv_mean = 0.852
        elif self.step_count == 4:
            cv_mean = 0.853  # Plateauing (<0.5% relative change from 0.852)
        elif self.step_count == 5:
            cv_mean = 0.8532 # Plateauing
        else:
            cv_mean = 0.8533 # Plateauing

        cv_std = round(random.uniform(0.003, 0.008), 4)
        submission_score = round(cv_mean - random.uniform(0.001, 0.005), 4)

        result = {
            "status": "success",
            "cv_mean": round(cv_mean, 4),
            "cv_std": cv_std,
            "submission_score": submission_score,
            "error": None,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
        self.history.append(result)
        return result

    def get_history(self) -> List[Dict[str, Any]]:
        return self.history

    def reset(self) -> Dict[str, Any]:
        self.history = []
        self.step_count = 0
        return {"status": "reset_success"}
