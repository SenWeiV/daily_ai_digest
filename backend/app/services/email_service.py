"""
邮件服务 - Gmail SMTP 发送每日摘要邮件
"""

import logging
import ssl
from html import escape
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date
from typing import List, Optional

import aiosmtplib
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.schemas import GitHubDigestItem, ArxivDigestItem, YouTubeDigestItem
from app.utils.helpers import format_number

logger = logging.getLogger(__name__)


class EmailService:
    """邮件发送服务"""
    
    def __init__(self):
        """初始化邮件服务"""
        # 优先使用新配置，兼容旧配置
        self.smtp_server = settings.smtp_server
        self.smtp_port = settings.smtp_port
        self.use_ssl = settings.smtp_use_ssl
        
        # 发件人信息（优先新配置，兼容旧配置）
        self.sender_email = settings.email_sender or settings.gmail_sender
        self.app_password = settings.email_password or settings.gmail_app_password
        self.recipient_email = settings.email_recipient or settings.digest_recipient or self.sender_email
        
        if self.sender_email and self.app_password:
            logger.info(f"邮件服务初始化完成，发件人: {self.sender_email}, SMTP: {self.smtp_server}:{self.smtp_port}")
        else:
            logger.warning("邮件服务未配置完整")
    
    @property
    def is_configured(self) -> bool:
        """检查邮件服务是否配置完整"""
        return bool(self.sender_email and self.app_password and self.recipient_email)
    
    def _generate_html_template(
        self,
        digest_date: date,
        github_items: List[GitHubDigestItem],
        youtube_items: List[YouTubeDigestItem],
        arxiv_items: Optional[List[ArxivDigestItem]] = None,
        daily_summary: Optional[str] = None
    ) -> str:
        """生成HTML邮件模板"""
        
        # GitHub 项目列表
        github_html = ""
        for i, item in enumerate(github_items, 1):
            innovations = "".join([f"<li>{p}</li>" for p in item.key_innovations[:3]]) if item.key_innovations else ""
            github_html += f"""
            <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 16px; border-left: 4px solid #2ea44f;">
                <h3 style="margin: 0 0 8px 0; color: #24292f;">
                    {i}. <a href="{item.repo_url}" style="color: #0969da; text-decoration: none;">{item.repo_name}</a>
                    <span style="color: #57606a; font-size: 14px; font-weight: normal;">
                        ⭐ {format_number(item.stars)} {f'(+{item.stars_today})' if item.stars_today > 0 else ''}
                    </span>
                </h3>
                <p style="color: #57606a; margin: 0 0 8px 0; font-size: 14px;">
                    {item.main_language or 'Unknown'} • {item.description[:100] + '...' if item.description and len(item.description) > 100 else item.description or ''}
                </p>
                <div style="margin: 12px 0;">
                    <strong style="color: #24292f;">📝 项目总结:</strong>
                    <p style="margin: 4px 0; color: #24292f;">{item.summary or '暂无总结'}</p>
                </div>
                <div style="margin: 12px 0;">
                    <strong style="color: #24292f;">🔥 为什么火:</strong>
                    <p style="margin: 4px 0; color: #24292f;">{item.why_trending or '暂无分析'}</p>
                </div>
                {f'<div style="margin: 12px 0;"><strong style="color: #24292f;">💡 关键创新:</strong><ul style="margin: 4px 0; padding-left: 20px; color: #24292f;">{innovations}</ul></div>' if innovations else ''}
                <div style="margin: 12px 0;">
                    <strong style="color: #24292f;">🎯 实用价值:</strong>
                    <p style="margin: 4px 0; color: #24292f;">{item.practical_value or '暂无'}</p>
                </div>
            </div>
            """

        arxiv_items = arxiv_items or []
        arxiv_html = ""
        for i, item in enumerate(arxiv_items, 1):
            title = escape(item.title)
            arxiv_url = escape(item.arxiv_url, quote=True)
            authors = escape(", ".join(item.authors[:5]))
            summary = escape(item.summary or item.abstract[:600])
            grade = escape(item.quality_grade)
            categories = escape(", ".join(item.categories))
            arxiv_html += f"""
            <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 16px; border-left: 4px solid #8250df;">
                <h3 style="margin: 0 0 8px 0; color: #24292f;">
                    {i}. <a href="{arxiv_url}" style="color: #0969da; text-decoration: none;">{title}</a>
                </h3>
                <p style="margin: 4px 0; color: #57606a;">{authors}</p>
                <p style="margin: 8px 0; color: #24292f;">{summary}</p>
                <p style="margin: 4px 0; color: #57606a;">质量: {grade} · {categories}</p>
            </div>
            """

        # YouTube 视频列表
        youtube_html = ""
        for i, item in enumerate(youtube_items, 1):
            key_points = "".join([f"<li>{p}</li>" for p in item.key_points[:5]]) if item.key_points else ""
            youtube_html += f"""
            <div style="background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 16px; border-left: 4px solid #ff0000;">
                <h3 style="margin: 0 0 8px 0; color: #24292f;">
                    {i}. <a href="{item.video_url}" style="color: #0969da; text-decoration: none;">{item.title}</a>
                </h3>
                <p style="color: #57606a; margin: 0 0 8px 0; font-size: 14px;">
                    📺 {item.channel} • 👀 {format_number(item.view_count)} 观看 • ⏱️ {item.duration}
                </p>
                <div style="margin: 12px 0;">
                    <strong style="color: #24292f;">📝 内容总结:</strong>
                    <p style="margin: 4px 0; color: #24292f;">{item.content_summary or '暂无总结'}</p>
                </div>
                {f'<div style="margin: 12px 0;"><strong style="color: #24292f;">🎯 核心观点:</strong><ul style="margin: 4px 0; padding-left: 20px; color: #24292f;">{key_points}</ul></div>' if key_points else ''}
                <div style="margin: 12px 0;">
                    <strong style="color: #24292f;">🔥 为什么受欢迎:</strong>
                    <p style="margin: 4px 0; color: #24292f;">{item.why_popular or '暂无分析'}</p>
                </div>
                <div style="margin: 12px 0;">
                    <strong style="color: #24292f;">💡 实用收获:</strong>
                    <p style="margin: 4px 0; color: #24292f;">{item.practical_takeaways or '暂无'}</p>
                </div>
            </div>
            """
        
        # 完整HTML模板
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily AI Digest - {digest_date.strftime('%Y-%m-%d')}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; line-height: 1.6; color: #24292f; max-width: 800px; margin: 0 auto; padding: 20px; background: #ffffff;">
    
    <!-- Header -->
    <div style="text-align: center; padding: 24px 0; border-bottom: 2px solid #e1e4e8;">
        <h1 style="margin: 0; color: #24292f; font-size: 28px;">🤖 Daily AI Digest</h1>
        <p style="margin: 8px 0 0 0; color: #57606a; font-size: 16px;">{digest_date.strftime('%Y年%m月%d日')} AI领域热点情报</p>
    </div>
    
    <!-- 统计概览 -->
    <div style="display: flex; justify-content: space-around; padding: 24px 0; border-bottom: 1px solid #e1e4e8; text-align: center;">
        <div>
            <div style="font-size: 32px; font-weight: bold; color: #2ea44f;">🐙 {len(github_items)}</div>
            <div style="color: #57606a;">GitHub 热门项目</div>
        </div>
        <div>
            <div style="font-size: 32px; font-weight: bold; color: #8250df;">📄 {len(arxiv_items)}</div>
            <div style="color: #57606a;">arXiv 论文</div>
        </div>
        <div>
            <div style="font-size: 32px; font-weight: bold; color: #ff0000;">📺 {len(youtube_items)}</div>
            <div style="color: #57606a;">YouTube 热门视频</div>
        </div>
    </div>
    
    {f'''
    <!-- 每日总结 -->
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; margin: 24px 0; color: white;">
        <h2 style="margin: 0 0 12px 0; font-size: 18px;">📊 今日AI领域概览</h2>
        <p style="margin: 0; font-size: 15px; line-height: 1.8;">{daily_summary}</p>
    </div>
    ''' if daily_summary else ''}
    
    <!-- GitHub Top 10 -->
    <div style="margin: 32px 0;">
        <h2 style="color: #24292f; border-bottom: 2px solid #2ea44f; padding-bottom: 8px; display: flex; align-items: center;">
            <span style="font-size: 24px; margin-right: 8px;">??</span> GitHub Top {len(github_items)}
        </h2>
        {github_html if github_html else '<p style="color: #57606a;">暂无数据</p>'}
    </div>
    
    <!-- arXiv papers -->
    <div style="margin: 32px 0;">
        <h2 style="color: #24292f; border-bottom: 2px solid #8250df; padding-bottom: 8px;">arXiv 精选 {len(arxiv_items)}</h2>
        {arxiv_html if arxiv_html else '<p style="color: #57606a;">暂无数据</p>'}
    </div>

    <!-- YouTube Top 10 -->
    <div style="margin: 32px 0;">
        <h2 style="color: #24292f; border-bottom: 2px solid #ff0000; padding-bottom: 8px; display: flex; align-items: center;">
            <span style="font-size: 24px; margin-right: 8px;">??</span> YouTube Top {len(youtube_items)}
        </h2>
        {youtube_html if youtube_html else '<p style="color: #57606a;">暂无数据</p>'}
    </div>
    
    <!-- Footer -->
    <div style="text-align: center; padding: 24px 0; border-top: 1px solid #e1e4e8; color: #57606a; font-size: 14px;">
        <p style="margin: 0;">由 <strong>Daily AI Digest</strong> 自动生成</p>
        <p style="margin: 8px 0 0 0;">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
