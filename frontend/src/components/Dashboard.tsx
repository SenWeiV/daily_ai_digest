import {
  Github,
  Youtube,
  Mail,
  Clock,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import type { SystemStatus, DigestRecord } from "../types";

interface DashboardProps {
  status: SystemStatus | null;
  digest: DigestRecord | null;
  loading: boolean;
}

function Dashboard({ status, digest, loading }: DashboardProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="surface rounded-2xl p-6 animate-pulse">
            <div className="h-4 bg-neutral-800 rounded w-1/2 mb-4"></div>
            <div className="h-8 bg-neutral-800 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  const stats = [
    {
      label: "GitHub 热门项目",
      value: digest?.github_data?.length || 0,
      icon: Github,
      color: "text-emerald-300",
      bgColor: "bg-emerald-400/10",
      configured: status?.github_configured,
    },
    {
      label: "YouTube 热门视频",
      value: digest?.youtube_data?.length || 0,
      icon: Youtube,
      color: "text-red-300",
      bgColor: "bg-red-400/10",
      configured: status?.youtube_configured,
    },
    {
      label: "邮件状态",
      value: digest?.email_sent ? "已发送" : "未发送",
      icon: Mail,
      color: digest?.email_sent ? "text-sky-300" : "text-neutral-400",
      bgColor: digest?.email_sent ? "bg-sky-400/10" : "bg-neutral-800/40",
      configured: status?.email_configured,
    },
    {
      label: "下次执行",
      value: status?.next_execution
        ? new Date(status.next_execution).toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
          })
        : "--:--",
      icon: Clock,
      color: "text-violet-300",
      bgColor: "bg-violet-400/10",
      configured: true,
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
      {stats.map((stat) => {
        const Icon = stat.icon;
        return (
          <div
            key={stat.label}
            className="surface rounded-2xl p-6 transition-colors duration-300 hover:bg-neutral-900/70"
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-neutral-400 text-sm font-light">
                {stat.label}
              </span>
              <div
                className={`${stat.bgColor} p-2 rounded-lg border border-neutral-800`}
              >
                <Icon className={`w-5 h-5 ${stat.color}`} />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-2xl font-light ${stat.color}`}>
                {stat.value}
              </span>
              {stat.configured !== undefined && (
                <span className="flex items-center text-xs text-neutral-400">
                  {stat.configured ? (
                    <CheckCircle className="w-4 h-4 text-emerald-400 mr-1" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-orange-400 mr-1" />
                  )}
                  {stat.configured ? "已配置" : "未配置"}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default Dashboard;
