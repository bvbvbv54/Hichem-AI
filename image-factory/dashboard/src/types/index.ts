export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "user";
  created_at: string;
}

export interface AuthSession {
  user: User;
  token: string;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: "draft" | "uploading" | "processing" | "completed" | "failed";
  product_count: number;
  generated_image_count: number;
  created_at: string;
  updated_at: string;
}

export interface Product {
  id: string;
  project_id: string;
  url: string;
  status:
    | "waiting"
    | "extracting"
    | "translating"
    | "generating_images"
    | "delivering"
    | "completed"
    | "failed";
  generated_title: string;
  generated_description: string;
  images: Asset[];
  created_at: string;
}

export interface Asset {
  id: string;
  job_id: string;
  project_id?: string;
  filename: string;
  file_path: string;
  file_size: number;
  mime_type: string;
  width: number;
  height: number;
  created_at: string;
  thumbnail_url?: string;
}

export interface Job {
  id: string;
  type: string;
  status: string;
  prompt: string;
  enhanced_prompt: string;
  progress: number;
  error_message: string;
  project_name: string;
  num_images: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  assets: Asset[];
}

export interface ActiveJob {
  id: string;
  type: string;
  status: string;
  prompt: string;
  progress: number;
  project_name: string;
  num_images: number;
  error_message: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface PipelineEvent {
  type: string;
  job_id: string;
  timestamp: string;
  [key: string]: unknown;
}

export interface AdminNotification {
  id: string;
  code: string;
  severity: string;
  message: string;
  stage: string;
  job_id: string;
  retryable: boolean;
  timestamp: string;
}

export interface SystemStatus {
  api: "healthy" | "warning" | "offline";
  worker: "healthy" | "warning" | "offline";
  queue: "healthy" | "warning" | "offline";
  database: "healthy" | "warning" | "offline";
  storage: "healthy" | "warning" | "offline";
  delivery: "healthy" | "warning" | "offline";
}

export interface QueueInfo {
  current_length: number;
  active_jobs: number;
  waiting_jobs: number;
  failed_jobs: number;
  retry_jobs: number;
  estimated_completion_minutes: number;
  estimated_wait_minutes: number;
  workers_active: number;
}

export interface DashboardStats {
  total_products: number;
  products_in_queue: number;
  products_processing: number;
  products_completed: number;
  products_failed: number;
  total_images: number;
  ai_credits_used: number;
  estimated_cost: number;
  avg_processing_time_seconds: number;
}

export interface AnalyticsData {
  daily: DailyStats[];
  performance: PerformanceStats;
  costs: CostStats;
}

export interface DailyStats {
  date: string;
  products_processed: number;
  images_generated: number;
  credits_consumed: number;
  success_rate: number;
}

export interface PerformanceStats {
  avg_generation_time: number;
  avg_extraction_time: number;
  avg_delivery_time: number;
  success_rate: number;
  failed_rate: number;
}

export interface CostStats {
  image_generation_cost: number;
  storage_cost: number;
  total_cost: number;
}

export interface AdminStats {
  total_users: number;
  total_projects: number;
  total_jobs: number;
  total_api_usage: number;
  worker_stats: {
    active: number;
    available: number;
    max_concurrency: number;
  };
  queue_stats: QueueInfo;
  infrastructure: SystemStatus;
}

export interface Notification {
  id: string;
  type:
    | "upload_completed"
    | "processing_started"
    | "processing_finished"
    | "project_completed"
    | "generation_failed"
    | "delivery_completed"
    | "drive_saved"
    | "scraping_finished"
    | "scraping_failed";
  title: string;
  message: string;
  read: boolean;
  created_at: string;
  data?: {
    product_id?: string;
    product_name?: string;
    project_name?: string;
    batch_id?: string;
    url?: string;
    job_id?: string;
    failure_type?: string;
    failure_detail?: string;
    [key: string]: unknown;
  };
}

export interface Template {
  name: string;
  category: string;
  description: string;
  default_parameters: Record<string, string>;
  suggested_aspect_ratio: string;
  suggested_style: string;
}

export interface PerSiteSummary {
  domain: string;
  support_status: "working" | "known_issues" | "not_supported";
  total: number;
  pending: number;
  scraping: number;
  scraped: number;
  completed: number;
  failed: number;
  skipped: number;
  failed_breakdown: Record<string, number>;
  success_rate: number | null;
  today_count: number;
}

export interface AcquisitionStatsResponse {
  sites: PerSiteSummary[];
  totals: {
    total_products: number;
    today_products: number;
    pending: number;
    scraping: number;
    scraped: number;
    completed: number;
    failed: number;
  };
}

export interface AcquisitionJob {
  id: string;
  job_id: string;
  url: string;
  domain: string;
  site: string;
  status: string;
  product_name: string;
  image_count: number;
  error_message: string;
  failure_type: string;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
}

export interface AcquisitionJobsResponse {
  jobs: AcquisitionJob[];
  total: number;
  limit: number;
  offset: number;
}

export interface SubmitUrlsResponse {
  accepted: number;
  skipped_banned: number;
  skipped_duplicates: number;
  jobs: { url: string; job_id: string; domain: string }[];
}

export interface ScoreResponse {
  product_id: string;
  product_name: string;
  reference_count: number;
  images: ScoredImage[];
  weights: Record<string, number>;
  confidence: number;
  auto_select_ids: string[];
}

export interface ScoredImage {
  asset_id: string;
  filename: string;
  file_path: string;
  width: number;
  height: number;
  scores: {
    center: number;
    chinese: number;
    quality: number;
    detail: number;
  };
  image_score: number;
  auto_selected: boolean;
}

export interface ReferenceStatus {
  product_id: string;
  selected_count: number;
  approved: boolean;
  locked: boolean;
  can_generate: boolean;
}
