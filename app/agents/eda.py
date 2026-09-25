import json
from pathlib import Path
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage

from app.core.state import ProjectState, EDAOutput
from app.core.model_router import ModelRouter
from app.core.memory import get_stage_context
from app.agents.coder import CoderSubAgent
from app.tools.registry import ToolRegistry
from app.config import PROJECTS_DIR



EDA_SYSTEM_PROMPT = """You are an expert Tabular EDA (Exploratory Data Analysis) Agent. You decide which analyses actually matter for this dataset and task, direct their computation, and turn results into concise, actionable findings for the Feature Engineering and Model agents downstream.
 
You do not write or run code yourself — you decide what to check and interpret the numbers Coder returns.
 
BE ADAPTIVE, NOT A CHECKLIST
Do not run every possible analysis on every dataset. Choose what's relevant given the task type, dataset shape, and what you've already found. Worth considering, not mandatory:
- Numerical: skewness, distribution shape, outliers/high-leverage points, transform candidates
- Categorical: cardinality, rare categories, encoding implications
- Relationships: feature-target association, multicollinearity, redundant features
- Data quality: missingness patterns, duplicates, constant/near-constant columns
- Risk: leakage (ID-like columns, post-target-timing columns, target proxies), class imbalance (classification), temporal ordering issues (if any datetime columns exist)
 
HARD RULES
1. No charts, plots, or images of any kind — never suggest generating one. All evidence is numeric or tabular.
2. Never assert a finding without a computed number backing it. If the evidence doesn't exist yet, request it via Coder before reporting the finding.
3. Prefer fewer, higher-value findings over an exhaustive dump — every finding must be something Feature Engineering or Model could actually act on.
 
OUTPUT FORMAT
Every finding uses exactly this shape:
{
  "finding": "<one sentence, plain language>",
  "evidence": "<the specific number(s)/stat(s) that support it>",
  "implication": "<why this matters for modeling>",
  "recommendation": "<a concrete next step, e.g. 'test log1p transform', 'exclude column X — leakage risk'>",
  "severity": "info" | "warning" | "critical"
}
Return a JSON object with a "findings" array of these, plus a short "summary" string.
"""


def run_eda(state: ProjectState, router: ModelRouter, registry: ToolRegistry) -> dict[str, Any]:
    """Runs adaptive, LLM-driven EDA using Coder for computation and producing structured findings."""
    project_id = state["project_id"]
    tools = registry.get_tools_for_role("eda")
    coder_tools = registry.get_tools_for_role("coder")
    coder = CoderSubAgent(project_id, router, coder_tools.files, coder_tools.execution)

    ctx = get_stage_context(state, "eda")
    dataset_version = state.get("dataset_version", "dataset_v1")
    dataset_path = str(tools.dataset.get_dataset_path(dataset_version).resolve()).replace("\\", "/")
    target_col = state.get("target_column")
    task_type = state.get("task_type")

    # 1. Ask Coder to compute statistical summaries and save to JSON
    eda_script_task = f"""Write a Python script to compute statistical EDA metrics for a tabular dataset.
Dataset file path: '{dataset_path}'
Target column: '{target_col}'
Task type: '{task_type}'

Requirements:
1. Load dataset using pandas.
2. Compute:
   - Numerical feature statistics: skewness, min, max, median, 25%, 75%
   - Categorical feature statistics: cardinality, top 3 values with frequency percentages
   - Correlations: Pearson correlation with target (if numeric target) or between numerical features
   - Missingness rates per feature
   - Leakage check: features with near 1.0 correlation with target or identical unique ID counts
   - Class balance ratio (if classification)
3. Print the computed summary as a valid JSON object wrapped in <JSON_OUTPUT> and </JSON_OUTPUT> tags.
4. NO plotting libraries (do NOT import matplotlib/seaborn).
"""

    coder_res = coder.run_task(task_description=eda_script_task, context=ctx)
    stdout = coder_res.get("full_stdout", "")

    # Extract JSON or use stdout
    extracted_stats = {}
    if "<JSON_OUTPUT>" in stdout and "</JSON_OUTPUT>" in stdout:
        try:
            raw_json = stdout.split("<JSON_OUTPUT>")[1].split("</JSON_OUTPUT>")[0].strip()
            extracted_stats = json.loads(raw_json)
        except Exception:
            extracted_stats = {"raw_output": stdout[-1500:]}
    else:
        extracted_stats = {"raw_output": stdout[-1500:]}

    # 2. Use LLM with structured output to synthesize findings
    llm = router.get_model("eda", temperature=0.0)
    structured_llm = llm.with_structured_output(EDAOutput)

    prompt = f"""Review the statistical analysis of the tabular dataset:
Task Type: {task_type}
Target Column: {target_col}
User Goal: {state.get('user_goal')}
Profile Summary: {json.dumps(state.get('profile_summary', {}), indent=2)[:2000]}
Computed Statistics from Data:
{json.dumps(extracted_stats, indent=2)[:3000]}

Produce a comprehensive EDA report with:
- Executive summary of the data dynamics
- Structured findings (category, finding, evidence, implication, recommendation)
- Leakage risks detected
- Suggested feature engineering ideas
Remember: NO PLOTS, NO IMAGES.
"""

    eda_output: EDAOutput = structured_llm.invoke([
        SystemMessage(content=EDA_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    # 3. Save findings to disk
    eda_dir = PROJECTS_DIR / project_id / "eda"
    eda_dir.mkdir(parents=True, exist_ok=True)
    findings_json_path = eda_dir / "findings.json"
    summary_md_path = eda_dir / "summary.md"

    output_dict = eda_output.model_dump()
    tools.files.write_file("eda/findings.json", json.dumps(output_dict, indent=2))

    # Create summary.md (text-only)
    md_lines = [
        f"# EDA Findings: Project `{project_id}`",
        f"**Target Column:** `{target_col}` | **Task Type:** `{task_type}`",
        "",
        "## Executive Summary",
        eda_output.executive_summary,
        "",
        "## Leakage Risks",
    ]
    if eda_output.leakage_risks:
        for risk in eda_output.leakage_risks:
            md_lines.append(f"- [WARNING] {risk}")
    else:
        md_lines.append("- None detected.")

    md_lines.extend(["", "## Detailed Findings", "| Category | Finding | Evidence | Recommendation |", "|---|---|---|---|"])
    for f in eda_output.findings:
        clean_finding = f.finding.replace("|", "/")
        clean_ev = f.evidence.replace("|", "/")
        clean_rec = f.recommendation.replace("|", "/")
        md_lines.append(f"| {f.category} | {clean_finding} | {clean_ev} | {clean_rec} |")

    md_lines.extend(["", "## Suggested Feature Ideas"])
    for idea in eda_output.suggested_feature_ideas:
        md_lines.append(f"- {idea}")

    tools.files.write_file("eda/summary.md", "\n".join(md_lines))

    # Register artifacts
    art_json = tools.artifacts.register_artifact(
        project_id=project_id,
        artifact_type="eda_findings_json",
        path=str(findings_json_path),
        run_id=state.get("run_id"),
        version=dataset_version,
    )
    art_md = tools.artifacts.register_artifact(
        project_id=project_id,
        artifact_type="eda_summary_md",
        path=str(summary_md_path),
        run_id=state.get("run_id"),
        version=dataset_version,
    )

    artifacts_list = list(state.get("artifacts", []))
    artifacts_list.extend([art_json, art_md])

    return {
        "eda_findings": output_dict,
        "current_stage": "eda",
        "artifacts": artifacts_list,
        "status": "SUCCESS",
    }
