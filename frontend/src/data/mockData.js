export const MOCK_AGENTS = [
  {
    id: 'planner',
    name: 'Planner Agent',
    role: 'Decomposes complex ML requirements into verified pipeline DAGs',
    color: '#DA7756', // Terracotta
    badge: 'Orchestrator',
    status: 'idle',
    model: 'qwen2.5-coder:32b',
    tools: ['rag_mcp', 'selector_mcp'],
  },
  {
    id: 'retriever',
    name: 'Retriever Agent',
    role: 'Fetches relevant algorithms, cheatsheets, and domain-specific code patterns',
    color: '#34D399', // Emerald
    badge: 'Knowledge Engine',
    status: 'idle',
    model: 'nomic-embed-text',
    tools: ['rag_mcp.query_cheatsheets', 'rag_mcp.query_library_docs'],
  },
  {
    id: 'coder',
    name: 'Coder Agent',
    role: 'Generates clean, vectorized Python code and scikit-learn/LightGBM pipelines',
    color: '#818CF8', // Indigo
    badge: 'Code Synthesizer',
    status: 'idle',
    model: 'qwen2.5-coder:32b',
    tools: ['local_env_mcp.run_python', 'local_env_mcp.write_file'],
  },
  {
    id: 'evaluator',
    name: 'Evaluator Agent',
    role: 'Analyzes model validation metrics, ROC-AUC curves, and feature importance',
    color: '#F43F5E', // Rose
    badge: 'Validation & Audit',
    status: 'idle',
    model: 'qwen2.5-coder:14b',
    tools: ['local_env_mcp.inspect_results'],
  },
];

export const MOCK_TOOLS = [
  {
    id: 'local_env_mcp',
    name: 'Local Environment MCP',
    category: 'Execution',
    description: 'Executes Python and shell scripts inside a secure local sandbox with GPU acceleration.',
    status: 'connected',
    endpoint: 'stdio://python -m tools.local_env_mcp.server',
    callsCount: 142,
  },
  {
    id: 'rag_mcp',
    name: 'RAG Knowledge MCP',
    category: 'Information Retrieval',
    description: 'Retrieves verified ML technique cheatsheets, hyperparameter strategies, and library docs.',
    status: 'connected',
    endpoint: 'stdio://python -m tools.rag_mcp.server',
    callsCount: 89,
  },
  {
    id: 'selector_mcp',
    name: 'Model Selector MCP',
    category: 'Architecture',
    description: 'Calculates suitability scores for algorithms based on dataset topology, cardinality, and task.',
    status: 'connected',
    endpoint: 'stdio://python -m tools.selector_mcp.server',
    callsCount: 37,
  },
  {
    id: 'data_profiler_mcp',
    name: 'Data Profiler MCP',
    category: 'Data Engineering',
    description: 'Inspects schema types, null ratios, distribution skewness, and target balance.',
    status: 'connected',
    endpoint: 'stdio://python -m tools.profiler.server',
    callsCount: 64,
  },
];

export const MOCK_PROJECTS = [
  { id: 'proj-1', name: 'Rainfall & Climate Prediction', chatsCount: 6, updatedAt: 'Just now' },
  { id: 'proj-2', name: 'Credit Default Risk Intelligence', chatsCount: 9, updatedAt: '2h ago' },
  { id: 'proj-3', name: 'Customer Churn & Retention v2', chatsCount: 4, updatedAt: 'Yesterday' },
];

export const MOCK_PINNED_SESSIONS = [
  {
    id: 'session-rainfall',
    title: 'Rainfall Prediction — Binary Classification & LightGBM',
    projectId: 'proj-1',
    mode: 'Local · Ollama',
    updatedAt: 'Just now',
  },
  {
    id: 'session-credit',
    title: 'Credit Default Risk — LightGBM & Feature Engineering',
    projectId: 'proj-2',
    mode: 'Local · GPU',
    updatedAt: '2h ago',
  },
];

export const MOCK_RECENT_SESSIONS = [
  {
    id: 'session-churn',
    title: 'Customer Churn — Imbalanced SMOTE vs Cost-Sensitive',
    projectId: 'proj-3',
    mode: 'Agent: Coder',
    updatedAt: 'Yesterday',
  },
  {
    id: 'session-sales',
    title: 'Time-Series Sales Forecasting — Lag Features & Prophet',
    projectId: 'proj-3',
    mode: 'Agent: Planner',
    updatedAt: '3d ago',
  },
];

