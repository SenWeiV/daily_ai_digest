"""
Gemini 分析引擎 - 使用 Gemini Pro 进行深度内容分析
"""

import json
import logging
import socket
from typing import Optional, List, Dict, Any

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    """Gemini 大模型分析引擎"""
    
    def __init__(self):
        """初始化 Gemini 客户端"""
        self.api_key = settings.gemini_api_key
        self.model_name = "gemini-1.5-pro"
        self.model = None
        self._token_count = 0
        self._network_available = None  # 缓存网络状态
        
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "max_output_tokens": 8192,
                }
            )
            logger.info(f"Gemini 分析引擎初始化完成，模型: {self.model_name}")
        else:
            logger.warning("未配置 Gemini API Key，分析功能将不可用")
    
    def _check_network(self) -> bool:
        """快速检测 Gemini API 网络连通性"""
        if self._network_available is not None:
            return self._network_available
        
        try:
            socket.setdefaulttimeout(5)
            socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=5)
            self._network_available = True
            logger.info("Gemini API 网络连通性检测通过")
        except (socket.timeout, socket.error, OSError) as e:
            self._network_available = False
            logger.warning(f"Gemini API 网络不可用: {e}")
        finally:
            socket.setdefaulttimeout(None)
        
        return self._network_available
    
    @property
    def is_available(self) -> bool:
        """检查 Gemini 是否可用（包括网络连通性）"""
        if self.model is None:
            return False
        # 检查网络连通性
        return self._check_network()
    
    @property
    def token_count(self) -> int:
        """获取已使用的 Token 数量"""
        return self._token_count
    
    def reset_token_count(self):
        """重置 Token 计数"""
        self._token_count = 0
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((Exception,)),
        reraise=True
    )
    async def _generate_content(self, prompt: str) -> str:
        """调用 Gemini 生成内容（带重试机制）"""
        if not self.is_available:
            raise RuntimeError("Gemini API 未配置")
        
        try:
            response = await self.model.generate_content_async(prompt)
            
            # 更新 Token 计数（估算）
            self._token_count += len(prompt) // 4 + len(response.text) // 4
            
            return response.text
        except Exception as e:
            logger.error(f"Gemini 生成内容失败: {e}")
            raise
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """解析 JSON 格式的响应"""
        # 尝试提取 JSON 块
        import re
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1)
        else:
            # 尝试直接解析
            text = text.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1] if '\n' in text else text[3:]
            if text.endswith('```'):
                text = text.rsplit('```', 1)[0]
        
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            logger.warning(f"JSON 解析失败，返回原始文本")
            return {"raw_response": text}
    
    async def analyze_github_repo(
        self,
        repo_name: str,
        description: str,
        language: str,
        stars: int,
        readme_content: str,
        code_files: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        分析 GitHub 仓库
        
        Args:
            repo_name: 仓库名称 (owner/repo)
            description: 项目描述
            language: 主要编程语言
            stars: Star 数量
            readme_content: README 内容
            code_files: 核心代码文件 {filename: content}
        
        Returns:
            分析结果字典
        """
        # 构建代码文件部分
        code_section = ""
        if code_files:
            code_section = "\n\n核心代码文件:\n"
            for filename, content in code_files.items():
                # 限制每个文件内容长度
                truncated = content[:3000] + "..." if len(content) > 3000 else content
                code_section += f"\n--- {filename} ---\n{truncated}\n"
        
        # 截断 README
        readme_truncated = readme_content[:8000] + "..." if len(readme_content) > 8000 else readme_content
        
        prompt = f"""你是一位资深AI技术专家和技术博主。请深度分析以下GitHub项目，并以JSON格式返回分析结果。

项目名称：{repo_name}
项目描述：{description or '无描述'}
主要语言：{language or '未知'}
Star数：{stars}

README内容：
{readme_truncated}
{code_section}

请从以下维度进行分析，以JSON格式返回（确保JSON格式正确）：

```json
{{
    "summary": "项目核心功能总结（100字内）",
    "why_trending": "为什么这个项目会火？（技术创新/解决痛点/时机把握，100字内）",
    "key_innovations": ["创新点1", "创新点2", "创新点3"],
    "practical_value": "对AI从业者/学习者的实用价值（100字内）",
    "learning_points": ["学习要点1", "学习要点2", "学习要点3"]
}}
```

请确保返回的是有效的JSON格式。"""

        try:
            response = await self._generate_content(prompt)
            result = self._parse_json_response(response)
            
            # 确保返回结构完整
            return {
                "summary": result.get("summary", ""),
                "why_trending": result.get("why_trending", ""),
                "key_innovations": result.get("key_innovations", []),
                "practical_value": result.get("practical_value", ""),
                "learning_points": result.get("learning_points", [])
            }
        except Exception as e:
            logger.error(f"分析 GitHub 仓库失败 [{repo_name}]: {e}")
            return {
                "summary": f"分析失败: {str(e)}",
                "why_trending": "",
                "key_innovations": [],
                "practical_value": "",
                "learning_points": []
            }
    
    async def analyze_youtube_video(
        self,
        title: str,
        channel: str,
        description: str,
        view_count: int,
        duration: str,
        transcript: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        分析 YouTube 视频
        
        Args:
            title: 视频标题
            channel: 频道名称
            description: 视频描述
            view_count: 观看量
            duration: 视频时长
            transcript: 字幕/转录文本
        
        Returns:
            分析结果字典
        """
        # 准备内容部分
        content_section = ""
        if transcript:
            # 截断字幕内容
            transcript_truncated = transcript[:15000] + "..." if len(transcript) > 15000 else transcript
            content_section = f"\n\n完整字幕/转录：\n{transcript_truncated}"
        else:
            # 无字幕时使用描述
            desc_truncated = description[:3000] if description else "无描述"
            content_section = f"\n\n视频描述：\n{desc_truncated}\n\n（注意：此视频无字幕，请基于标题和描述进行分析）"
        
        prompt = f"""你是一位资深AI领域内容分析师。请深度分析以下YouTube视频内容，并以JSON格式返回分析结果。

视频标题：{title}
频道：{channel}
观看量：{view_count:,}
时长：{duration}
{content_section}

请从以下维度进行分析，以JSON格式返回（确保JSON格式正确）：

```json
{{
    "content_summary": "视频核心内容总结（150字内）",
    "key_points": ["核心观点1", "核心观点2", "核心观点3", "核心观点4", "核心观点5"],
    "why_popular": "为什么这个视频受欢迎？（100字内）",
    "practical_takeaways": "观看后的实用收获（100字内）",
    "recommended_for": "适合什么样的观众（50字内）"
}}
```

请确保返回的是有效的JSON格式。"""

        try:
            response = await self._generate_content(prompt)
            result = self._parse_json_response(response)
            
            # 确保返回结构完整
            return {
                "content_summary": result.get("content_summary", ""),
                "key_points": result.get("key_points", []),
                "why_popular": result.get("why_popular", ""),
                "practical_takeaways": result.get("practical_takeaways", ""),
                "recommended_for": result.get("recommended_for", "")
            }
        except Exception as e:
            logger.error(f"分析 YouTube 视频失败 [{title}]: {e}")
            return {
                "content_summary": f"分析失败: {str(e)}",
                "key_points": [],
                "why_popular": "",
                "practical_takeaways": "",
                "recommended_for": ""
            }
    
    async def generate_daily_summary(
        self,
        github_items: List[Dict],
        youtube_items: List[Dict]
    ) -> str:
        """
        生成每日综合总结
        
        Args:
            github_items: GitHub 项目列表
            youtube_items: YouTube 视频列表
        
        Returns:
            综合总结文本
        """
        # 构建摘要内容
        github_summary = "\n".join([
            f"- {item.get('repo_name', 'Unknown')}: {item.get('summary', 'No summary')}"
            for item in github_items[:5]
        ])
        
        youtube_summary = "\n".join([
            f"- {item.get('title', 'Unknown')}: {item.get('content_summary', 'No summary')}"
            for item in youtube_items[:5]
        ])
        
        prompt = f"""作为AI领域观察者，请基于今日热门内容生成一段简洁的每日总结（200字内）：

GitHub热门项目：
{github_summary}

YouTube热门视频：
{youtube_summary}

请总结今日AI领域的主要趋势和值得关注的方向。"""

        try:
            response = await self._generate_content(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"生成每日总结失败: {e}")
            return "今日AI领域有多个值得关注的项目和视频，详情请查看下方内容。"


# 全局实例
gemini_analyzer = GeminiAnalyzer()