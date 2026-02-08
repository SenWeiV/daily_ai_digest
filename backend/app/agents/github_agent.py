"""
GitHub Agent - 检索和分析GitHub热门AI项目
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from github import Github, GithubException
from github.Repository import Repository

from app.config import settings
from app.schemas import GitHubDigestItem
from app.agents.gemini_analyzer import gemini_analyzer
from app.utils.helpers import get_yesterday, truncate_text

logger = logging.getLogger(__name__)


class GitHubAgent:
    """GitHub 热门项目检索和分析 Agent"""
    
    # AI/AGI/AI Agent 相关搜索关键词
    SEARCH_KEYWORDS = [
        "AI agent",
        "LLM agent",
        "autonomous agent",
        "AGI artificial general intelligence",
        "large language model",
        "GPT-4 GPT-5",
        "Claude Anthropic",
        "Gemini AI",
        "RAG retrieval augmented",
        "multi-agent system",
        "AI coding assistant",
        "AI workflow automation",
        "reasoning AI",
        "agentic AI"
    ]
    
    # 核心文件名模式（用于识别入口文件）
    CORE_FILE_PATTERNS = [
        "main.py", "app.py", "run.py", "index.py",
        "main.ts", "index.ts", "app.ts",
        "main.js", "index.js", "app.js",
        "agent.py", "llm.py", "core.py",
        "src/main.py", "src/index.py", "src/app.py"
    ]
    
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
        """检查 GitHub 客户端是否可用"""
        return self.client is not None
    
    async def search_trending_repos(
        self,
        keywords: Optional[List[str]] = None,
        days_ago: int = 1,
        min_stars: int = 50
    ) -> List[Repository]:
        """
        搜索过去24小时内 star 增长最快的 AI 相关仓库
        
        策略：搜索最近 N 天内有更新（pushed）的项目，按 star 排序
        活跃更新 + 高 star = 近期热门（star增长快的项目通常也在活跃更新）
        
        Args:
            keywords: 搜索关键词列表
            days_ago: 搜索最近N天内有更新的项目（默认1天=24小时）
            min_stars: 最小Star数过滤（默认50）
        
        Returns:
            Repository对象列表
        """
        if not self.is_available:
            logger.error("GitHub 客户端未初始化")
            return []
        
        keywords = keywords or self.SEARCH_KEYWORDS
        target_date = datetime.now() - timedelta(days=days_ago)
        date_str = target_date.strftime("%Y-%m-%d")
        
        all_repos: Dict[str, Repository] = {}
        
        for keyword in keywords:
            try:
                # 构建搜索查询：搜索最近N天内有更新的项目，按star排序
                # 活跃更新 + 高star = 近期热门
                query = f"{keyword} pushed:>={date_str} stars:>={min_stars}"
                
                # 异步执行搜索（GitHub API是同步的，放到线程池）
                def search_repos(q):
                    try:
                        result = self.client.search_repositories(
                            query=q,
                            sort="stars",
                            order="desc"
                        )
                        # 安全地获取前20个结果
                        repos_list = []
                        for i, repo in enumerate(result):
                            if i >= 20:
                                break
                            repos_list.append(repo)
                        return repos_list
                    except Exception as e:
                        logger.warning(f"搜索执行失败: {e}")
                        return []
                
                repos = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: search_repos(query)
                )
                
                # 去重并合并
                for repo in repos:
                    if repo.full_name not in all_repos:
                        all_repos[repo.full_name] = repo
                
                logger.info(f"关键词 '{keyword}' 找到 {len(repos)} 个新项目")
                
                # 避免触发GitHub API限流
                await asyncio.sleep(0.5)
                
            except GithubException as e:
                logger.error(f"搜索关键词 '{keyword}' 失败: {e}")
                continue
            except Exception as e:
                logger.error(f"搜索异常: {e}")
                continue
        
        # 按Star数排序（新项目中star最高的 = 增长最快）
        sorted_repos = sorted(
            all_repos.values(),
            key=lambda r: r.stargazers_count,
            reverse=True
        )
        
        logger.info(f"共找到 {len(sorted_repos)} 个去重后的活跃项目（最近{days_ago}天更新）")
        return sorted_repos[:self.top_n * 2]
    
    async def fetch_repo_details(self, repo: Repository) -> Dict[str, Any]:
        """
        获取仓库详细信息
        
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
        details: Dict[str, Any]
    ) -> GitHubDigestItem:
        """
        使用Gemini分析单个仓库
        
        Args:
            repo: GitHub Repository对象
            details: 仓库详情（README、代码文件等）
        
        Returns:
            GitHubDigestItem 分析结果
        """
        # 基础信息
        item = GitHubDigestItem(
            repo_name=repo.full_name,
            repo_url=repo.html_url,
            stars=repo.stargazers_count,
            stars_today=0,  # 需要额外API获取，暂时为0
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
    
    async def get_top_repos(
        self,
        keywords: Optional[List[str]] = None,
        days_ago: int = 1
    ) -> List[GitHubDigestItem]:
        """
        获取Top N热门AI仓库（完整流程）
        
        Args:
            keywords: 搜索关键词
            days_ago: 搜索时间范围（天）
        
        Returns:
            GitHubDigestItem列表
        """
        logger.info(f"开始获取GitHub Top{self.top_n}热门仓库...")
        
        # 1. 搜索热门仓库
        repos = await self.search_trending_repos(keywords, days_ago)
        
        if not repos:
            logger.warning("未找到任何仓库")
            return []
        
        # 2. 并发获取详情和分析
        results: List[GitHubDigestItem] = []
        
        for repo in repos[:self.top_n]:
            try:
                # 获取详情
                details = await self.fetch_repo_details(repo)
                
                # 分析
                item = await self.analyze_repo(repo, details)
                results.append(item)
                
                logger.info(f"完成分析: {repo.full_name} ⭐{repo.stargazers_count}")
                
                # 避免API限流
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"处理仓库失败 [{repo.full_name}]: {e}")
                continue
        
        # 3. 最终排序
        results.sort(key=lambda x: x.stars, reverse=True)
        
        logger.info(f"GitHub Agent 完成，共获取 {len(results)} 个项目")
        return results[:self.top_n]


# 全局实例
github_agent = GitHubAgent()