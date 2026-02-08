import { Star, GitFork, ExternalLink, Code, Lightbulb, TrendingUp } from 'lucide-react'
import type { GitHubDigestItem } from '../types'

interface GitHubListProps {
  items: GitHubDigestItem[]
  onItemClick?: (item: GitHubDigestItem) => void
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K'
  }
  return num.toString()
}

function GitHubList({ items, onItemClick }: GitHubListProps) {
  if (!items || items.length === 0) {
    return (
      <div className="bg-white rounded-xl p-8 shadow-sm border border-gray-100 text-center">
        <p className="text-gray-500">暂无 GitHub 数据</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {items.map((item, index) => (
        <div
          key={item.repo_name}
          className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 border-l-4 border-l-green-500 card-hover cursor-pointer"
          onClick={() => onItemClick?.(item)}
        >
          {/* 标题行 */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex-1">
              <div className="flex items-center space-x-2">
                <span className="text-lg font-bold text-gray-400">#{index + 1}</span>
                <h3 className="text-lg font-semibold text-gray-900 hover:text-green-600">
                  {item.repo_name}
                </h3>
                <a
                  href={item.repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-gray-400 hover:text-green-600"
                  onClick={(e) => e.stopPropagation()}
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
              <p className="text-gray-600 text-sm mt-1 line-clamp-2">
                {item.description || '暂无描述'}
              </p>
            </div>
            {/* Star 信息 */}
            <div className="flex items-center space-x-4 ml-4">
              <div className="flex items-center space-x-1 text-yellow-500">
                <Star className="w-5 h-5 fill-current" />
                <span className="font-semibold">{formatNumber(item.stars)}</span>
                {item.stars_today > 0 && (
                  <span className="text-green-500 text-sm">(+{item.stars_today})</span>
                )}
              </div>
              <div className="flex items-center space-x-1 text-gray-500">
                <GitFork className="w-4 h-4" />
                <span className="text-sm">{formatNumber(item.forks)}</span>
              </div>
            </div>
          </div>

          {/* 标签 */}
          <div className="flex items-center flex-wrap gap-2 mb-4">
            {item.main_language && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                <Code className="w-3 h-3 mr-1" />
                {item.main_language}
              </span>
            )}
            {item.topics?.slice(0, 4).map((topic) => (
              <span
                key={topic}
                className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700"
              >
                {topic}
              </span>
            ))}
          </div>

          {/* AI分析结果 */}
          {item.summary && (
            <div className="bg-gray-50 rounded-lg p-4 space-y-3">
              <div>
                <div className="flex items-center text-gray-700 font-medium mb-1">
                  <Lightbulb className="w-4 h-4 mr-2 text-yellow-500" />
                  项目总结
                </div>
                <p className="text-gray-600 text-sm">{item.summary}</p>
              </div>
              
              {item.why_trending && (
                <div>
                  <div className="flex items-center text-gray-700 font-medium mb-1">
                    <TrendingUp className="w-4 h-4 mr-2 text-red-500" />
                    为什么火
                  </div>
                  <p className="text-gray-600 text-sm">{item.why_trending}</p>
                </div>
              )}

              {item.key_innovations && item.key_innovations.length > 0 && (
                <div>
                  <div className="text-gray-700 font-medium mb-1">💡 关键创新</div>
                  <ul className="list-disc list-inside text-gray-600 text-sm space-y-1">
                    {item.key_innovations.slice(0, 3).map((point, idx) => (
                      <li key={idx}>{point}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default GitHubList