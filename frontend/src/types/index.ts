/**
 * TypeScript 类型定义
 */

// GitHub 摘要项
export interface GitHubDigestItem {
  repo_name: string;
  repo_url: string;
  stars: number;
  stars_today: number;
  forks: number;
  watchers: number;
  open_issues: number;
  recent_issue_comments: number | null;
  source_channel: 'trending' | 'search' | 'legacy';
  trending_rank: number | null;
  trending_period: 'daily' | 'weekly' | 'monthly' | null;
  recent_stars: number;
  recent_star_period_days: number;
  recent_star_velocity: number;
  description: string | null;
  main_language: string | null;
  topics: string[];
  created_at: string | null;
  updated_at: string | null;
  // Gemini 分析结果
  summary: string | null;
  why_trending: string | null;
  key_innovations: string[];
  practical_value: string | null;
  learning_points: string[];
}

// arXiv 摘要项
export interface ArxivDigestItem {
  arxiv_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  published_at: string | null;
  updated_at: string | null;
  version: string | null;
  arxiv_url: string;
  github_urls: string[];
  research_topics: string[];
  quality_evidence: string[];
  quality_grade: "A" | "B" | "C";
  related_repo_names: string[];
  summary: string | null;
  problem: string | null;
  method: string | null;
  evaluation: string | null;
  results: string | null;
  limitations: string | null;
}

// 摘要记录
export interface DigestRecord {
  id: number | null;
  digest_date: string;
  digest_type: string; // daily/weekly/monthly
  github_data: GitHubDigestItem[];
  arxiv_data: ArxivDigestItem[];
  email_sent: boolean;
  delivery_status?: 'pending' | 'sending' | 'sent' | 'failed' | 'partial' | 'unknown';
  email_sent_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// 摘要简要信息
export interface DigestRecordBrief {
  id: number;
  digest_date: string;
  github_count: number;
  arxiv_count: number;
  email_sent: boolean;
  created_at: string | null;
}

// 执行日志
export interface ExecutionLog {
  id: number | null;
  execution_time: string;
  status: 'success' | 'failed' | 'running';
  github_count: number;
  error_message: string | null;
  duration_seconds: number | null;
  created_at: string | null;
}

// 系统状态
export interface SystemStatus {
  status: string;
  version: string;
  last_execution: string | null;
  next_execution: string | null;
  database_connected: boolean;
  config_valid: boolean;
  github_configured: boolean;
  gemini_configured: boolean;
  email_configured: boolean;
}

// 配置信息
export interface AppConfig {
  schedule_hour: number;
  schedule_minute: number;
  timezone: string;
  github_top_n: number;
  ai_keywords: string[];
  gmail_sender: string;
  digest_recipient: string;
  github_configured: boolean;
  gemini_configured: boolean;
  email_configured: boolean;
}

// API 响应
export interface ApiResponse<T = unknown> {
  success: boolean;
  message: string;
  data?: T;
}

// 触发请求
export interface TriggerRequest {
  force: boolean;
  send_email: boolean;
  digest_type?: string; // daily/weekly/monthly，默认 daily
}

// 触发响应
export interface TriggerResponse {
  success: boolean;
  message: string;
  task_id: string | null;
  digest_date: string | null;
}

// 历史列表响应
export interface HistoryResponse {
  items: DigestRecordBrief[];
  total: number;
  limit: number;
  offset: number;
}

// 日志列表响应
export interface LogsResponse {
  items: ExecutionLog[];
  total: number;
}
