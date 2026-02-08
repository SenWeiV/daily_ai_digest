import { Eye, ThumbsUp, MessageCircle, ExternalLink, Clock, Lightbulb, TrendingUp } from 'lucide-react'
import type { YouTubeDigestItem } from '../types'

interface YouTubeListProps {
  items: YouTubeDigestItem[]
  onItemClick?: (item: YouTubeDigestItem) => void
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

function YouTubeList({ items, onItemClick }: YouTubeListProps) {
  if (!items || items.length === 0) {
    return (
      <div className="bg-white rounded-xl p-8 shadow-sm border border-gray-100 text-center">
        <p className="text-gray-500">暂无 YouTube 数据</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {items.map((item, index) => (
        <div
          key={item.video_id}
          className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 border-l-4 border-l-red-500 card-hover cursor-pointer"
          onClick={() => onItemClick?.(item)}
        >
          <div className="flex gap-4">
            {/* 缩略图 */}
            {item.thumbnail_url && (
              <a
                href={item.video_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-shrink-0"
                onClick={(e) => e.stopPropagation()}
              >
                <img
                  src={item.thumbnail_url}
                  alt={item.title}
                  className="w-40 h-24 object-cover rounded-lg hover:opacity-90 transition-opacity"
                />
              </a>
            )}

            {/* 内容区 */}
            <div className="flex-1 min-w-0">
              {/* 标题 */}
              <div className="flex items-start justify-between mb-2">
                <div className="flex-1">
                  <div className="flex items-center space-x-2">
                    <span className="text-lg font-bold text-gray-400">#{index + 1}</span>
                    <h3 className="text-lg font-semibold text-gray-900 hover:text-red-600 line-clamp-2">
                      {item.title}
                    </h3>
                    <a
                      href={item.video_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-gray-400 hover:text-red-600 flex-shrink-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
                  </div>
                  <p className="text-gray-600 text-sm mt-1">
                    📺 {item.channel}
                  </p>
                </div>
              </div>

              {/* 统计信息 */}
              <div className="flex items-center flex-wrap gap-4 mb-3 text-sm">
                <div className="flex items-center space-x-1 text-gray-600">
                  <Eye className="w-4 h-4" />
                  <span>{formatNumber(item.view_count)} 观看</span>
                </div>
                <div className="flex items-center space-x-1 text-gray-600">
                  <ThumbsUp className="w-4 h-4" />
                  <span>{formatNumber(item.like_count)}</span>
                </div>
                <div className="flex items-center space-x-1 text-gray-600">
                  <MessageCircle className="w-4 h-4" />
                  <span>{formatNumber(item.comment_count)}</span>
                </div>
                {item.duration && (
                  <div className="flex items-center space-x-1 text-gray-600">
                    <Clock className="w-4 h-4" />
                    <span>{item.duration}</span>
                  </div>
                )}
              </div>

              {/* AI分析结果 */}
              {item.content_summary && (
                <div className="bg-gray-50 rounded-lg p-4 space-y-3">
                  <div>
                    <div className="flex items-center text-gray-700 font-medium mb-1">
                      <Lightbulb className="w-4 h-4 mr-2 text-yellow-500" />
                      内容总结
                    </div>
                    <p className="text-gray-600 text-sm">{item.content_summary}</p>
                  </div>

                  {item.key_points && item.key_points.length > 0 && (
                    <div>
                      <div className="text-gray-700 font-medium mb-1">🎯 核心观点</div>
                      <ul className="list-disc list-inside text-gray-600 text-sm space-y-1">
                        {item.key_points.slice(0, 3).map((point, idx) => (
                          <li key={idx}>{point}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {item.why_popular && (
                    <div>
                      <div className="flex items-center text-gray-700 font-medium mb-1">
                        <TrendingUp className="w-4 h-4 mr-2 text-red-500" />
                        为什么受欢迎
                      </div>
                      <p className="text-gray-600 text-sm">{item.why_popular}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default YouTubeList