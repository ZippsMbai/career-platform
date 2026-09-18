const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string) {
  localStorage.setItem("token", token);
}

export function clearToken() {
  localStorage.removeItem("token");
}

async function request(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  login: (email: string, password: string) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  listResumes: () => request("/resumes"),
  createResume: (label: string, raw_text: string) =>
    request("/resumes", { method: "POST", body: JSON.stringify({ label, raw_text }) }),
  uploadResume: async (label: string, file: File) => {
    const formData = new FormData();
    formData.append("label", label);
    formData.append("file", file);
    const res = await fetch(`${API_BASE}/resumes/upload`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Resume upload failed");
    }
    return res.json();
  },

  listJobs: () => request("/jobs"),
  createJob: (raw_text: string, title?: string, company?: string) =>
    request("/jobs", { method: "POST", body: JSON.stringify({ raw_text, title, company }) }),

  runAnalysis: (job_id: string, resume_id: string) =>
    request("/analyses", { method: "POST", body: JSON.stringify({ job_id, resume_id }) }),
  batchAnalyze: (resume_id: string, offset: number, location_filter: string) =>
    request(`/analyses/batch?offset=${offset}&location_filter=${location_filter}`, { method: "POST", body: JSON.stringify({ job_id: "", resume_id }) }) as Promise<{ results: any[]; remaining: number }>,
  listAnalysesForResume: (resume_id: string) => request(`/analyses?resume_id=${resume_id}`),

  listApplications: () => request("/applications"),
  createApplication: (job_id: string, analysis_id: string, status: string) =>
    request("/applications", { method: "POST", body: JSON.stringify({ job_id, analysis_id, status }) }),
  updateApplication: (id: string, patch: { status?: string; notes?: string }) =>
    request(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  deleteApplication: (id: string) =>
    request(`/applications/${id}`, { method: "DELETE" }),
  deleteJob: (id: string) =>
    request(`/jobs/${id}`, { method: "DELETE" }),
};