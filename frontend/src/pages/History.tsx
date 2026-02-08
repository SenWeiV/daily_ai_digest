import { useState, useEffect } from 'react'
import { Calendar, ChevronRight, Github, Youtube, Mail, CheckCircle, XCircle } from 'lucide-react'
import { digestApi } from '../services/api'
import GitHubList from '../components/GitHubList'
import YouTubeList from '../components/YouTubeList'
import DetailModal from '../components/DetailModal'
import type { DigestRecordBrief, DigestRecord, GitHubDigestItem, YouTubeDigestItem } from '../types'

function History() {
  const [historyList, setHistoryList] = useState<DigestRecordBrief[]>([])
  const [selectedRecord, setSelectedRecord] = useState<DigestRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [selectedItem, setSelectedItem] = useState<GitHubDigestItem | YouTubeDigestItem | null>(null)
  const [selectedType, setSelectedType] = useState<'github' | 'youtube'>('github')
  const [activeTab, setActiveTab] = useState<'github' | 'youtube'>('github')

  // 加载历史列表
  useEffect(() => {
    const loadHistory = async () => {
      try {
        setLoading(true)
        const response = await digestApi.getHistory(30, 0)
        setHistoryList(response.items)
      } catch (error) {
        console.error('加载历史记录失败:', error)
      } finally {
        setLoading(false)
      }
    }
    loadHistory()
  }, [])

  // 加载指定日期的详情
  const loadDetail = async (date: string) => {
    try {
      setDetailLoading(true)
      const record = await digestApi.getByDate(date)
      setSelectedRecord(record)
    } catch (error) {
      console.error('加载详情失败:', error)
    } finally {
      setDetailLoading(false)
    }
  }

  // 格式化日期
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      weekday: 'short',
    })
  }

  return (
    <div className="flex gap-6">
      {/* 左侧历史列表 */}
      <div className="w-80 flex-shrink-0">
        <h2 className="text-xl font-bold text-gray-900 mb-4">历史记录</h2>
        
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="bg-white rounded-lg p-4 shadow-sm animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-3/4 mb-2"></div>
                <div className="h-3 bg-gray-200 rounded w-1/2"></div>
              </div>
            ))}
          </div>
        ) : historyList.length === 0 ? (
          <div className="bg-white rounded-lg p-8 shadow-sm text-center">
            <Calendar className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">暂无历史记录</p>
          </div>
        ) : (
          <div className="space-y-2 max-h-[calc(100vh-200px)] overflow-y-auto">
            {historyList.map((item) => (
              <button
                key={item.id}
                onClick={() => loadDetail(item.digest_date)}
                className={`w-full text-left bg-white rounded-lg p-4 shadow-sm border transition-all ${
                  selectedRecord?.digest_date === item.digest_date
                    ? 'border-indigo-500 ring-2 ring-indigo-100'
                    : 'border-gray-100 hover:border-gray-200'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium text-gray-900">
                    {formatDate(item.digest_date)}
                  </span>
                  <ChevronRight className="w-4 h-4 text-gray-400" />
                </div>
                <div className="flex items-center space-x-4 text-sm text-gray-500">
                  <span className="flex items-center">
                    <Github className="w-4 h-4 mr-1 text-green-600" />
                    {item.github_count}
                  </span>
                  <span className="flex items-center">
                    <Youtube className="w-4 h-4 mr-1 text-red-600" />
                    {item.youtube_count}
                  </span>
                  <span className="flex items-center">
                    {item.email_sent ? (
                      <CheckCircle className="w-4 h-4 text-green-500" />
                    ) : (
                      <XCircle className="w-4 h-4 text-gray-300" />
                    )}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 右侧详情 */}
      <div className="flex-1">
        {!selectedRecord ? (
          <div className="bg-white rounded-xl p-12 shadow-sm text-center">
            <Calendar className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 text-lg">请从左侧选择一个日期查看详情</p>
          </div>
        ) : detailLoading ? (
          <div className="bg-white rounded-xl p-12 shadow-sm">
            <div className="animate-pulse space-y-4">
              <div className="h-8 bg-gray-200 rounded w-1/3"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
              <div className="h-64 bg-gray-200 rounded"></div>
            </div>
          </div>
        ) : (
          <div>
            {/* 日期标题 */}
            <div className="mb-6">
              <h2 className="text-2xl font-bold text-gray-900">
                {formatDate(selectedRecord.digest_date)}
              </h2>
              <div className="flex items-center space-x-4 mt-2 text-sm text-gray-500">
                <span className="flex items-center">
                  <Github className="w-4 h-4 mr-1 text-green-600" />
                  GitHub {selectedRecord.github_data?.length || 0} 个项目
                </span>
                <span className="flex items-center">
                  <Youtube className="w-4 h-4 mr-1 text-red-600" />
                  YouTube {selectedRecord.youtube_data?.length || 0} 个视频
                </span>
                {selectedRecord.email_sent && (
                  <span className="flex items-center text-green-600">
                    <Mail className="w-4 h-4 mr-1" />
                    已发送邮件
                  </span>
                )}
              </div>
            </div>

            {/* Tab 切换 */}
            <div className="flex space-x-1 mb-6 bg-gray-100 rounded-lg p-1 w-fit">
              <button
                onClick={() => setActiveTab('github')}
                className={`px-6 py-2 rounded-md font-medium transition-colors ${
                  activeTab === 'github'
                    ? 'bg-white text-green-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                🐙 GitHub
              </button>
              <button
                onClick={() => setActiveTab('youtube')}
                className={`px-6 py-2 rounded-md font-medium transition-colors ${
                  activeTab === 'youtube'
                    ? 'bg-white text-red-600 shadow-sm'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                📺 YouTube
              </button>
            </div>

            {/* 内容列表 */}
            {activeTab === 'github' ? (
              <GitHubList
                items={selectedRecord.github_data || []}
                onItemClick={(item) => {
                  setSelectedItem(item)
                  setSelectedType('github')
                }}
              />
            ) : (
              <YouTubeList
                items={selectedRecord.youtube_data || []}
                onItemClick={(item) => {
                  setSelectedItem(item)
                  setSelectedType('youtube')
                }}
              />
            )}
          </div>
        )}
      </div>

      {/* 详情弹窗 */}
      <DetailModal
        item={selectedItem}
        type={selectedType}
        onClose={() => setSelectedItem(null)}
      />
    </div>
  )
}

export default History