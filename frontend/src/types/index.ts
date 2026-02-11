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

// YouTube 摘要项
export interface YouTubeDigestItem {
  video_id: string;
  title: string;
  channel: string;
  channel_url: string | null;
  video_url: string;
  thumbnail_url: string | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  published_at: string | null;
  duration: string | null;
  // Gemini 分析结果
  content_summary: string | null;
  key_points: string[];
  why_popular: string | null;
  practical_takeaways: string | null;
  recommended_for: string | null;
}

// 摘要记录
export interface DigestRecord {
  id: number | null;
  digest_date: string;
  github_data: GitHubDigestItem[];
  youtube_data: YouTubeDigestItem[];
  email_sent: boolean;
  email_sent_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// 摘要简要信息
export interface DigestRecordBrief {
  id: number;
  digest_date: string;
  github_count: number;
  youtube_count: number;
  email_sent: boolean;
  created_at: string | null;
}

// 执行日志
export interface ExecutionLog {
  id: number | null;
  execution_time: string;
  status: 'success' | 'failed' | 'running';
  github_count: number;
  youtube_count: number;
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
  youtube_configured: boolean;
  gemini_configured: boolean;
  email_configured: boolean;
}

// 配置信息
export interface AppConfig {
  schedule_hour: number;
  schedule_minute: number;
  timezone: string;
  github_top_n: number;
  youtube_top_n: number;
  ai_keywords: string[];
  gmail_sender: string;
  digest_recipient: string;
  github_configured: boolean;
  youtube_configured: boolean;
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
}

// 触发响应
export interface TriggerResponse {
  success: boolean;
  message: string;
  task_id: string | null;
  digest_date: string | null;
}

// YouTube 单视频分析请求
export interface YouTubeAnalyzeRequest {
  video_url?: string;
  video_id?: string;
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
