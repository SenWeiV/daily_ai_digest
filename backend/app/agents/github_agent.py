"""
GitHub Agent - 从 GitHub Trending 页面检索热门AI项目
"""

import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any, Literal

import httpx
from bs4 import BeautifulSoup
from github import Github, GithubException
from github.Repository import Repository

from app.config import settings
from app.schemas import GitHubDigestItem
from app.agents.gemini_analyzer import gemini_analyzer
from app.utils.helpers import truncate_text
from app.content_profile import (
    extract_explicit_arxiv_ids,
    github_social_grade,
    is_research_relevant,
    matching_profiles,
    value_evidence,
)

logger = logging.getLogger(__name__)


class GitHubAgent:
    """GitHub Trending 热门项目检索和分析 Agent"""
    
    # GitHub Trending URL
    TRENDING_URL = "https://github.com/trending"
    
    # Narrow queries intentionally combine a research domain and a content signal.
    DEFAULT_SEARCH_QUERIES = (
        '"vision language" benchmark',
        'multimodal evaluation',
        'agent benchmark',
        'agentic workflow framework',
        'llm evaluation dataset',
        'topic:vision-language-model',
        'topic:llm-evaluation',
        'topic:ai-agents',
    )
    
    # Trending 网络异常类型
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
        self._analysis_context: dict[str, Dict[str, Any]] = {}

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
        time_range: Literal["daily", "weekly", "monthly"],
        attempt_number: int = 1,
    ) -> tuple[bool, List[Dict[str, Any]], Optional[Exception]]:
        """
        单个 URL 请求（带重试逻辑）
        
        Args:
            url: 请求 URL
            proxy: 代理地址
            headers: 请求头
            time_range: Trending周期
            attempt_number: 当前全局尝试序号

        Returns:
            (成功标志, 仓库列表, 错误信息)
        """
        try:
            logger.info(
                "正在抓取 GitHub Trending: %s (proxy: %s, 尝试: %s/%s)",
                url,
                proxy or "无",
                attempt_number,
                settings.github_trending_max_attempts,
            )

            client_kwargs = {
                "timeout": settings.github_trending_attempt_timeout_seconds,
                "follow_redirects": True,
            }
            if proxy:
                client_kwargs["proxies"] = proxy
            
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                repo_list = soup.find_all('article', class_='Box-row')
                
                trending_repos = []
                period_days = {"daily": 1, "weekly": 7, "monthly": 30}[time_range]
                for rank, article in enumerate(repo_list, 1):
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
                        recent_stars = 0
                        if stars_tag:
                            stars_text = stars_tag.get_text(strip=True)
                            try:
                                recent_stars = int(stars_text.split()[0].replace(',', ''))
                            except (ValueError, IndexError):
                                pass

                        trending_repos.append({
                            "full_name": repo_full_name,
                            "url": repo_url,
                            "description": description,
                            "language": repo_language,
                            "stars_today": recent_stars,
                            "recent_stars": recent_stars,
                            "recent_star_period_days": period_days,
                            "recent_star_velocity": recent_stars / period_days,
                            "trending_rank": rank,
                            "trending_period": time_range,
                            "source_channel": "trending",
                            "time_range": time_range,
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
        从 GitHub Trending 页面抓取热门仓库（所有访问方式共享全局重试预算）
        
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
        max_attempts = max(1, settings.github_trending_max_attempts)

        for attempt_index in range(max_attempts):
            url, proxy = urls_to_try[attempt_index % len(urls_to_try)]
            success, repos, error = await self._fetch_single_url(
                url,
                proxy,
                headers,
                time_range,
                attempt_number=attempt_index + 1,
            )
            if success and repos:
                return repos

            last_error = error
            should_wait = True
            if isinstance(error, httpx.HTTPStatusError):
                status_code = error.response.status_code
                should_wait = status_code == 429 or status_code >= 500
            if attempt_index < max_attempts - 1 and should_wait:
                wait_time = min(2 ** min(attempt_index, 3), 10)
                logger.info("等待 %s 秒后尝试下一个 Trending 访问方式...", wait_time)
                await asyncio.sleep(wait_time)

        logger.error(
            "GitHub Trending 在 %s 次尝试后仍失败，最后错误: %s",
            max_attempts,
            last_error,
        )
        return []
    
    def is_ai_related(self, repo_info: Dict[str, Any], details: Optional[Dict[str, Any]] = None) -> bool:
        """Require a research profile match instead of a broad keyword hit."""
        details = details or {}
        text_to_check = " ".join(
            [
                str(repo_info.get("description", "")),
                str(repo_info.get("full_name", "")),
                " ".join(repo_info.get("topics") or []),
                str(details.get("readme_content", "")),
            ]
        )
        return is_research_relevant(text_to_check)

    def candidate_quality(self, repo_info: Dict[str, Any], details: Optional[Dict[str, Any]] = None) -> tuple[str, set[str], list[str]]:
        details = details or {}
        text = " ".join(
            [
                str(repo_info.get("description", "")),
                str(repo_info.get("full_name", "")),
                " ".join(repo_info.get("topics") or []),
                str(details.get("readme_content", "")),
            ]
        )
        evidence = value_evidence(repo_info, details)
        topics = matching_profiles(text)
        grade, social_evidence = github_social_grade(
            relevant=bool(topics),
            source_channel=str(repo_info.get("source_channel") or repo_info.get("channel") or "legacy"),
            recent_stars=int(repo_info.get("recent_stars") or 0),
            recent_issue_comments=repo_info.get("recent_issue_comments"),
            forks=int(repo_info.get("forks") or 0),
            watchers=int(repo_info.get("watchers") or 0),
            open_issues=int(repo_info.get("open_issues") or 0),
            min_recent_comments=settings.github_min_recent_comments_a,
            activity_signal_threshold=settings.github_activity_signal_threshold,
        )
        evidence.update(social_evidence)
        return grade, evidence, topics
    
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
            "code_files": {},
            "root_entries": [],
            "topics": [],
        }

        try:
            try:
                details["topics"] = await asyncio.get_event_loop().run_in_executor(
                    None,
                    repo.get_topics,
                )
            except Exception as e:
                logger.warning(f"获取Topics失败 [{repo.full_name}]: {e}")

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
                details["root_entries"] = [content.name for content in contents]

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
        stars_today: int = 0,
        deep_analysis: bool = True,
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
            topics=list(details.get("topics") or []),
            created_at=repo.created_at.isoformat() if repo.created_at else None,
            updated_at=repo.updated_at.isoformat() if repo.updated_at else None
        )
        
        # 使用Gemini进行深度分析
        if deep_analysis and gemini_analyzer.is_available and details.get("readme_content"):
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

    async def analyze_selected_repos(
        self,
        items: List[GitHubDigestItem],
    ) -> List[GitHubDigestItem]:
        """Run model analysis only for candidates retained by the shared selector."""
        analyzed_items: List[GitHubDigestItem] = []
        for item in items:
            context = self._analysis_context.get(item.repo_url.rstrip("/").lower())
            if not context:
                analyzed_items.append(item)
                continue
            try:
                analyzed = await self.analyze_repo(
                    context["repo"],
                    context["details"],
                    stars_today=item.stars_today,
                    deep_analysis=True,
                )
                for field in (
                    "watchers",
                    "open_issues",
                    "recent_issue_comments",
                    "source_channel",
                    "trending_rank",
                    "trending_period",
                    "recent_stars",
                    "recent_star_period_days",
                    "recent_star_velocity",
                    "research_topics",
                    "quality_evidence",
                    "quality_grade",
                    "related_arxiv_ids",
                ):
                    setattr(analyzed, field, getattr(item, field))
                analyzed_items.append(analyzed)
            except Exception as exc:
                logger.warning("GitHub analysis failed [%s]: %s", item.repo_name, exc)
                analyzed_items.append(item)
        return analyzed_items

    def _search_queries(self) -> tuple[str, ...]:
        if settings.github_search_queries.strip():
            return tuple(query.strip() for query in settings.github_search_queries.split(";") if query.strip())
        return self.DEFAULT_SEARCH_QUERIES

    async def search_popular_active_candidates(self) -> list[dict[str, Any]]:
        """Search recently-pushed relevant repositories as a bounded fallback."""
        if not self.client:
            return []

        cutoff = (date.today() - timedelta(days=settings.github_active_project_days)).isoformat()
        queries = self._search_queries()
        per_query = max(1, settings.github_candidate_limit // max(len(queries), 1))

        def run_search(query: str) -> list[Repository]:
            results = self.client.search_repositories(
                query=f"{query} pushed:>={cutoff}",
                sort="stars",
                order="desc",
            )
            return list(results[:per_query])

        candidates: dict[int, dict[str, Any]] = {}
        for query in queries:
            try:
                repos = await asyncio.get_event_loop().run_in_executor(None, run_search, query)
            except GithubException as exc:
                logger.warning("GitHub fallback search failed [%s]: %s", query, exc)
                continue
            for repo in repos:
                candidates[repo.id] = {
                    "repo_id": repo.id,
                    "full_name": repo.full_name,
                    "url": repo.html_url,
                    "description": repo.description or "",
                    "language": repo.language or "Unknown",
                    "stars_today": 0,
                    "recent_stars": 0,
                    "recent_star_period_days": 1,
                    "recent_star_velocity": 0.0,
                    "trending_rank": None,
                    "trending_period": None,
                    "stars": repo.stargazers_count,
                    "forks": repo.forks_count,
                    "watchers": getattr(repo, "subscribers_count", 0) or 0,
                    "open_issues": repo.open_issues_count or 0,
                    "created_at": repo.created_at.isoformat() if repo.created_at else None,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "topics": [],
                    "source_channel": "search",
                    "channel": "search",
                    "repo": repo,
                }

        return sorted(
            candidates.values(),
            key=lambda item: (item.get("stars", 0), item.get("updated_at") or ""),
            reverse=True,
        )[: settings.github_candidate_limit]

    async def fetch_recent_issue_comment_count(self, repo: Repository) -> Optional[int]:
        """Count a bounded sample of recent Issue/PR comments."""
        limit = max(0, settings.github_recent_comment_limit)
        if limit == 0:
            return 0
        since = datetime.now(timezone.utc) - timedelta(days=settings.github_social_window_days)

        def count_comments() -> int:
            comments = repo.get_issues_comments(since=since)
            count = 0
            for _ in comments:
                count += 1
                if count >= limit:
                    break
            return count

        try:
            return await asyncio.get_event_loop().run_in_executor(None, count_comments)
        except Exception as exc:
            logger.warning("获取近期 Issue/PR 评论失败 [%s]: %s", repo.full_name, exc)
            return None

    async def _grade_candidates(
        self,
        candidates: list[dict[str, Any]],
        seen_repo_ids: set[int],
    ) -> list[tuple[dict[str, Any], Repository, dict[str, Any], str, set[str], list[str]]]:
        graded: list[tuple[dict[str, Any], Repository, dict[str, Any], str, set[str], list[str]]] = []
        for repo_info in candidates:
            try:
                repo = repo_info.get("repo") or await self.get_repo_details_from_api(repo_info["full_name"])
                if not repo:
                    continue
                repo_id = int(repo.id)
                if repo_id in seen_repo_ids:
                    continue
                seen_repo_ids.add(repo_id)
                repo_info["repo_id"] = repo_id
                repo_info["stars"] = repo.stargazers_count
                repo_info["forks"] = repo.forks_count
                repo_info["watchers"] = getattr(repo, "subscribers_count", 0) or 0
                repo_info["open_issues"] = repo.open_issues_count or 0
                details = await self.fetch_repo_details(repo)
                repo_info["topics"] = list(details.get("topics") or [])
                if not self.is_ai_related(repo_info, details):
                    continue
                repo_info["recent_issue_comments"] = await self.fetch_recent_issue_comment_count(repo)
                grade, evidence, topics = self.candidate_quality(repo_info, details)
                if grade == "C":
                    continue
                graded.append((repo_info, repo, details, grade, evidence, topics))
            except Exception as exc:
                logger.warning("GitHub candidate failed [%s]: %s", repo_info.get("full_name"), exc)
        return graded

    async def get_research_repos(
        self,
        time_range: Literal["daily", "weekly", "monthly"] = "daily",
    ) -> List[GitHubDigestItem]:
        """Collect and grade bounded candidates without running model analysis."""
        self._analysis_context = {}
        try:
            trending_data = await self.fetch_trending_repos(time_range=time_range)
        except Exception as exc:
            logger.warning("GitHub Trending failed: %s", exc)
            trending_data = []

        trending_by_name: dict[str, dict[str, Any]] = {}
        for item in trending_data:
            item["channel"] = "trending"
            item["source_channel"] = "trending"
            key = str(item.get("full_name") or "").lower()
            if key:
                trending_by_name[key] = item

        # This order decides which Trending items receive bounded API enrichment;
        # final output ordering is applied after grading with all social metrics.
        trending_candidates = sorted(
            trending_by_name.values(),
            key=lambda item: (
                -(item.get("trending_rank") or 10_000),
                item.get("recent_star_velocity", 0.0),
            ),
            reverse=True,
        )
        trending_budget = min(
            len(trending_candidates),
            max(settings.target_items, settings.github_candidate_limit - settings.target_items),
        )
        seen_repo_ids: set[int] = set()
        graded = await self._grade_candidates(
            trending_candidates[:trending_budget],
            seen_repo_ids,
        )

        remaining_budget = max(0, settings.github_candidate_limit - trending_budget)
        if len(graded) < settings.target_items and remaining_budget:
            try:
                search_candidates = await self.search_popular_active_candidates()
            except Exception as exc:
                logger.warning("GitHub fallback Repository Search failed: %s", exc)
                search_candidates = []
            graded.extend(
                await self._grade_candidates(
                    search_candidates[:remaining_budget],
                    seen_repo_ids,
                )
            )

        graded.sort(
            key=lambda row: (
                row[3] == "A",
                row[0].get("source_channel") == "trending",
                row[0].get("recent_star_velocity", 0.0),
                row[0].get("recent_issue_comments") if row[0].get("recent_issue_comments") is not None else -1,
                row[0].get("stars", 0),
                row[0].get("forks", 0) + row[0].get("watchers", 0) + row[0].get("open_issues", 0),
                len(row[4]),
                row[0].get("updated_at") or "",
                str(row[0].get("full_name") or "").lower(),
            ),
            reverse=True,
        )

        results: list[GitHubDigestItem] = []
        for repo_info, repo, details, grade, evidence, topics in graded[: settings.github_candidate_limit]:
            try:
                item = await self.analyze_repo(
                    repo,
                    details,
                    stars_today=repo_info.get("stars_today", 0),
                    deep_analysis=False,
                )
                item.watchers = repo_info.get("watchers", 0)
                item.open_issues = repo_info.get("open_issues", 0)
                item.recent_issue_comments = repo_info.get("recent_issue_comments")
                item.source_channel = repo_info.get("source_channel", "legacy")
                item.trending_rank = repo_info.get("trending_rank")
                item.trending_period = repo_info.get("trending_period")
                item.recent_stars = repo_info.get("recent_stars", 0)
                item.recent_star_period_days = repo_info.get("recent_star_period_days", 1)
                item.recent_star_velocity = repo_info.get("recent_star_velocity", 0.0)
                item.research_topics = topics
                item.quality_evidence = sorted(evidence)
                item.quality_grade = grade
                item.related_arxiv_ids = extract_explicit_arxiv_ids(details.get("readme_content", ""))
                self._analysis_context[item.repo_url.rstrip("/").lower()] = {
                    "repo": repo,
                    "details": details,
                }
                results.append(item)
            except Exception as exc:
                logger.warning("GitHub candidate build failed [%s]: %s", repo.full_name, exc)

        logger.info("GitHub Agent completed with %s qualified projects", len(results))
        return results

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