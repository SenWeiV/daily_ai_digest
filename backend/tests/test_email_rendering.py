from datetime import date

from app.schemas import ArxivDigestItem, GitHubDigestItem, YouTubeDigestItem
from app.services.email_service import EmailService


def test_email_renders_arxiv_without_changing_youtube_section():
    service = EmailService()
    github = [GitHubDigestItem(repo_name="org/repo", repo_url="https://github.com/org/repo", stars=3)]
    arxiv = [
        ArxivDigestItem(
            arxiv_id="2501.01234",
            title="A useful paper",
            abstract="A method and evaluation.",
            authors=["A. Researcher"],
            categories=["cs.AI"],
            arxiv_url="https://arxiv.org/abs/2501.01234",
            quality_grade="A",
        )
    ]
    youtube = [
        YouTubeDigestItem(
            video_id="video",
            title="Existing YouTube item",
            channel="channel",
            video_url="https://youtube.com/watch?v=video",
            view_count=1,
            like_count=1,
            comment_count=0,
        )
    ]

    html = service._generate_html_template(
        date(2026, 7, 15),
        github,
        youtube,
        arxiv_items=arxiv,
    )
    text = service._generate_plain_text(
        date(2026, 7, 15),
        github,
        youtube,
        arxiv_items=arxiv,
    )

    assert "arXiv 精选 1" in html
    assert "A useful paper" in html
    assert "Existing YouTube item" in html
    assert "arXiv 精选 1" in text
    assert "Existing YouTube item" in text


def test_email_escapes_untrusted_arxiv_feed_fields():
    service = EmailService()
    paper = ArxivDigestItem(
        arxiv_id="2501.09999",
        title='<img src=x onerror="alert(1)">',
        abstract="A <b>method</b> & evaluation.",
        authors=["A. <Researcher>"],
        categories=["cs.AI<script>"],
        arxiv_url='https://arxiv.org/abs/2501.09999?x="bad"',
    )

    html = service._generate_html_template(date(2026, 7, 15), [], [], arxiv_items=[paper])

    assert "<img src=x" not in html
    assert "<b>method</b>" not in html
    assert "<script>" not in html
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html
    assert "A &lt;b&gt;method&lt;/b&gt; &amp; evaluation." in html
