/**
 * API 服务封装
 */

import axios from "axios";
import type {
  DigestRecord,
  SystemStatus,
  AppConfig,
  TriggerRequest,
  TriggerResponse,
  YouTubeAnalyzeRequest,
  YouTubeDigestItem,
  HistoryResponse,
  LogsResponse,
  ApiResponse,
} from "../types";

// GitHub Pages 场景：前端与后端不在同域，生产环境建议配置 VITE_API_BASE_URL
// - 本地开发：默认 '/api'，由 Vite proxy 转发到 http://localhost:8000
// - 线上部署：例如 'http://120.48.83.123:8000/api'
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "/api";

// 创建 axios 实例
const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 60000,
  headers: {
    "Content-Type": "application/json",
  },
});

// 响应拦截器
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("API Error:", error);
    return Promise.reject(error);
  },
);

/**
 * 摘要相关 API
 */
export const digestApi = {
  // 获取今日摘要
  getToday: async (): Promise<DigestRecord | null> => {
    const response = await api.get<DigestRecord | null>("/digest/today");
    return response.data;
  },

  // 获取最新摘要
  getLatest: async (): Promise<DigestRecord | null> => {
    const response = await api.get<DigestRecord | null>("/digest/latest");
    return response.data;
  },

  // 获取指定日期摘要
  getByDate: async (date: string): Promise<DigestRecord> => {
    const response = await api.get<DigestRecord>(`/digest/${date}`);
    return response.data;
  },

  // 获取历史记录
  getHistory: async (limit = 30, offset = 0, digestType = "daily"): Promise<HistoryResponse> => {
    const response = await api.get<HistoryResponse>("/digest/history", {
      params: { limit, offset, digest_type: digestType },
    });
    return response.data;
  },

  // 手动触发
  trigger: async (request: TriggerRequest): Promise<TriggerResponse> => {
    const response = await api.post<TriggerResponse>(
      "/digest/trigger",
      request,
    );
    return response.data;
  },
};

/**
 * 系统状态 API
 */
export const systemApi = {
  // 获取系统状态
  getStatus: async (): Promise<SystemStatus> => {
    const response = await api.get<SystemStatus>("/status");
    return response.data;
  },

  // 获取执行日志
  getLogs: async (limit = 50): Promise<LogsResponse> => {
    const response = await api.get<LogsResponse>("/logs", {
      params: { limit },
    });
    return response.data;
  },

  // 获取调度器信息
  getScheduler: async () => {
    const response = await api.get("/scheduler");
    return response.data;
  },
};

/**
 * 配置 API
 */
export const configApi = {
  // 获取配置
  get: async (): Promise<AppConfig> => {
    const response = await api.get<AppConfig>("/config");
    return response.data;
  },

  // 更新配置
  update: async (config: Partial<AppConfig>): Promise<ApiResponse> => {
    const response = await api.put<ApiResponse>("/config", config);
    return response.data;
  },
};

/**
 * 邮件 API
 */
export const emailApi = {
  // 发送测试邮件
  sendTest: async (recipient?: string): Promise<ApiResponse> => {
    const response = await api.post<ApiResponse>("/email/test", null, {
      params: recipient ? { recipient } : undefined,
    });
    return response.data;
  },
};

/**
 * YouTube 工具 API
 */
export const youtubeApi = {
  // 分析单个视频（URL/ID）
  analyze: async (
    request: YouTubeAnalyzeRequest,
  ): Promise<YouTubeDigestItem> => {
    const response = await api.post<YouTubeDigestItem>(
      "/youtube/analyze",
      request,
    );
    return response.data;
  },
};

export default api;