</body>
</html>
"""
        return html
    
    def _generate_plain_text(
        self,
        digest_date: date,
        github_items: List[GitHubDigestItem],
        youtube_items: List[YouTubeDigestItem],
        arxiv_items: Optional[List[ArxivDigestItem]] = None,
        daily_summary: Optional[str] = None
    ) -> str:
        """生成纯文本邮件内容"""

        arxiv_items = arxiv_items or []
        lines = [
            "=" * 60,
            f"🤖 Daily AI Digest - {digest_date.strftime('%Y年%m月%d日')}",
            "=" * 60,
            "",
            f"📊 今日概览: GitHub {len(github_items)} 个 | arXiv {len(arxiv_items)} 篇 | YouTube {len(youtube_items)} 个",
            "",
        ]
        
        if daily_summary:
            lines.extend([
                "📝 今日总结:",
                daily_summary,
                "",
            ])
        
        # GitHub
        lines.extend([
            "-" * 60,
            f"🐙 GitHub Top {len(github_items)}",
            "-" * 60,
            "",
        ])
        
        for i, item in enumerate(github_items, 1):
            lines.extend([
                f"{i}. {item.repo_name} ⭐{format_number(item.stars)}",
                f"   链接: {item.repo_url}",
                f"   总结: {item.summary or '暂无'}",
                f"   为什么火: {item.why_trending or '暂无'}",
                "",
            ])
        
        # arXiv
        lines.extend([
            "-" * 60,
            f"📄 arXiv 精选 {len(arxiv_items)}",
            "-" * 60,
            "",
        ])
        for i, item in enumerate(arxiv_items, 1):
            lines.extend([
                f"{i}. {item.title}",
                f"   链接: {item.arxiv_url}",
                f"   总结: {item.summary or item.abstract[:600]}",
                "",
            ])

        # YouTube
        lines.extend([
            "-" * 60,
            f"📺 YouTube Top {len(youtube_items)}",
            "-" * 60,
            "",
        ])
        
        for i, item in enumerate(youtube_items, 1):
            lines.extend([
                f"{i}. {item.title}",
                f"   频道: {item.channel} | 观看: {format_number(item.view_count)}",
                f"   链接: {item.video_url}",
                f"   总结: {item.content_summary or '暂无'}",
                "",
            ])
        
        lines.extend([
            "=" * 60,
            "由 Daily AI Digest 自动生成",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ])
        
        return "\n".join(lines)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def send_digest_email(
        self,
        digest_date: date,
        github_items: List[GitHubDigestItem],
        youtube_items: List[YouTubeDigestItem],
        arxiv_items: Optional[List[ArxivDigestItem]] = None,
        daily_summary: Optional[str] = None,
        recipient: Optional[str] = None,
        subject_suffix: str = "Daily"
    ) -> bool:
        """
        发送每日/每周/每月摘要邮件
        
        Args:
            digest_date: 摘要日期
            github_items: GitHub项目列表
            youtube_items: YouTube视频列表
            daily_summary: 每日总结
            recipient: 收件人（可选，默认使用配置）
            subject_suffix: 邮件主题后缀 (Daily/Weekly/Monthly)
        
        Returns:
            是否发送成功
        """
        if not self.is_configured:
            logger.error("邮件服务未配置完整，无法发送")
            return False
        
        recipient = recipient or self.recipient_email
        
        try:
            # 创建邮件
            msg = MIMEMultipart("alternative")
            arxiv_items = arxiv_items or []
            msg["Subject"] = f"🤖 {subject_suffix} AI Digest - {digest_date.strftime('%Y-%m-%d')} | GitHub {len(github_items)} + arXiv {len(arxiv_items)} + YouTube {len(youtube_items)}"
            msg["From"] = self.sender_email
            msg["To"] = recipient
            
            # 纯文本版本
            text_content = self._generate_plain_text(
                digest_date,
                github_items,
                youtube_items,
                arxiv_items=arxiv_items,
                daily_summary=daily_summary,
            )
            part1 = MIMEText(text_content, "plain", "utf-8")
            
            # HTML版本
            html_content = self._generate_html_template(
                digest_date,
                github_items,
                youtube_items,
                arxiv_items=arxiv_items,
                daily_summary=daily_summary,
            )
            part2 = MIMEText(html_content, "html", "utf-8")
            
            # 添加到邮件（先纯文本后HTML，邮件客户端会优先显示HTML）
            msg.attach(part1)
            msg.attach(part2)
            
            # 发送邮件
            context = ssl.create_default_context()
            
            # 根据配置选择连接方式
            if self.use_ssl:
                # SSL 直连（163/QQ 邮箱使用端口 465）
                async with aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    use_tls=True,
                    tls_context=context
                ) as server:
                    await server.login(self.sender_email, self.app_password)
                    await server.sendmail(self.sender_email, recipient, msg.as_string())
            else:
                # STARTTLS（Gmail 使用端口 587）
                async with aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    use_tls=False
                ) as server:
                    await server.starttls(context=context)
                    await server.login(self.sender_email, self.app_password)
                    await server.sendmail(self.sender_email, recipient, msg.as_string())
            
            logger.info(f"邮件发送成功: {recipient}")
            return True
            
        except aiosmtplib.errors.SMTPAuthenticationError as e:
            logger.error(f"邮件认证失败: {e}")
            raise
        except aiosmtplib.errors.SMTPException as e:
            logger.error(f"邮件发送失败: {e}")
            raise
        except Exception as e:
            logger.error(f"邮件发送异常: {e}")
            raise
    
    async def send_test_email(self, recipient: Optional[str] = None) -> bool:
        """
        发送测试邮件
        
        Args:
            recipient: 收件人
        
        Returns:
            是否发送成功
        """
        if not self.is_configured:
            logger.error("邮件服务未配置完整")
            return False
        
        recipient = recipient or self.recipient_email
        
        try:
            msg = MIMEMultipart()
            msg["Subject"] = "🤖 Daily AI Digest - 测试邮件"
            msg["From"] = self.sender_email
            msg["To"] = recipient
            
            body = """
            <html>
            <body>
                <h1>✅ 邮件服务测试成功！</h1>
                <p>Daily AI Digest 邮件服务已正确配置。</p>
                <p>您将在每天早上8点收到AI领域热点情报摘要。</p>
            </body>
            </html>
            """
            msg.attach(MIMEText(body, "html", "utf-8"))
            
            context = ssl.create_default_context()
            
            # 根据配置选择连接方式
            if self.use_ssl:
                # SSL 直连（163/QQ 邮箱使用端口 465）
                async with aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    use_tls=True,
                    tls_context=context
                ) as server:
                    await server.login(self.sender_email, self.app_password)
                    await server.sendmail(self.sender_email, recipient, msg.as_string())
            else:
                # STARTTLS（Gmail 使用端口 587）
                async with aiosmtplib.SMTP(
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    use_tls=False
                ) as server:
                    await server.starttls(context=context)
                    await server.login(self.sender_email, self.app_password)
                    await server.sendmail(self.sender_email, recipient, msg.as_string())
            
            logger.info(f"测试邮件发送成功: {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"测试邮件发送失败: {e}")
            return False


# 全局实例
email_service = EmailService()