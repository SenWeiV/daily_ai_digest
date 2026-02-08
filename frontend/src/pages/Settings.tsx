import { useState, useEffect } from 'react'
import { Save, Send, RefreshCw, CheckCircle, XCircle, AlertCircle } from 'lucide-react'
import { configApi, emailApi, systemApi } from '../services/api'
import type { AppConfig, SystemStatus, ExecutionLog } from '../types'

function Settings() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [logs, setLogs] = useState<ExecutionLog[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [sendingTest, setSendingTest] = useState(false)

  // 加载数据
  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true)
        const [configData, statusData, logsData] = await Promise.all([
          configApi.get(),
          systemApi.getStatus(),
          systemApi.getLogs(20),
        ])
        setConfig(configData)
        setStatus(statusData)
        setLogs(logsData.items)
      } catch (error) {
        console.error('加载配置失败:', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  // 发送测试邮件
  const handleSendTestEmail = async () => {
    if (sendingTest) return
    
    try {
      setSendingTest(true)
      const response = await emailApi.sendTest()
      if (response.success) {
        alert('测试邮件发送成功！')
      } else {
        alert('发送失败: ' + response.message)
      }
    } catch (error) {
      console.error('发送测试邮件失败:', error)
      alert('发送失败，请检查邮件配置')
    } finally {
      setSendingTest(false)
    }
  }

  // 配置状态指示器
  const ConfigStatus = ({ configured }: { configured: boolean }) => (
    configured ? (
      <span className="flex items-center text-green-600 text-sm">
        <CheckCircle className="w-4 h-4 mr-1" />
        已配置
      </span>
    ) : (
      <span className="flex items-center text-orange-500 text-sm">
        <AlertCircle className="w-4 h-4 mr-1" />
        未配置
      </span>
    )
  )

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-1/4"></div>
        <div className="bg-white rounded-xl p-6 shadow-sm">
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-12 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">系统设置</h1>

      {/* API 配置状态 */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">API 配置状态</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-gray-700">Gemini API</span>
              <ConfigStatus configured={config?.gemini_configured || false} />
            </div>
            <p className="text-xs text-gray-500">用于AI内容分析</p>
          </div>
          
          <div className="p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-gray-700">GitHub Token</span>
              <ConfigStatus configured={config?.github_configured || false} />
            </div>
            <p className="text-xs text-gray-500">用于获取GitHub热门项目</p>
          </div>
          
          <div className="p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-gray-700">YouTube API</span>
              <ConfigStatus configured={config?.youtube_configured || false} />
            </div>
            <p className="text-xs text-gray-500">用于获取YouTube热门视频</p>
          </div>
          
          <div className="p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-gray-700">Gmail SMTP</span>
              <ConfigStatus configured={config?.email_configured || false} />
            </div>
            <p className="text-xs text-gray-500">用于发送每日摘要邮件</p>
          </div>
        </div>

        <div className="mt-6 p-4 bg-blue-50 rounded-lg">
          <p className="text-sm text-blue-700">
            ?? API 密钥需要在后端 <code className="bg-blue-100 px-1 rounded">.env</code> 文件中配置，请参考 <code className="bg-blue-100 px-1 rounded">.env.example</code> 文件。
          </p>
        </div>
      </div>

      {/* 调度配置 */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">调度配置</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              每日执行时间
            </label>
            <div className="flex items-center space-x-2">
              <input
                type="number"
                min="0"
                max="23"
                value={config?.schedule_hour || 8}
                className="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                readOnly
              />
              <span className="text-gray-500">:</span>
              <input
                type="number"
                min="0"
                max="59"
                value={config?.schedule_minute || 0}
                className="w-20 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                readOnly
              />
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              时区
            </label>
            <input
              type="text"
              value={config?.timezone || 'Asia/Shanghai'}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
              readOnly
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              下次执行时间
            </label>
            <input
              type="text"
              value={status?.next_execution 
                ? new Date(status.next_execution).toLocaleString('zh-CN')
                : '未调度'
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
              readOnly
            />
          </div>
        </div>
      </div>

      {/* 邮件设置 */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">邮件设置</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              发件人邮箱
            </label>
            <input
              type="text"
              value={config?.gmail_sender || '未配置'}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
              readOnly
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              收件人邮箱
            </label>
            <input
              type="text"
              value={config?.digest_recipient || '未配置'}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50"
              readOnly
            />
          </div>
        </div>
        
        <div className="mt-4">
          <button
            onClick={handleSendTestEmail}
            disabled={!config?.email_configured || sendingTest}
            className="inline-flex items-center px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className={`w-4 h-4 mr-2 ${sendingTest ? 'animate-pulse' : ''}`} />
            {sendingTest ? '发送中...' : '发送测试邮件'}
          </button>
        </div>
      </div>

      {/* 搜索关键词 */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">搜索关键词</h2>
        <div className="flex flex-wrap gap-2">
          {config?.ai_keywords?.map((keyword, index) => (
            <span
              key={index}
              className="px-3 py-1 bg-indigo-50 text-indigo-700 rounded-full text-sm"
            >
              {keyword}
            </span>
          ))}
        </div>
      </div>

      {/* 执行日志 */}
      <div className="bg-white rounded-xl p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">最近执行日志</h2>
        {logs.length === 0 ? (
          <p className="text-gray-500 text-center py-8">暂无执行记录</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">执行时间</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">状态</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">GitHub</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">YouTube</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">耗时</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">错误信息</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4 text-sm text-gray-900">
                      {new Date(log.execution_time).toLocaleString('zh-CN')}
                    </td>
                    <td className="py-3 px-4">
                      {log.status === 'success' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          成功
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                          <XCircle className="w-3 h-3 mr-1" />
                          失败
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">{log.github_count}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">{log.youtube_count}</td>
                    <td className="py-3 px-4 text-sm text-gray-600">
                      {log.duration_seconds ? `${log.duration_seconds.toFixed(1)}s` : '-'}
                    </td>
                    <td className="py-3 px-4 text-sm text-red-600 truncate max-w-xs">
                      {log.error_message || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default Settings