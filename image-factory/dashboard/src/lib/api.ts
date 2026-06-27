const API_BASE = "/api/v1";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function getToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem("auth_session");
  if (!stored) return null;
  try {
    const parsed = JSON.parse(stored);
    return parsed?.state?.token ?? parsed?.token ?? null;
  } catch {
    return null;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(
      body || `Request failed: ${response.status}`,
      response.status
    );
  }

  return response.json();
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([_, v]) => v !== undefined);
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

export const api = {
  getToken,

  // Auth
  login: (email: string, password: string) =>
    request<{ token: string; user: any }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (name: string, email: string, password: string) =>
    request<{ token: string; user: any }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),

  forgotPassword: (email: string) =>
    request<{ message: string }>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, password: string) =>
    request<{ message: string }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),

  getProfile: () => request<any>("/auth/me"),

  // API Keys
  getApiKeys: () => request<any[]>("/users/api-keys"),
  createApiKey: (name: string) =>
    request<{ key: string; id: string }>("/users/api-keys", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteApiKey: (id: string) =>
    request<void>(`/users/api-keys/${id}`, { method: "DELETE" }),

  // Dashboard
  getDashboardStats: () => request<any>("/dashboard/stats"),
  getActiveJobs: () => request<any[]>("/dashboard/active"),
  getSystemStatus: () => request<any>("/dashboard/status"),
  getQueueInfo: () => request<any>("/dashboard/queue"),

  // Projects
  listProjects: (params?: { status?: string; limit?: number; offset?: number }) =>
    request<{ projects: any[]; total: number }>(
      `/projects${buildQuery(params || {})}`
    ),

  getProject: (id: string) => request<any>(`/projects/${id}`),
  createProject: (data: { name: string; description?: string }) =>
    request<any>("/projects", { method: "POST", body: JSON.stringify(data) }),
  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: "DELETE" }),

  // Products within a project
  getProjectProducts: (projectId: string, params?: { status?: string; limit?: number; offset?: number }) =>
    request<{ products: any[]; total: number }>(
      `/projects/${projectId}/products${buildQuery(params || {})}`
    ),

  getProduct: (projectId: string, productId: string) =>
    request<any>(`/projects/${projectId}/products/${productId}`),

  // Upload
  uploadFile: async (file: File, projectId: string) => {
    const token = await getToken();
    const form = new FormData();
    form.append("file", file);
    form.append("project_id", projectId);
    const response = await fetch(`${API_BASE}/products/upload`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(body || `Upload failed: ${response.status}`, response.status);
    }
    return response.json();
  },

  // Submit generation with user config
  submitGeneration: async (data: {
    batch_id: string;
    project_id?: string;
    num_images_per_product: number;
    image_descriptions: string[];
    prompt_template?: string;
  }) => request<any>("/products/generate", {
    method: "POST",
    body: JSON.stringify(data),
  }),

  // Assets
  listAssets: (params?: {
    project_id?: string;
    status?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) =>
    request<{ assets: any[]; total: number }>(
      `/assets${buildQuery(params || {})}`
    ),

  getAsset: (id: string) => request<any>(`/assets/${id}`),

  // Jobs
  listJobs: (params?: {
    status?: string;
    project?: string;
    limit?: number;
    offset?: number;
  }) =>
    request<{ jobs: any[]; total: number }>(
      `/jobs${buildQuery(params || {})}`
    ),

  getJob: (id: string) => request<any>(`/jobs/${id}`),
  retryJob: (id: string) =>
    request<any>(`/jobs/${id}/retry`, { method: "POST" }),
  cancelJob: (id: string) =>
    request<any>(`/jobs/${id}/cancel`, { method: "POST" }),

  // Analytics
  getAnalytics: (params?: { days?: number }) =>
    request<any>(`/analytics${buildQuery(params || {})}`),

  // Admin
  getAdminStats: () => request<any>("/admin/stats"),
  listUsers: () => request<{ users: any[] }>("/admin/users"),
  getAdminNotifications: () => request<{ notifications: any[] }>("/admin/notifications"),
  clearAdminNotifications: () => request<void>("/admin/notifications", { method: "DELETE" }),
  retryAllFailed: () => request<any>("/admin/jobs/retry-all-failed", { method: "POST" }),
  clearCompletedJobs: () => request<any>("/admin/jobs/clear-completed", { method: "DELETE" }),
  getQueueStatus: () => request<any>("/admin/queue/status"),
  pauseQueue: () => request<any>("/admin/queue/pause", { method: "POST" }),
  resumeQueue: () => request<any>("/admin/queue/resume", { method: "POST" }),

  // Google Drive - Service Account
  saveDriveCredentials: (credentialsJson: string) =>
    request<any>("/google-drive/credentials", {
      method: "POST",
      body: JSON.stringify({ credentials_json: credentialsJson }),
    }),
  getDriveCredentials: () => request<{ configured: boolean; client_email: string }>("/google-drive/credentials"),
  testDriveConnection: () => request<any>("/google-drive/test", { method: "POST" }),
  getDriveStatus: () => request<any>("/google-drive/auth/status"),
  disconnectDrive: () => request<any>("/google-drive/auth/disconnect", { method: "POST" }),
  getDriveConfig: () => request<any>("/google-drive/config"),
  updateDriveConfig: (data: { root_folder?: string; auto_upload?: boolean }) =>
    request<any>(`/google-drive/config${buildQuery(data)}`, { method: "PUT" }),
  listDriveFiles: (folderId?: string) =>
    request<any>(`/google-drive/list${folderId ? `?folder_id=${folderId}` : ""}`),

  // Notifications
  getNotifications: (params?: { unread_only?: boolean }) =>
    request<{ notifications: any[]; unread_count: number }>(
      `/notifications${buildQuery(params || {})}`
    ),

  markNotificationRead: (id: string) =>
    request<void>(`/notifications/${id}/read`, { method: "POST" }),

  markAllNotificationsRead: () =>
    request<void>("/notifications/read-all", { method: "POST" }),

  // Templates
  getTemplates: (category?: string) =>
    request<{ templates: any[] }>(
      `/templates${category ? `?category=${category}` : ""}`
    ),

  // Verification
  startSmokeTest: () => request<any>("/verification/smoke-test", { method: "POST" }),
  getSmokeTestStatus: () => request<any>("/verification/smoke-test/status"),
  getSmokeTestLatest: () => request<any>("/verification/smoke-test/latest"),
  runDryRun: () => request<any>("/verification/dry-run", { method: "POST" }),
  getSystemReadiness: () => request<any>("/verification/ready"),

  // Content (Product Links Tracking)
  getContentProducts: (params?: { status?: string; search?: string; project_id?: string; limit?: number; offset?: number }) =>
    request<{ products: any[]; total: number }>(
      `/content/products${buildQuery(params || {})}`
    ),

  getProductDetail: (id: string) =>
    request<any>(`/content/products/${id}`),

  retryContentProduct: (id: string) =>
    request<any>(`/content/products/${id}/retry`, { method: "POST" }),

  getContentStats: () =>
    request<any>("/content/products/stats"),

  // Credit Check
  checkCredits: (data: { batch_id: string; num_images_per_product?: number }) =>
    request<any>("/products/check-credits", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Provider Keys
  getProviderKeys: () => request<any>("/admin/provider-keys"),

  // Image-to-Image Model Settings
  getImg2imgSettings: () => request<any>("/admin/settings/img2img"),
  updateImg2imgSettings: (model: string) =>
    request<any>("/admin/settings/img2img", { method: "PUT", body: JSON.stringify({ img2img_model: model }) }),

  // Storage / Output Directory Settings
  getStorageSettings: () => request<any>("/admin/settings/storage"),
  updateStorageSettings: (storagePath: string) =>
    request<any>("/admin/settings/storage", { method: "PUT", body: JSON.stringify({ storage_local_path: storagePath }) }),

  // Clear all data for fresh start
  clearAllData: () =>
    request<{ status: string; deleted_product_links: number; deleted_jobs: number; deleted_assets: number; deleted_redis_keys: number; message: string }>(
      "/admin/data/clear-all",
      { method: "DELETE" }
    ),

  // Scrapfly Usage
  getScrapflyUsage: () => request<any>("/admin/scrapfly/usage"),

  // Intelligence / CAPTCHA
  getCaptchaIntelligence: () => request<any>("/dashboard/captcha"),

  // AI Limiter (budget consumption)
  getAiLimiter: () => request<any>("/dashboard/ai-limiter"),
};
