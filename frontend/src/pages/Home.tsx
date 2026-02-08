import { useState, useEffect } from 'react'
import { RefreshCw, Calendar } from 'lucide-react'
import Dashboard from '../components/Dashboard'
import GitHubList from '../components/GitHubList'
import YouTubeList from '../components/YouTubeList'
import DetailModal from '../components/DetailModal'
import { digestApi, systemApi } from '../services/api'
import type { DigestRecord, SystemStatus, GitHubDigestItem, YouTubeDigestItem } from '../types'

function Home() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [digest, setDigest] = useState<DigestRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [selectedItem, setSelectedItem] = useState<GitHubDigestItem | YouTubeDigestItem | null>(null)
  const [selectedType, setSelectedType] = useState<'github' | 'youtube'>('github')
  const [activeTab, setActiveTab] = useState<'github' | 'youtube'>('github')

  // 加载数据
  const loadData = async () => {
    try {
      setLoading(true)
      const [statusData, digestData] = await Promise.all([
        systemApi.getStatus(),
        digestApi.getLatest(),
      ])
      setStatus(statusData)
      setDigest(digestData)
    } catch (error) {
      console.error('加载数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // 手动触发
  const handleTrigger = async () => {
    if (triggering) return
    
    try {
      setTriggering(true)
      const response = await digestApi.trigger({ force: false, send_email: true })
      if (response.success) {
        alert('摘要生成任务已启动，请稍后刷新查看结果')
      } else {
        alert(response.message)
      }
    } catch (error) {
      console.error('触发失败:', error)
      alert('触发失败，请检查配置')
    } finally {
      setTriggering(false)
    }
  }

  // 点击项目详情
  const handleGitHubClick = (item: GitHubDigestItem) => {
    setSelectedItem(item)
    setSelectedType('github')
  }

  const handleYouTubeClick = (item: YouTubeDigestItem) => {
    setSelectedItem(item)
    setSelectedType('youtube')
  }

  return (
    <div>
      {/* 页面标题 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">数据看板</h1>
          <p className="text-gray-500 mt-1">
            {digest?.digest_date
              ? `${digest.digest_date} 的 AI 热点情报`
              : '暂无数据'}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={loadData}
            className="inline-flex items-center px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="inline-flex items-center px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            <Calendar className={`w-4 h-4 mr-2 ${triggering ? 'animate-spin' : ''}`} />
            {triggering ? '生成中...' : '立即生成'}
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <Dashboard status={status} digest={digest} loading={loading} />

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
          🐙 GitHub Top {digest?.github_data?.length || 0}
        </button>
        <button
          onClick={() => setActiveTab('youtube')}
          className={`px-6 py-2 rounded-md font-medium transition-colors ${
            activeTab === 'youtube'
              ? 'bg-white text-red-600 shadow-sm'
              : 'text-gray-600 hover:text-gray-900'
          }`}
        >
          📺 YouTube Top {digest?.youtube_data?.length || 0}
        </button>
      </div>

      {/* 内容列表 */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-xl p-6 shadow-sm animate-pulse">
              <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
              <div className="h-4 bg-gray-200 rounded w-2/3 mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : (
        <>
          {activeTab === 'github' ? (
            <GitHubList
              items={digest?.github_data || []}
              onItemClick={handleGitHubClick}
            />
          ) : (
            <YouTubeList
              items={digest?.youtube_data || []}
              onItemClick={handleYouTubeClick}
            />
          )}
        </>
      )}

      {/* 详情弹窗 */}
      <DetailModal
        item={selectedItem}
        type={selectedType}
        onClose={() => setSelectedItem(null)}
      />
    </div>
  )
}

export default Home