export const INITIAL_CONVERSATIONS = {
  'session-rainfall': {
    id: 'session-rainfall',
    title: 'Rainfall Prediction — Binary Classification & LightGBM',
    mode: 'Local · Ollama (qwen2.5-coder)',
    project: 'Rainfall & Climate Prediction',
    messages: [
      {
        id: 'msg-rf-1',
        sender: 'assistant',
        timestamp: '11:20 AM',
        agents: ['Planner Agent'],
        thinking: {
          summary: 'Initialized environment and verified local Python 3.11 + LightGBM sandbox',
          duration: 'Thought for 4s',
          trace: [
            'System startup: Loaded local GPU drivers and MCP execution sandbox.',
            'Ready to ingest dataset schema and run automated multi-agent pipeline.'
          ]
        },
        prose: `Welcome to **ML Agent Studio**.

Upload your dataset or specify your prediction objective. The multi-agent swarm will autonomously:
1. Profile column distributions, null ratios, and class balance
2. Retrieve state-of-the-art architectures and loss functions
3. Run cross-validation in the local sandbox
4. Produce a **downloadable, production-ready model artifact** with inference code.`
      },
      {
        id: 'msg-rf-2',
        sender: 'user',
        timestamp: '11:22 AM',
        content: 'rainfall is the target column (binary class classification). Here is our training data. Train the best model and provide the final deliverable to download.',
        attachments: [
          { name: 'train.csv', size: '131.6 KB', type: 'text/csv' }
        ]
      },
      {
        id: 'msg-rf-3',
        sender: 'assistant',
        timestamp: '11:23 AM',
        agents: ['Planner Agent', 'Coder Agent', 'Evaluator Agent'],
        thinking: {
          summary: 'Analyzed train.csv schema, handled weather feature collinearity, configured 5-Fold Stratified LightGBM',
          duration: 'Thought for 14s',
          trace: [
            '1. Ingested train.csv (131.6 KB, 1,420 weather observations, 18 numerical meteorological variables).',
            '2. Target audit: "rainfall" binary column (0 = No Rain, 1 = Rain Tomorrow). Class distribution: 68.4% class 0, 31.6% class 1.',
            '3. Detected collinearity between atmospheric pressure (9am vs 3pm) and humidity. Imputed 0.8% missing values using median transforms.',
            '4. Chose LightGBM with histogram-based gradient boosting and early stopping on out-of-fold validation log-loss.',
            '5. Executed training in local sandbox: completed 5 folds with 0 runtime warnings.',
            '6. Serialized final booster weights to rainfall_lightgbm_v1.booster and generated inference wrapper.'
          ]
        },
        toolCalls: {
          summary: 'Ran 2 MCP tools (data_profiler, local_env sandbox)',
          calls: [
            {
              id: 'call-p1',
              tool: 'data_profiler_mcp.profile_csv',
              args: { file: 'train.csv', target: 'rainfall' },
              duration: '180ms',
              status: 'success',
              result: 'Profiled 1,420 rows, 18 columns. Class balance: 68.4% No Rain, 31.6% Rain. Missing values: 11 values across 2 columns.'
            },
            {
              id: 'call-e1',
              tool: 'local_env_mcp.run_python',
              args: { script: 'train_rainfall_model.py', folds: 5, seed: 42 },
              duration: '3.8s',
              status: 'success',
              result: 'Executed 5-fold Stratified CV. Saved weights -> rainfall_lightgbm_v1.booster (4.2 MB)'
            }
          ]
        },
        prose: `I have analyzed \`train.csv\` and trained a **5-Fold Stratified LightGBM Classifier** for rainfall prediction.

### Key Dataset & Modeling Insights:
* **Target Distribution**: \`68.4%\` dry days vs \`31.6%\` rainy days.
* **Top Predictive Features**: \`humidity_3pm\` (+34% importance), \`pressure_drop_24h\` (+22% importance), and \`cloud_cover_3pm\`.
* **Cross-Validation**: 5-Fold Stratified Out-of-Fold validation preventing data leakage and overfitting.`,
        terminalCard: {
          id: 'term-rf-1',
          title: 'Sandbox Execution — train_rainfall_model.py',
          language: 'python',
          lines: [
            '$ python train_rainfall_model.py --data train.csv --target rainfall --folds 5',
            '[11:22:45] [INFO] Loaded dataset: 1,420 rows, 18 features (target: rainfall)',
            '[11:22:46] [TRAIN] Fold 1/5: Early stopping at iter 142 — Val ROC-AUC: 0.8912 | F1: 0.819',
            '[11:22:47] [TRAIN] Fold 2/5: Early stopping at iter 165 — Val ROC-AUC: 0.8964 | F1: 0.825',
            '[11:22:48] [TRAIN] Fold 3/5: Early stopping at iter 138 — Val ROC-AUC: 0.8890 | F1: 0.814',
            '[11:22:49] [TRAIN] Fold 4/5: Early stopping at iter 154 — Val ROC-AUC: 0.8975 | F1: 0.828',
            '[11:22:50] [TRAIN] Fold 5/5: Early stopping at iter 149 — Val ROC-AUC: 0.8941 | F1: 0.821',
            '[11:22:51] [SUCCESS] 5-Fold Out-of-Fold ROC-AUC: 0.8936 (±0.0031) | Mean F1: 0.8214',
            '[11:22:51] [SUCCESS] Model serialized -> ./rainfall_lightgbm_v1.booster (4.2 MB)'
          ]
        },
        artifact: {
          name: 'rainfall_lightgbm_v1.booster',
          filename: 'rainfall_lightgbm_v1.booster',
          type: 'LightGBM Binary Classifier',
          size: '4.2 MB',
          description: 'Optimized 5-fold gradient boosted trees for rainfall prediction with calibrated probabilities.',
          metrics: {
            'ROC-AUC': '0.8936',
            'F1-Score': '0.8214',
            'Accuracy': '84.8%',
            'Latency': '1.2ms'
          },
          codeSnippet: `import lightgbm as lgb
import numpy as np
import pandas as pd

# Load the trained model deliverable
model = lgb.Booster(model_file="rainfall_lightgbm_v1.booster")

# Prepare new weather sample
sample = pd.DataFrame([{
    "humidity_9am": 74.0,
    "humidity_3pm": 82.0,
    "pressure_9am": 1012.4,
    "pressure_3pm": 1008.2,
    "temp_3pm": 19.8,
    "wind_speed_3pm": 28.0
}])

# Predict probability of rainfall
prob = model.predict(sample)[0]
print(f"Rainfall Probability: {prob:.1%}")
print(f"Prediction: {'Rain Tomorrow' if prob > 0.5 else 'No Rain'}")`
        },
        closingProse: `The trained model file is ready for download above. You can also export it to ONNX or view the Python inference snippet.`
      }
    ]
  },

  'session-credit': {
    id: 'session-credit',
    title: 'Credit Default Risk — LightGBM & Feature Engineering',
    mode: 'Local · GPU (CUDA 12.4)',
    project: 'Credit Default Risk Intelligence',
    messages: [
      {
        id: 'msg-c-1',
        sender: 'user',
        timestamp: '9:40 AM',
        content: 'We need to predict 90-day loan default risk on 150k applicant records with heavy class imbalance (6.2% default rate).',
        attachments: [
          { name: 'credit_default_2026.csv', size: '18.4 MB', type: 'text/csv' }
        ]
      },
      {
        id: 'msg-c-2',
        sender: 'assistant',
        timestamp: '9:42 AM',
        agents: ['Planner Agent', 'Coder Agent', 'Evaluator Agent'],
        thinking: {
          summary: 'Configured cost-sensitive scale_pos_weight = 15.1 and TreeSHAP waterfall explanations',
          duration: 'Thought for 18s',
          trace: [
            'Ingested credit_default_2026.csv (150k rows × 28 features).',
            'Applied stratified 5-fold cross-validation with custom pos_scale weights.',
            'Trained LightGBM booster achieving 0.8922 mean ROC-AUC.'
          ]
        },
        toolCalls: {
          summary: 'Ran 2 MCP tools (local_env, selector_mcp)',
          calls: [
            {
              id: 'call-c1',
              tool: 'local_env_mcp.run_python',
              args: { script: 'train_credit.py' },
              duration: '12.4s',
              status: 'success',
              result: 'Trained model saved -> credit_default_v1.booster'
            }
          ]
        },
        prose: `Trained a **cost-sensitive LightGBM default risk model** with \`scale_pos_weight=15.1\` to penalize false negatives.

* **5-Fold ROC-AUC**: \`0.8922\`
* **Mean PR-AUC**: \`0.6490\` (10× above random baseline).`,
        terminalCard: {
          id: 'term-c-1',
          title: 'Sandbox Execution — train_credit.py',
          language: 'python',
          lines: [
            '$ python train_credit.py --data credit_default_2026.csv',
            '[INFO] Stratified 5-Fold validation with scale_pos_weight=15.1',
            '[TRAIN] 5-Fold Mean ROC-AUC: 0.8922 (±0.0016) | Mean PR-AUC: 0.6490',
            '[SUCCESS] Model weights saved to ./credit_default_v1.booster (4.8 MB)'
          ]
        },
        artifact: {
          name: 'credit_default_v1.booster',
          filename: 'credit_default_v1.booster',
          type: 'Risk Scoring Booster',
          size: '4.8 MB',
          description: 'Production credit underwriting model with calibrated probabilities for loan officers.',
          metrics: {
            'ROC-AUC': '0.8922',
            'PR-AUC': '0.6490',
            'Inference Latency': '1.4ms'
          },
          codeSnippet: `import lightgbm as lgb
model = lgb.Booster(model_file="credit_default_v1.booster")
print("Model loaded successfully")`
        }
      }
    ]
  }
};
