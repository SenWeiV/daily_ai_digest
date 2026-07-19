import { X, Star, GitFork, Eye, ThumbsUp, ExternalLink, Code, MessageCircle, TrendingUp } from 'lucide-react'
import type { GitHubDigestItem, YouTubeDigestItem } from '../types'

interface DetailModalProps {
  item: GitHubDigestItem | YouTubeDigestItem | null
  type: 'github' | 'youtube'
  onClose: () => void
}

function formatNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M'
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K'
  return num.toString()
}

function recentStarsLabel(item: GitHubDigestItem): string | null {
  const recentStars = item.recent_stars || item.stars_today
  if (recentStars <= 0) return null
  const labels = { daily: '今日', weekly: '本周', monthly: '本月' }
  const period = item.trending_period ? labels[item.trending_period] : '近期'
  return `${period} +${formatNumber(recentStars)}`
}

function DetailModal({ item, type, onClose }: DetailModalProps) {
  if (!item) return null

  const isGitHub = type === 'github'
  const githubItem = item as GitHubDigestItem
  const youtubeItem = item as YouTubeDigestItem

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* 背景遮罩 */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={onClose}
      />

      {/* 弹窗内容 */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-2xl shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto animate-fade-in">
          {/* 关闭按钮 */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-full hover:bg-gray-100 transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>

          {/* 头部 */}
          <div className={`p-6 border-b ${isGitHub ? 'border-l-4 border-l-green-500' : 'border-l-4 border-l-red-500'}`}>
            <div className="flex items-start gap-4">
              {!isGitHub && youtubeItem.thumbnail_url && (
                <img
                  src={youtubeItem.thumbnail_url}
                  alt={youtubeItem.title}
                  className="w-32 h-20 object-cover rounded-lg"
                />
              )}
              <div className="flex-1">
                <h2 className="text-xl font-bold text-gray-900 pr-8">
                  {isGitHub ? githubItem.repo_name : youtubeItem.title}
                </h2>
                <p className="text-gray-600 mt-1">
                  {isGitHub ? githubItem.description : `📺 ${youtubeItem.channel}`}
                </p>
                
                {/* 统计信息 */}
                <div className="flex items-center flex-wrap gap-4 mt-3 text-sm">
                  {isGitHub ? (
                    <>
                      <div className="flex items-center space-x-1 text-yellow-500" title="总 Star">
                        <Star className="w-4 h-4 fill-current" />
                        <span className="font-medium">{formatNumber(githubItem.stars)}</span>
                      </div>
                      {recentStarsLabel(githubItem) && (
                        <div className="flex items-center space-x-1 text-green-600" title="Trending 周期新增 Star">
                          <TrendingUp className="w-4 h-4" />
                          <span>{recentStarsLabel(githubItem)}</span>
                        </div>
                      )}
                      {githubItem.recent_issue_comments !== null && (
                        <div className="flex items-center space-x-1 text-blue-600" title="近期 Issue/PR 评论">
                          <MessageCircle className="w-4 h-4" />
                          <span>{formatNumber(githubItem.recent_issue_comments)}</span>
                        </div>
                      )}
                      <div className="flex items-center space-x-1 text-gray-500" title="Fork">
                        <GitFork className="w-4 h-4" />
                        <span>{formatNumber(githubItem.forks)}</span>
                      </div>
                      {githubItem.main_language && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                          <Code className="w-3 h-3 mr-1" />
                          {githubItem.main_language}
                        </span>
                      )}
                    </>
                  ) : (
                    <>
                      <div className="flex items-center space-x-1 text-gray-600">
                        <Eye className="w-4 h-4" />
                        <span>{formatNumber(youtubeItem.view_count)} 观看</span>
                      </div>
                      <div className="flex items-center space-x-1 text-gray-600">
                        <ThumbsUp className="w-4 h-4" />
                        <span>{formatNumber(youtubeItem.like_count)}</span>
                      </div>
                      {youtubeItem.duration && (
                        <span className="text-gray-600">⏱️ {youtubeItem.duration}</span>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* 内容区 */}
          <div className="p-6 space-y-6">
            {isGitHub ? (
              <>
                {/* GitHub 详情 */}
                {githubItem.summary && (
                  <Section title="📝 项目总结" content={githubItem.summary} />
                )}
                
                {githubItem.why_trending && (
                  <Section title="🔥 为什么火" content={githubItem.why_trending} />
                )}
                
                {githubItem.key_innovations && githubItem.key_innovations.length > 0 && (
                  <ListSection title="💡 关键创新点" items={githubItem.key_innovations} />
                )}
                
                {githubItem.practical_value && (
                  <Section title="🎯 实用价值" content={githubItem.practical_value} />
                )}
                
                {githubItem.learning_points && githubItem.learning_points.length > 0 && (
                  <ListSection title="📚 学习要点" items={githubItem.learning_points} />
                )}

                {githubItem.topics && githubItem.topics.length > 0 && (
                  <div>
                    <h3 className="font-semibold text-gray-900 mb-2">🏷️ 标签</h3>
                    <div className="flex flex-wrap gap-2">
                      {githubItem.topics.map((topic) => (
                        <span
                          key={topic}
                          className="px-3 py-1 rounded-full text-sm bg-gray-100 text-gray-700"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <>
                {/* YouTube 详情 */}
                {youtubeItem.content_summary && (
                  <Section title="📝 内容总结" content={youtubeItem.content_summary} />
                )}
                
                {youtubeItem.key_points && youtubeItem.key_points.length > 0 && (
                  <ListSection title="🎯 核心观点" items={youtubeItem.key_points} />
                )}
                
                {youtubeItem.why_popular && (
                  <Section title="🔥 为什么受欢迎" content={youtubeItem.why_popular} />
                )}
                
                {youtubeItem.practical_takeaways && (
                  <Section title="💡 实用收获" content={youtubeItem.practical_takeaways} />
                )}
                
                {youtubeItem.recommended_for && (
                  <Section title="👥 推荐人群" content={youtubeItem.recommended_for} />
                )}
              </>
            )}
          </div>

          {/* 底部操作 */}
          <div className="p-6 border-t bg-gray-50 rounded-b-2xl">
            <a
              href={isGitHub ? githubItem.repo_url : youtubeItem.video_url}
              target="_blank"
              rel="noopener noreferrer"
              className={`inline-flex items-center px-6 py-3 rounded-lg text-white font-medium transition-colors ${
                isGitHub ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'
              }`}
            >
              <ExternalLink className="w-5 h-5 mr-2" />
              {isGitHub ? '查看 GitHub 仓库' : '观看 YouTube 视频'}
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}

function Section({ title, content }: { title: string; content: string }) {
  return (
    <div>
      <h3 className="font-semibold text-gray-900 mb-2">{title}</h3>
      <p className="text-gray-600 leading-relaxed">{content}</p>
    </div>
  )
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3 className="font-semibold text-gray-900 mb-2">{title}</h3>
      <ul className="space-y-2">
        {items.map((item, idx) => (
          <li key={idx} className="flex items-start">
            <span className="text-indigo-500 mr-2">•</span>
            <span className="text-gray-600">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default DetailModal