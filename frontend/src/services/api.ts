import {
  Project,
  Dataset,
  WorkflowRun,
  ArtifactIndex,
  ArtifactContent,
  DatasetPreview,
  LeaderboardResponse,
  EvaluationResponse,
  ReportResponse,
} from "../types";

const BASE_URL = "";

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errMsg = `Request failed: ${res.status} ${res.statusText}`;
    try {
      const errData = await res.json();
      if (errData.detail) errMsg = typeof errData.detail === "string" ? errData.detail : JSON.stringify(errData.detail);
    } catch {
      // ignore
    }
    throw new Error(errMsg);
  }
  return res.json();
}

export const api = {
  // Projects
  async getProjects(): Promise<Project[]> {
    const res = await fetch(`${BASE_URL}/projects`);
    return handleResponse<Project[]>(res);
  },

  async getProject(id: string): Promise<Project> {
    const res = await fetch(`${BASE_URL}/projects/${id}`);
    return handleResponse<Project>(res);
  },

  async createProject(data: { name: string; description?: string }): Promise<Project> {
    const res = await fetch(`${BASE_URL}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return handleResponse<Project>(res);
  },

  // Datasets
  async getDatasets(projectId: string): Promise<Dataset[]> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/datasets`);
    return handleResponse<Dataset[]>(res);
  },

  async uploadDataset(projectId: string, file: File): Promise<Dataset> {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${BASE_URL}/projects/${projectId}/datasets`, {
      method: "POST",
      body: formData,
    });
    return handleResponse<Dataset>(res);
  },

  async previewDataset(projectId: string, version: string): Promise<DatasetPreview> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/datasets/${version}/preview`);
    return handleResponse<DatasetPreview>(res);
  },

  // Runs
  async getRuns(projectId: string): Promise<WorkflowRun[]> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/runs`);
    return handleResponse<WorkflowRun[]>(res);
  },

  async getRun(projectId: string, runId: string): Promise<WorkflowRun> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/runs/${runId}`);
    return handleResponse<WorkflowRun>(res);
  },

  async triggerRun(
    projectId: string,
    payload: {
      target_column?: string;
      target_metric?: string;
      dataset_version?: string;
      constraints?: Record<string, any>;
    }
  ): Promise<WorkflowRun> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return handleResponse<WorkflowRun>(res);
  },

  // Artifacts
  async getArtifacts(projectId: string): Promise<ArtifactIndex[]> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/artifacts`);
    return handleResponse<ArtifactIndex[]>(res);
  },

  async getArtifactContent(projectId: string, artifactId: string): Promise<ArtifactContent> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/artifacts/${artifactId}/content`);
    return handleResponse<ArtifactContent>(res);
  },

  // Models & Leaderboard
  async getLeaderboard(projectId: string, metric: string = "f1"): Promise<LeaderboardResponse> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/models?metric=${encodeURIComponent(metric)}`);
    return handleResponse<LeaderboardResponse>(res);
  },

  async getExperiments(projectId: string): Promise<{ project_id: string; runs: any[] }> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/experiments`);
    return handleResponse<{ project_id: string; runs: any[] }>(res);
  },

  // Evaluation & Report
  async getEvaluation(projectId: string): Promise<EvaluationResponse> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/evaluation`);
    return handleResponse<EvaluationResponse>(res);
  },

  async getReport(projectId: string): Promise<ReportResponse> {
    const res = await fetch(`${BASE_URL}/projects/${projectId}/report`);
    return handleResponse<ReportResponse>(res);
  },

  // Kaggle Submission Predict
  async predictModel(
    projectId: string,
    experimentId: string,
    testFile: File,
    idColumn?: string
  ): Promise<string> {
    const formData = new FormData();
    formData.append("test_file", testFile);
    if (idColumn && idColumn.trim()) {
      formData.append("id_column", idColumn.trim());
    }
    const res = await fetch(`${BASE_URL}/projects/${projectId}/models/${experimentId}/predict`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      let errMsg = `Prediction failed (${res.status} ${res.statusText})`;
      try {
        const errJson = await res.json();
        if (errJson.detail) errMsg = typeof errJson.detail === "string" ? errJson.detail : JSON.stringify(errJson.detail);
      } catch {
        // ignore
      }
      throw new Error(errMsg);
    }
    return res.text();
  },
};

