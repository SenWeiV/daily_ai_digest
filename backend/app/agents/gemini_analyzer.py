"""
Gemini 分析引擎 - 使用 Gemini Pro 进行深度内容分析
"""

import json
import logging
import socket
from urllib.parse import urlparse
from typing import Optional, List, Dict, Any

import google.generativeai as genai
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.config import secret_value, settings
from app.model_roles import role_usage

logger = logging.getLogger(__name__)


class GeminiAnalyzer:
    """Gemini 大模型分析引擎"""
    
    def __init__(self):
        """初始化 Gemini 客户端"""
        self.api_key = secret_value(settings.text_api_key)
        self.base_url = settings.text_base_url.rstrip("/")
        self.model_name = settings.text_model
        self.model_names = self._build_model_list()
        self.models: Dict[str, genai.GenerativeModel] = {}
        self.active_model_name: Optional[str] = None
        self._token_count = 0
        self._network_available = None  # 缓存网络状态
        self.use_openai_compatible = bool(self.base_url)
        
        if self.api_key:
            if self.use_openai_compatible:
                # OpenAI 兼容接口仅在请求时动态发送 model，不需要预构建客户端对象
                for model_name in self.model_names:
                    self.models[model_name] = None  # type: ignore[assignment]
            else:
                genai.configure(api_key=self.api_key)
                generation_config = {
                    "temperature": 0.3,
                    "top_p": 0.8,
                    "max_output_tokens": 8192,
                }
                for model_name in self.model_names:
                    self.models[model_name] = genai.GenerativeModel(
                        model_name=model_name,
                        generation_config=generation_config
                    )
            self.active_model_name = self.model_names[0] if self.model_names else None
            if self.use_openai_compatible:
                host = urlparse(self.base_url).hostname or self.base_url
                logger.info(
                    f"LLM 分析引擎初始化完成 | 模型={self.active_model_name} | 端点={host} "
                    f"| 备选={', '.join(self.model_names[1:]) or '无'}"
                )
            else:
                logger.info(f"Gemini 分析引擎初始化完成，模型链路: {', '.join(self.model_names)}")
        else:
            logger.warning("未配置 LLM API Key，分析功能将不可用")

    def _build_model_list(self) -> List[str]:
        """构建模型优先级列表（主模型 + 回退模型）"""
        raw_models = [settings.text_model]
        if settings.text_fallback_models:
            raw_models.extend(settings.text_fallback_models.split(","))

        models: List[str] = []
        seen = set()
        for model in raw_models:
            model_name = model.strip()
            if model_name and model_name not in seen:
                seen.add(model_name)
                models.append(model_name)
        return models
    
    def _check_network(self) -> bool:
        """快速检测 API 网络连通性"""
        if self._network_available is not None:
            return self._network_available

        try:
            socket.setdefaulttimeout(10)
            if self.use_openai_compatible:
                # OpenAI 兼容接口（如 Kimi、DeepSeek 等）
                parsed = urlparse(self.base_url)
                host = parsed.hostname
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                if not host:
                    raise OSError(f"无效 BASE_URL: {self.base_url}")
                socket.create_connection((host, port), timeout=10)
                self._network_available = True
                logger.info(f"LLM API 网络连通性检测通过: {host}:{port}")
            else:
                # Google Gemini 原生接口
                socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=10)
                self._network_available = True
                logger.info("Gemini API 网络连通性检测通过")
        except (socket.timeout, socket.error, OSError) as e:
            self._network_available = False
            logger.warning(f"LLM API 网络不可用: {e}")
        finally:
            socket.setdefaulttimeout(None)

        return self._network_available
    
    @property
    def is_available(self) -> bool:
        """检查 Gemini 是否可用（包括网络连通性）"""
        if not self.models:
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
            raise RuntimeError("Gemini API 不可用（未配置或网络不可达）")
        
        model_candidates = list(self.model_names)
        if self.active_model_name in self.models:
            model_candidates = [self.active_model_name] + [
                name for name in self.model_names if name != self.active_model_name
            ]

        last_error = None
        for model_name in model_candidates:
            try:
                if self.use_openai_compatible:
                    response_text = await self._generate_with_openai_compatible(prompt, model_name)
                else:
                    model = self.models.get(model_name)
                    if not model:
                        continue
                    response = await model.generate_content_async(prompt)
                    response_text = response.text or ""

                # 更新 Token 计数（估算）
                self._token_count += len(prompt) // 4 + len(response_text) // 4
                role_usage.record("text")
                self.active_model_name = model_name
                return response_text
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini 模型调用失败 [{model_name}]: {e}")
                continue

        logger.error(f"Gemini 生成内容失败，所有模型均不可用: {last_error}")
        raise RuntimeError(f"Gemini 生成内容失败: {last_error}")

    async def _generate_with_openai_compatible(self, prompt: str, model_name: str) -> str:
        """通过 OpenAI 兼容接口生成内容"""
        endpoint = self._resolve_endpoint()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
        }
        # 刻意只发 model + messages。DeepSeek V4 的思考模式默认开启，实测这种
        # 最小请求返回 content 与 reasoning_content 两者都有；一旦显式带上
        # temperature 或 max_tokens，就等于用我们猜的常量去覆盖 provider 默认值：
        # max_tokens 会在长 README 上截断答案（截断的 JSON 解析失败，落成"分析为空"），
        # temperature 则在部分模型上直接被拒（K3 只接受 1）。
        # 需要压低随机性时改 provider 侧或换模型，不在这里写死。

        async with httpx.AsyncClient(timeout=120, trust_env=False) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            if response.status_code >= 400:
                # 凭据错误/配额错误必须带上 provider 状态，不能表现为"分析为空"
                detail = response.text.strip()[:300]
                logger.error(
                    f"LLM 接口返回错误 [{model_name}] status={response.status_code}: {detail}"
                )
                response.raise_for_status()
            raw_text = response.text.strip()
            if not raw_text:
                raise RuntimeError("OpenAI兼容接口返回空响应")
            try:
                data = response.json()
            except json.JSONDecodeError:
                return raw_text

        message = data.get("choices", [{}])[0].get("message", {}) or {}
        content = message.get("content", "")

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            content = "\n".join(parts)

        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()

        if not content:
            # 思考模式可能只回 reasoning_content。推理链不是答案，绝不能当分析结果存下去
            reasoning = message.get("reasoning_content") or ""
            if reasoning:
                logger.debug(
                    f"LLM 仅返回推理内容，无答案正文 [{model_name}]，推理长度={len(reasoning)}"
                )
                raise RuntimeError("LLM 仅返回推理内容，缺少答案正文")

        return content

    def _resolve_endpoint(self) -> str:
        """构建 chat completions 端点

        base_url 带路径（如 /v1、/compatible-mode/v1、/api/v3）视为已含版本段，
        直接追加 /chat/completions；不带路径则补 /v1/chat/completions。
        """
        base = self.base_url.rstrip("/")
        base_path = urlparse(base).path.rstrip("/")
        if base_path:
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"
    
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
            raw_fallback = result.get("raw_response", "").strip()
            
            # 确保返回结构完整
            return {
                "summary": result.get("summary", "") or raw_fallback[:300],
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
    
    async def analyze_arxiv_paper(
        self,
        title: str,
        abstract: str,
        authors: List[str],
        categories: List[str],
    ) -> Dict[str, Any]:
        """Analyze a selected paper without inventing missing evidence."""
        if not self.is_available:
            return {"summary": abstract[:800]}
        prompt = f"""请分析下面的 arXiv 论文元数据。只根据给定标题和摘要作答；摘要未提供的信息必须写“摘要未说明”，不要推测实验结果。

标题: {title}
作者: {', '.join(authors)}
分类: {', '.join(categories)}
摘要: {abstract[:12000]}

返回严格 JSON：
{{
  "summary": "核心总结",
  "problem": "研究问题",
  "method": "方法",
  "evaluation": "评测设置；未说明则明确写出",
  "results": "主要结果；未说明则明确写出",
  "limitations": "局限；未说明则明确写出"
}}
"""
        try:
            response = await self._generate_content(prompt)
            return self._parse_json_response(response)
        except Exception as exc:
            logger.warning("arXiv analysis failed [%s]: %s", title, exc)
            return {"summary": abstract[:800]}

    async def generate_period_summary(
        self,
        github_items: List[Dict],
        arxiv_items: List[Dict],
        period: str = "daily"
    ) -> str:
        """
        生成周期综合总结（日/周/月）
        
        Args:
            github_items: GitHub 项目列表
            arxiv_items: arXiv 论文列表
            period: 周期类型 (daily/weekly/monthly)
        
        Returns:
            综合总结文本
        """
        # 构建摘要内容
        github_summary = "\n".join([
            f"- {item.get('repo_name', 'Unknown')}: {item.get('summary', 'No summary')}"
            for item in github_items[:10]
        ])
        
        arxiv_summary = "\n".join([
            f"- {item.get('title', 'Unknown')}: {item.get('summary', 'No summary')}"
            for item in arxiv_items[:10]
        ])
        
        period_names = {
            "daily": ("今日", "200"),
            "weekly": ("本周", "300"),
            "monthly": ("本月", "400")
        }
        period_name, max_chars = period_names.get(period, ("本周期", "300"))
        
        prompt = f"""作为AI领域观察者，请基于{period_name}热门内容生成一段简洁的总结（{max_chars}字内）：

GitHub热门项目：
{github_summary}

arXiv 精选论文：
{arxiv_summary}

请总结{period_name}AI领域的主要趋势、技术突破和值得关注的方向。"""

        try:
            response = await self._generate_content(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"生成{period}总结失败: {e}")
            period_desc = {"daily": "今日", "weekly": "本周", "monthly": "本月"}.get(period, "本周期")
            return f"{period_desc}AI领域有多个值得关注的项目和论文，详情请查看下方内容。"


# 全局实例
gemini_analyzer = GeminiAnalyzer()
