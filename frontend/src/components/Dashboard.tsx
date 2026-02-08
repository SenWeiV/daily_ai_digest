import { Github, Youtube, Mail, Clock, CheckCircle, AlertCircle } from 'lucide-react'
import type { SystemStatus, DigestRecord } from '../types'

interface DashboardProps {
  status: SystemStatus | null
  digest: DigestRecord | null
  loading: boolean
}

function Dashboard({ status, digest, loading }: DashboardProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
            <div className="h-8 bg-gray-200 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    )
  }

  const stats = [
    {
      label: 'GitHub 热门项目',
      value: digest?.github_data?.length || 0,
      icon: Github,
      color: 'text-green-600',
      bgColor: 'bg-green-50',
      configured: status?.github_configured,
    },
    {
      label: 'YouTube 热门视频',
      value: digest?.youtube_data?.length || 0,
      icon: Youtube,
      color: 'text-red-600',
      bgColor: 'bg-red-50',
      configured: status?.youtube_configured,
    },
    {
      label: '邮件状态',
      value: digest?.email_sent ? '已发送' : '未发送',
      icon: Mail,
      color: digest?.email_sent ? 'text-blue-600' : 'text-gray-400',
      bgColor: digest?.email_sent ? 'bg-blue-50' : 'bg-gray-50',
      configured: status?.email_configured,
    },
    {
      label: '下次执行',
      value: status?.next_execution
        ? new Date(status.next_execution).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })
        : '--:--',
      icon: Clock,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50',
      configured: true,
    },
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
      {stats.map((stat) => {
        const Icon = stat.icon
        return (
          <div
            key={stat.label}
            className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 card-hover"
          >
            <div className="flex items-center justify-between mb-4">
              <span className="text-gray-500 text-sm">{stat.label}</span>
              <div className={`${stat.bgColor} p-2 rounded-lg`}>
                <Icon className={`w-5 h-5 ${stat.color}`} />
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className={`text-2xl font-bold ${stat.color}`}>{stat.value}</span>
              {stat.configured !== undefined && (
                <span className="flex items-center text-xs">
                  {stat.configured ? (
                    <CheckCircle className="w-4 h-4 text-green-500 mr-1" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-orange-500 mr-1" />
                  )}
                  {stat.configured ? '已配置' : '未配置'}
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default Dashboard