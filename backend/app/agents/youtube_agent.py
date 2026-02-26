"""
YouTube Agent - 检索和分析YouTube热门AI视频
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

import socket
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import httplib2
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)

from app.config import settings
from app.schemas import YouTubeDigestItem
from app.agents.gemini_analyzer import gemini_analyzer
from app.utils.helpers import format_number, parse_iso8601_duration, format_duration

logger = logging.getLogger(__name__)


class YouTubeAgent:
    """YouTube 热门视频检索和分析 Agent"""
    
    # AI/AGI/AI Agent 相关搜索关键词
    SEARCH_KEYWORDS = [
        "AI agent 2025",
        "LLM agent tutorial",
        "AGI artificial general intelligence",
        "autonomous AI agent",
        "multi-agent AI system",
        "Claude AI news",
        "GPT-4 GPT-5 news",
        "Gemini AI update",
        "AI coding agent",
        "agentic AI workflow",
        "AI reasoning breakthrough",
        "OpenAI news",
        "Anthropic Claude",
        "AI automation agent"
    ]
    
    def __init__(self):
        """初始化 YouTube 客户端"""
        self.api_key = settings.youtube_api_key
        self.client = None
        self.top_n = settings.youtube_top_n
        self._network_available = None  # 缓存网络状态
        self._disabled = False  # 是否禁用 YouTube 功能

        if self.api_key:
            self.client = self._build_client()
            logger.info("YouTube Agent 初始化完成")
        else:
            self._disabled = True
            logger.warning("未配置 YouTube API Key，YouTube 功能已禁用")

    def _get_proxy_url(self) -> str:
        """从环境变量读取代理地址（优先 HTTPS_PROXY）。"""
        return (
            os.getenv("HTTPS_PROXY")
            or os.getenv("https_proxy")
            or os.getenv("HTTP_PROXY")
            or os.getenv("http_proxy")
            or os.getenv("ALL_PROXY")
            or os.getenv("all_proxy")
            or ""
        ).strip()

    def _build_client(self):
        """构建 YouTube API 客户端。

        说明：云服务器可能无法直连 Google，需要通过代理访问。
        googleapiclient 默认底层使用 httplib2，这里显式注入 proxy_info，避免不走环境代理。
        """
        proxy_url = self._get_proxy_url()
        if not proxy_url:
            return build("youtube", "v3", developerKey=self.api_key)

        # 优先使用 httplib2 内置的 from_environment（不依赖 PySocks）。
        try:
            from_env = getattr(getattr(httplib2, "ProxyInfo", None), "from_environment", None)
            if callable(from_env):
                proxy_info = from_env()
                if proxy_info is not None:
                    http = httplib2.Http(proxy_info=proxy_info, timeout=30)
                    logger.info("YouTube Agent 使用环境变量代理访问 Google API: %s", proxy_url)
                    return build("youtube", "v3", developerKey=self.api_key, http=http)
        except Exception as e:
            logger.warning("YouTube Agent 读取环境代理失败，将尝试默认客户端: %s", e)

        # 兜底：直接 build（部分环境下 httplib2 会自动读取 http_proxy/https_proxy）
        logger.info("YouTube Agent 使用默认客户端（可能会读取环境代理）: %s", proxy_url)
        return build("youtube", "v3", developerKey=self.api_key)
    
    def _check_network(self) -> bool:
        """快速检测 Google API 网络连通性"""
        if self._disabled:
            return False
        if self._network_available is not None:
            return self._network_available

        # 如果设置了代理，必须通过代理探测网络；直连 socket 会在国内环境超时。
        proxy_url = self._get_proxy_url()
        if proxy_url:
            try:
                with httpx.Client(timeout=5, trust_env=True, follow_redirects=True) as client:
                    # 204 探测接口，能快速判断是否可达
                    resp = client.get("https://www.googleapis.com/generate_204")
                self._network_available = resp.status_code in {200, 204}
                if self._network_available:
                    logger.info("YouTube API 网络连通性检测通过（proxy）")
                else:
                    logger.warning(
                        "YouTube API 网络检测失败（proxy），status=%s", resp.status_code
                    )
            except Exception as e:
                self._network_available = False
                logger.warning(f"YouTube API 网络不可用（proxy）: {e}")
            return self._network_available

        # 国内环境无代理时，直接标记网络不可用，避免长时间超时
        logger.warning("YouTube API: 国内环境无代理，跳过网络检测")
        self._network_available = False
        return self._network_available
    
    @property
    def is_available(self) -> bool:
        """检查 YouTube 客户端是否可用"""
        if self._disabled:
            return False
        return self.client is not None

    def extract_video_id(self, video_input: str) -> Optional[str]:
        """
        从 YouTube URL 或文本中提取视频ID
        支持:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/shorts/VIDEO_ID
        - 直接传入 11 位视频ID
        """
        if not video_input:
            return None

        raw = video_input.strip()
        if re.match(r"^[a-zA-Z0-9_-]{11}$", raw):
            return raw

        patterns = [
            r"(?:v=)([a-zA-Z0-9_-]{11})",
            r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:/shorts/)([a-zA-Z0-9_-]{11})",
            r"(?:/embed/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw)
            if match:
                return match.group(1)
        return None

    async def fetch_video_by_id(self, video_id: str) -> Optional[Dict[str, Any]]:
        """按视频ID获取详情"""
        if not self.is_available:
            logger.error("YouTube 客户端未初始化")
            return None

        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=video_id,
                    maxResults=1
                ).execute()
            )
            items = response.get("items", [])
            return items[0] if items else None
        except HttpError as e:
            logger.error(f"拉取视频详情失败 [{video_id}]: {e}")
            return None
        except Exception as e:
            logger.error(f"拉取视频详情异常 [{video_id}]: {e}")
            return None
    
    async def search_trending_videos(
        self,
        keywords: Optional[List[str]] = None,
        days_ago: int = 1,
        max_results_per_keyword: int = 15
    ) -> List[Dict[str, Any]]:
        """
        搜索观看量增长最快的 AI 相关视频
        
        策略：搜索过去 N 天内发布的视频，按观看量排序
        新视频 + 高观看量 = 观看量增长最快
        
        Args:
            keywords: 搜索关键词列表
            days_ago: 搜索最近N天发布的视频（默认1天=24小时）
            max_results_per_keyword: 每个关键词返回的最大结果数
        
        Returns:
            视频信息列表
        """
        if not self.is_available:
            logger.error("YouTube 客户端未初始化")
            return []
        
        # 快速检测网络，避免长时间超时
        if not self._check_network():
            logger.warning("YouTube API 网络不可用，跳过视频搜索")
            return []
        
        keywords = keywords or self.SEARCH_KEYWORDS
        published_after = (datetime.utcnow() - timedelta(days=days_ago)).isoformat() + "Z"
        
        all_videos: Dict[str, Dict] = {}
        
        for keyword in keywords:
            try:
                # 执行搜索
                search_response = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda k=keyword: self.client.search().list(
                        q=k,
                        part="snippet",
                        type="video",
                        order="viewCount",
                        publishedAfter=published_after,
                        maxResults=max_results_per_keyword,
                        relevanceLanguage="en"
                    ).execute()
                )
                
                # 提取视频ID
                video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
                
                if video_ids:
                    # 获取视频详细信息（包含统计数据）
                    videos_response = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda ids=video_ids: self.client.videos().list(
                            part="snippet,statistics,contentDetails",
                            id=",".join(ids)
                        ).execute()
                    )
                    
                    # 合并结果
                    for item in videos_response.get("items", []):
                        video_id = item["id"]
                        if video_id not in all_videos:
                            all_videos[video_id] = item
                
                logger.info(f"关键词 '{keyword}' 找到 {len(video_ids)} 个视频")
                
                # 避免API限流
                await asyncio.sleep(0.3)
                
            except HttpError as e:
                logger.error(f"搜索关键词 '{keyword}' 失败: {e}")
                continue
            except Exception as e:
                logger.error(f"搜索异常: {e}")
                continue
        
        # 按观看量排序
        sorted_videos = sorted(
            all_videos.values(),
            key=lambda v: int(v.get("statistics", {}).get("viewCount", 0)),
            reverse=True
        )
        
        logger.info(f"共找到 {len(sorted_videos)} 个去重后的视频")
        return sorted_videos[:self.top_n * 2]
    
    async def fetch_video_transcript(self, video_id: str) -> Optional[str]:
        """
        获取视频字幕/转录
        
        Args:
            video_id: YouTube视频ID
        
        Returns:
            字幕文本，无字幕返回None
        """
        try:
            # 尝试获取字幕
            transcript_list = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: YouTubeTranscriptApi.list_transcripts(video_id)
            )
            
            # 优先获取英文字幕
            transcript = None
            try:
                transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
            except:
                # 尝试获取自动生成的字幕
                try:
                    transcript = transcript_list.find_generated_transcript(['en', 'en-US', 'en-GB'])
                except:
                    # 获取任意可用字幕
                    for t in transcript_list:
                        transcript = t
                        break
            
            if transcript:
                # 获取字幕内容
                transcript_data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    transcript.fetch
                )
                
                # 合并字幕文本
                full_text = " ".join([entry["text"] for entry in transcript_data])
                
                # 清理文本
                full_text = re.sub(r'\[.*?\]', '', full_text)  # 移除 [Music] 等标记
                full_text = re.sub(r'\s+', ' ', full_text).strip()
                
                return full_text
            
        except TranscriptsDisabled:
            logger.warning(f"视频 {video_id} 已禁用字幕")
        except NoTranscriptFound:
            logger.warning(f"视频 {video_id} 未找到字幕")
        except VideoUnavailable:
            logger.warning(f"视频 {video_id} 不可用")
        except Exception as e:
            logger.warning(f"获取字幕失败 [{video_id}]: {e}")
        
        return None
    
    async def analyze_video(self, video_data: Dict[str, Any]) -> YouTubeDigestItem:
        """
        分析单个视频
        
        Args:
            video_data: YouTube API返回的视频数据
        
        Returns:
            YouTubeDigestItem 分析结果
        """
        snippet = video_data.get("snippet", {})
        statistics = video_data.get("statistics", {})
        content_details = video_data.get("contentDetails", {})
        
        video_id = video_data.get("id", "")
        
        # 解析时长
        duration_iso = content_details.get("duration", "PT0S")
        duration_seconds = parse_iso8601_duration(duration_iso)
        duration_str = format_duration(duration_seconds)
        
        # 基础信息
        item = YouTubeDigestItem(
            video_id=video_id,
            title=snippet.get("title", ""),
            channel=snippet.get("channelTitle", ""),
            channel_url=f"https://www.youtube.com/channel/{snippet.get('channelId', '')}",
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
            view_count=int(statistics.get("viewCount", 0)),
            like_count=int(statistics.get("likeCount", 0)),
            comment_count=int(statistics.get("commentCount", 0)),
            published_at=snippet.get("publishedAt", ""),
            duration=duration_str
        )
        
        # 获取字幕
        transcript = await self.fetch_video_transcript(video_id)
        
        # 使用Gemini进行深度分析
        if gemini_analyzer.is_available:
            try:
                analysis = await gemini_analyzer.analyze_youtube_video(
                    title=item.title,
                    channel=item.channel,
                    description=snippet.get("description", ""),
                    view_count=item.view_count,
                    duration=duration_str,
                    transcript=transcript
                )
                
                item.content_summary = analysis.get("content_summary", "")
                item.key_points = analysis.get("key_points", [])
                item.why_popular = analysis.get("why_popular", "")
                item.practical_takeaways = analysis.get("practical_takeaways", "")
                item.recommended_for = analysis.get("recommended_for", "")
                
            except Exception as e:
                logger.error(f"Gemini分析失败 [{item.title}]: {e}")
                item.content_summary = snippet.get("description", "")[:200]
        else:
            # 无Gemini时使用基础描述
            item.content_summary = snippet.get("description", "")[:200]
        
        return item
    
    async def get_top_videos(
        self,
        keywords: Optional[List[str]] = None,
        days_ago: int = 1
    ) -> List[YouTubeDigestItem]:
        """
        获取观看量增长最快的 Top N AI 视频（完整流程）
        
        策略：搜索过去24小时内发布的视频，按观看量排序
        
        Args:
            keywords: 搜索关键词
            days_ago: 搜索时间范围（天），默认1天
        
        Returns:
            YouTubeDigestItem列表
        """
        logger.info(f"开始获取YouTube Top{self.top_n}（过去{days_ago}天内发布）热门视频...")
        
        # 1. 搜索热门视频
        videos = await self.search_trending_videos(keywords, days_ago)
        
        if not videos:
            logger.warning("未找到任何视频")
            return []
        
        # 2. 逐个分析视频
        results: List[YouTubeDigestItem] = []
        
        for video in videos[:self.top_n]:
            try:
                item = await self.analyze_video(video)
                results.append(item)
                
                logger.info(f"完成分析: {item.title[:50]}... 👀{format_number(item.view_count)}")
                
                # 避免API限流
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"处理视频失败: {e}")
                continue
        
        # 3. 最终排序（按观看量）
        results.sort(key=lambda x: x.view_count, reverse=True)
        
        logger.info(f"YouTube Agent 完成，共获取 {len(results)} 个视频")
        return results[:self.top_n]

    async def analyze_video_by_id(
        self,
        video_url: Optional[str] = None,
        video_id: Optional[str] = None
    ) -> YouTubeDigestItem:
        """分析指定 YouTube 视频（URL/ID）"""
        if not self.is_available:
            raise RuntimeError("YouTube API 未配置")

        if not self._check_network():
            raise RuntimeError("YouTube API 网络不可达")

        resolved_video_id = video_id or ""
        if not resolved_video_id and video_url:
            resolved_video_id = self.extract_video_id(video_url) or ""

        if not resolved_video_id:
            raise ValueError("无法解析 YouTube 视频ID，请传入有效的 video_url 或 video_id")

        video_data = await self.fetch_video_by_id(resolved_video_id)
        if not video_data:
            raise ValueError(f"未找到视频，ID: {resolved_video_id}")

        return await self.analyze_video(video_data)


# 全局实例
youtube_agent = YouTubeAgent()
