"""
GitHub Agent - 从 GitHub Trending 页面检索热门AI项目
"""

import asyncio
import logging
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Literal

import httpx
from bs4 import BeautifulSoup
from github import Github, GithubException
from github.Repository import Repository
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from app.config import settings
from app.schemas import GitHubDigestItem
from app.agents.gemini_analyzer import gemini_analyzer
from app.utils.helpers import truncate_text

logger = logging.getLogger(__name__)


class GitHubAgent:
    """GitHub Trending 热门项目检索和分析 Agent"""
    
    # GitHub Trending URL
    TRENDING_URL = "https://github.com/trending"
    
    # AI/ML 相关关键词（用于过滤）
    AI_KEYWORDS = [
        "ai", "llm", "agent", "gpt", "claude", "gemini", "openai", "anthropic",
        "machine learning", "deep learning", "neural", "model", "language model",
        "rag", "retrieval", "embedding", "vector", "transformer",
        "autonomous", "bot", "assistant", "chatbot", "copilot",
        "diffusion", "stable diffusion", "image generation", "text to image",
        "fine-tune", "training", "inference", "prompt",
        "mcp", "model context protocol"
    ]
    
    # 重试配置
    MAX_RETRIES = 10
    RETRYABLE_EXCEPTIONS = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
    )
    
    def __init__(self):
        """初始化 GitHub 客户端"""
        self.token = settings.github_token
        self.client = None
        self.top_n = settings.github_top_n
        
        if self.token:
            self.client = Github(self.token)
            logger.info("GitHub Agent 初始化完成")
        else:
            logger.warning("未配置 GitHub Token，功能将受限")
    
    @property
    def is_available(self) -> bool:
        """检查 GitHub Agent 是否可用
        
        Trending 页面抓取不需要 Token，始终可用
        API 详情获取需要 Token，但不是必需的
        """
        return True  # Trending 页面抓取始终可用
    
    def _build_fallback_urls(self, time_range: str, language: str = "") -> List[tuple]:
        """
        构建 fallback URL 列表，优先级: 直连 > 代理 > 镜像
        
        Returns:
            [(url, proxy_config), ...] 列表
        """
        urls = []
        path = f"/{language}" if language else ""
        trending_path = f"/trending{path}?since={time_range}"
        
        # 1. 直连 (最高优先级，某些云服务器可能可访问)
        urls.append((f"https://github.com{trending_path}", None))
        
        # 2. 代理访问
        if settings.github_proxy:
            urls.append((f"https://github.com{trending_path}", settings.github_proxy))
        
        # 3. 镜像站点
        if settings.github_mirror:
            mirror_url = settings.github_mirror.rstrip('/')
            urls.append((f"{mirror_url}/https://github.com{trending_path}", None))
        
        return urls

    async def _fetch_single_url(
        self,
        url: str,
        proxy: Optional[str],
        headers: dict,
        retry_count: int = 0
    ) -> tuple[bool, List[Dict[str, Any]], Optional[Exception]]:
        """
        单个 URL 请求（带重试逻辑）
        
        Args:
            url: 请求 URL
            proxy: 代理地址
            headers: 请求头
            retry_count: 当前重试次数
        
        Returns:
            (成功标志, 仓库列表, 错误信息)
        """
        try:
            logger.info(f"正在抓取 GitHub Trending: {url} (proxy: {proxy or '无'}, 重试: {retry_count}/{self.MAX_RETRIES})")
            
            client_kwargs = {
                "timeout": 30.0,
                "follow_redirects": True
            }
            if proxy:
                client_kwargs["proxies"] = proxy
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                repo_list = soup.find_all('article', class_='Box-row')
                
                trending_repos = []
                for article in repo_list:
                    try:
                        h2_tag = article.find('h2', class_='h3')
                        if not h2_tag:
                            continue
                        
                        repo_link = h2_tag.find('a')
                        if not repo_link:
                            continue
                        
                        repo_full_name = repo_link.get_text(strip=True).replace('\n', '').replace(' ', '')
                        repo_url = f"https://github.com{repo_link['href']}"
                        
                        description_tag = article.find('p', class_='col-9')
                        description = description_tag.get_text(strip=True) if description_tag else ""
                        
                        lang_tag = article.find('span', itemprop='programmingLanguage')
                        repo_language = lang_tag.get_text(strip=True) if lang_tag else "Unknown"
                        
                        stars_tag = article.find('span', class_='d-inline-block float-sm-right')
                        stars_today = 0
                        if stars_tag:
                            stars_text = stars_tag.get_text(strip=True)
                            try:
                                stars_today = int(stars_text.split()[0].replace(',', ''))
                            except (ValueError, IndexError):
                                pass
                        
                        trending_repos.append({
                            "full_name": repo_full_name,
                            "url": repo_url,
                            "description": description,
                            "language": repo_language,
                            "stars_today": stars_today,
                            "time_range": ""
                        })
                        
                    except Exception as e:
                        logger.warning(f"解析单个仓库失败: {e}")
                        continue
                
                if trending_repos:
                    logger.info(f"从 {url} 成功获取 {len(trending_repos)} 个仓库")
                    return True, trending_repos, None
                else:
                    return False, [], Exception("未找到仓库")
                    
        except self.RETRYABLE_EXCEPTIONS as e:
            logger.warning(f"网络错误 [{type(e).__name__}]: {url}, 错误: {e}")
            return False, [], e
        except httpx.HTTPStatusError as e:
            # 4xx 错误不重试
            if 400 <= e.response.status_code < 500:
                logger.error(f"HTTP 客户端错误 [{e.response.status_code}]: {url}")
                return False, [], e
            # 5xx 错误可以重试
            logger.warning(f"HTTP 服务器错误 [{e.response.status_code}]: {url}")
            return False, [], e
        except Exception as e:
            logger.warning(f"抓取异常: {url}, 错误: {e}")
            return False, [], e

    async def fetch_trending_repos(
        self,
        time_range: Literal["daily", "weekly", "monthly"] = "daily",
        language: str = ""
    ) -> List[Dict[str, Any]]:
        """
        从 GitHub Trending 页面抓取热门仓库（支持代理和镜像 fallback，每个 URL 最多重试 10 次）
        
        Args:
            time_range: 时间范围 - daily(今日), weekly(本周), monthly(本月)
            language: 编程语言筛选（默认空表示所有语言）
        
        Returns:
            包含仓库基本信息的字典列表
        """
        urls_to_try = self._build_fallback_urls(time_range, language)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
        }
        
        last_error = None
        
        for url, proxy in urls_to_try:
            # 每个 URL 最多重试 10 次
            for retry_count in range(self.MAX_RETRIES):
                success, repos, error = await self._fetch_single_url(url, proxy, headers, retry_count)
                
                if success and repos:
                    # 更新 time_range
                    for repo in repos:
                        repo["time_range"] = time_range
                    return repos
                
                last_error = error
                
                # 判断是否应该重试
                if error and isinstance(error, httpx.HTTPStatusError):
                    if 400 <= error.response.status_code < 500:
                        # 4xx 错误不重试，直接尝试下一个 URL
                        break
                
                # 指数退避等待
                if retry_count < self.MAX_RETRIES - 1:
                    wait_time = min(2 ** retry_count, 60)  # 最大 60 秒
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    await asyncio.sleep(wait_time)
        
        logger.error(f"所有访问方式均失败，最后错误: {last_error}")
        return []
    
    def is_ai_related(self, repo_info: Dict[str, Any]) -> bool:
        """
        判断仓库是否与 AI 相关
        
        Args:
            repo_info: 仓库信息字典
        
        Returns:
            是否AI相关
        """
        text_to_check = f"{repo_info.get('description', '')} {repo_info.get('full_name', '')}".lower()
        
        for keyword in self.AI_KEYWORDS:
            if keyword.lower() in text_to_check:
                return True
        
        return False
    
    async def get_repo_details_from_api(self, full_name: str) -> Optional[Repository]:
        """
        使用 GitHub API 获取仓库详细信息
        
        Args:
            full_name: 仓库全名 (owner/repo)
        
        Returns:
            Repository 对象或 None
        """
        if not self.is_available:
            return None
        
        try:
            def fetch_repo():
                return self.client.get_repo(full_name)
            
            repo = await asyncio.get_event_loop().run_in_executor(None, fetch_repo)
            return repo
        except GithubException as e:
            logger.warning(f"获取仓库详情失败 [{full_name}]: {e}")
            return None
        except Exception as e:
            logger.error(f"API 调用异常 [{full_name}]: {e}")
            return None
    
    async def fetch_repo_details(self, repo: Repository) -> Dict[str, Any]:
        """
        获取仓库详细信息（README、代码文件等）
        
        Args:
            repo: GitHub Repository对象
        
        Returns:
            包含README和核心代码的详情字典
        """
        details = {
            "readme_content": "",
            "code_files": {}
        }
        
        try:
            # 获取README
            try:
                readme = await asyncio.get_event_loop().run_in_executor(
                    None,
                    repo.get_readme
                )
                details["readme_content"] = readme.decoded_content.decode("utf-8", errors="ignore")
            except Exception as e:
                logger.warning(f"获取README失败 [{repo.full_name}]: {e}")
            
            # 获取核心代码文件
            try:
                contents = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: repo.get_contents("")
                )
                
                # 查找核心文件
                files_to_fetch = []
                for content in contents:
                    if content.type == "file" and content.name.lower() in [
                        "main.py", "app.py", "run.py", "index.py", "agent.py",
                        "main.ts", "index.ts", "app.ts",
                        "main.js", "index.js", "app.js"
                    ]:
                        files_to_fetch.append(content)
                
                # 获取文件内容（最多3个）
                for content in files_to_fetch[:3]:
                    try:
                        file_content = await asyncio.get_event_loop().run_in_executor(
                            None,
                            lambda c=content: c.decoded_content.decode("utf-8", errors="ignore")
                        )
                        details["code_files"][content.name] = file_content
                    except Exception as e:
                        logger.warning(f"获取文件内容失败 [{content.name}]: {e}")
                        
            except Exception as e:
                logger.warning(f"获取仓库内容失败 [{repo.full_name}]: {e}")
                
        except Exception as e:
            logger.error(f"获取仓库详情失败 [{repo.full_name}]: {e}")
        
        return details
    
    async def analyze_repo(
        self,
        repo: Repository,
        details: Dict[str, Any],
        stars_today: int = 0
    ) -> GitHubDigestItem:
        """
        使用Gemini分析单个仓库
        
        Args:
            repo: GitHub Repository对象
            details: 仓库详情（README、代码文件等）
            stars_today: 今日新增star数
        
        Returns:
            GitHubDigestItem 分析结果
        """
        # 基础信息
        item = GitHubDigestItem(
            repo_name=repo.full_name,
            repo_url=repo.html_url,
            stars=repo.stargazers_count,
            stars_today=stars_today,
            forks=repo.forks_count,
            description=repo.description or "",
            main_language=repo.language or "Unknown",
            topics=repo.get_topics() if hasattr(repo, 'get_topics') else [],
            created_at=repo.created_at.isoformat() if repo.created_at else None,
            updated_at=repo.updated_at.isoformat() if repo.updated_at else None
        )
        
        # 使用Gemini进行深度分析
        if gemini_analyzer.is_available and details.get("readme_content"):
            try:
                analysis = await gemini_analyzer.analyze_github_repo(
                    repo_name=repo.full_name,
                    description=repo.description or "",
                    language=repo.language or "Unknown",
                    stars=repo.stargazers_count,
                    readme_content=details.get("readme_content", ""),
                    code_files=details.get("code_files")
                )
                
                item.summary = analysis.get("summary", "")
                item.why_trending = analysis.get("why_trending", "")
                item.key_innovations = analysis.get("key_innovations", [])
                item.practical_value = analysis.get("practical_value", "")
                item.learning_points = analysis.get("learning_points", [])
                
            except Exception as e:
                logger.error(f"Gemini分析失败 [{repo.full_name}]: {e}")
                item.summary = truncate_text(repo.description or "无描述", 200)
        else:
            # 无Gemini时使用基础描述
            item.summary = truncate_text(repo.description or "无描述", 200)
        
        return item
    
    async def get_trending_repos(
        self,
        time_range: Literal["daily", "weekly", "monthly"] = "daily"
    ) -> List[GitHubDigestItem]:
        """
        从 GitHub Trending 获取Top N热门AI仓库（完整流程）
        
        Args:
            time_range: 时间范围 - daily(今日), weekly(本周), monthly(本月)
        
        Returns:
            GitHubDigestItem列表
        """
        logger.info(f"开始从 GitHub Trending 获取 [{time_range}] Top{self.top_n} 热门AI仓库...")
        
        # 1. 从 Trending 页面抓取仓库列表
        trending_data = await self.fetch_trending_repos(time_range=time_range)
        
        if not trending_data:
            logger.warning("未能从 Trending 页面获取任何仓库")
            return []
        
        # 2. 筛选AI相关的仓库
        ai_repos = [r for r in trending_data if self.is_ai_related(r)]
        logger.info(f"筛选出 {len(ai_repos)} 个AI相关仓库")
        
        # 如果没有AI相关的，取前top_n个
        if not ai_repos:
            ai_repos = trending_data[:self.top_n]
            logger.info(f"未找到AI相关仓库，使用前 {len(ai_repos)} 个热门仓库")
        
        # 3. 并发获取详情和分析
        results: List[GitHubDigestItem] = []
        
        for repo_info in ai_repos[:self.top_n]:
            try:
                # 使用API获取完整仓库信息（如果有Token）
                repo = await self.get_repo_details_from_api(repo_info["full_name"])
                
                if repo:
                    # 有API详情时进行完整分析
                    details = await self.fetch_repo_details(repo)
                    item = await self.analyze_repo(
                        repo, 
                        details, 
                        stars_today=repo_info.get("stars_today", 0)
                    )
                else:
                    # 无API时使用Trending页面数据创建基础项
                    logger.info(f"使用基础数据: {repo_info['full_name']}")
                    item = GitHubDigestItem(
                        repo_name=repo_info["full_name"],
                        repo_url=repo_info["url"],
                        stars=0,  # 无法获取总star数
                        stars_today=repo_info.get("stars_today", 0),
                        forks=0,
                        description=repo_info.get("description", ""),
                        main_language=repo_info.get("language", "Unknown"),
                        topics=[],
                        summary=truncate_text(repo_info.get("description", "无描述"), 200)
                    )
                
                results.append(item)
                
                if repo:
                    logger.info(f"完成分析: {repo.full_name} ⭐{repo.stargazers_count} (+{item.stars_today})")
                else:
                    logger.info(f"完成基础数据: {item.repo_name} (+{item.stars_today})")
                
                # 避免API限流
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"处理仓库失败 [{repo_info.get('full_name', 'unknown')}]: {e}")
                continue
        
        # 4. 最终排序（按今日新增stars）
        results.sort(key=lambda x: x.stars_today, reverse=True)
        
        logger.info(f"GitHub Agent 完成，共获取 {len(results)} 个项目")
        return results[:self.top_n]
    
    # 保持向后兼容的方法
    async def get_top_repos(
        self,
        keywords: Optional[List[str]] = None,
        days_ago: int = 1
    ) -> List[GitHubDigestItem]:
        """
        获取Top N热门AI仓库（向后兼容）
        
        现在直接调用 get_trending_repos
        """
        return await self.get_trending_repos(time_range="daily")


# 全局实例
github_agent = GitHubAgent()