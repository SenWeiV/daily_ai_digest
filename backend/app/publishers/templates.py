"""平台图片模板：从摘要数据排版，而不是从长图裁剪。

裁剪是显而易见的偷懒办法，也是错的：从一张纵向长图里抠一个 3:4 的框，得到
的是任意位置的一刀，上下边缘各切断一行文字。视觉质检会把它判为"边缘截断"，
然后每次重试都得到同一个结果 —— 缺陷在数据到像素的路径上，不在渲染参数里。

所以每张平台图都独立排版：给定条目、给定画幅，自己决定放几条、每条几个字。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from app.publishers.layout import TYPE_SCALE_STEPS, TypeScale, tightened_limit, truncate_to
from app.publishers.styles import IMAGE_FRAMES, PlatformStyle

# 每类画幅承载的条目数与字数上限。数字来自画幅高度与字号的比例，
# 放在这里而不是散在模板字符串里，是为了让质检的降级路径能读到它们。
COVER_TITLE_MAX = 16
COVER_SUBTITLE_MAX = 28
CARD_ITEMS_PER_PAGE = 3
CARD_NAME_MAX = 28
CARD_LINE_MAX = 46
X_TITLE_MAX = 52
X_SUBTITLE_MAX = 64
IG_TITLE_MAX = 34
IG_ITEMS = 3
IG_LINE_MAX = 40


@dataclass(frozen=True)
class CardItem:
    """一条内容在图上的最终形态。已截断，模板不再改动它。"""

    name: str
    line: str


@dataclass(frozen=True)
class PageSpec:
    """一张平台图的完整规格。"""

    slug: str
    platform: str
    width: int
    height: int
    kind: str  # cover / cards / wide / square
    heading: str
    subheading: str = ""
    items: tuple[CardItem, ...] = field(default_factory=tuple)
    scale: TypeScale = TypeScale()
    footer: str = ""


def _digest_lines(items: list[dict]) -> list[CardItem]:
    """把摘要条目压成"名字 + 一句话"。

    一句话优先取 summary，退到 why_trending，再退到 description。三者都空时
    仍然产出这一条，但只有名字 —— 编一句话来填版面会把未经分析的项目
    包装成已分析的。
    """
    lines: list[CardItem] = []
    for item in items:
        name = item.get("repo_name") or item.get("title") or ""
        blurb = item.get("summary") or item.get("why_trending") or item.get("description") or ""
        lines.append(CardItem(name=name.strip(), line=blurb.strip()))
    return lines


def build_page_specs(
    style: PlatformStyle,
    items: list[dict],
    digest_label: str,
    scale: TypeScale = TypeScale(),
    *,
    truncation_attempt: int = 0,
    content_reduction: int = 0,
) -> list[PageSpec]:
    """按平台的 image_slugs 生成页规格。

    条目多于内容页能装的数量时，按摘要顺序取最靠前的；少于时省掉用不到的页，
    而不是产出空白页 —— 空白页在质检里会被判为"文字缺失"，浪费一轮预算。

    `truncation_attempt` 与 `content_reduction` 是质检的两个修正手柄：前者收紧
    每条的字数，后者减少每页放几条。两者都必须真的改变输出，否则重试是原地重放。
    """
    if not style.image_slugs:
        return []

    lines = _digest_lines(items)
    specs: list[PageSpec] = []

    def limit(base: int) -> int:
        return tightened_limit(base, truncation_attempt)

    per_page = max(1, CARD_ITEMS_PER_PAGE - content_reduction)
    ig_items = max(1, IG_ITEMS - content_reduction)
    effective_scale = TypeScale(
        step=min(scale.step + truncation_attempt, len(TYPE_SCALE_STEPS) - 1)
    )

    slugs = list(style.image_slugs)
    if style.key == "xiaohongshu":
        declared_content = sum(slug.startswith("xhs-content-") for slug in slugs)
        required_content = (len(lines) + per_page - 1) // per_page
        next_content = declared_content + 1
        while declared_content < required_content:
            slugs.append(f"xhs-content-{next_content}")
            declared_content += 1
            next_content += 1

    for slug in slugs:
        frame_slug = slug
        if frame_slug not in IMAGE_FRAMES and frame_slug.startswith("xhs-content-"):
            frame_slug = "xhs-content-1"
        width, height = IMAGE_FRAMES[frame_slug]

        if slug.endswith("cover"):
            specs.append(
                PageSpec(
                    slug=slug,
                    platform=style.key,
                    width=width,
                    height=height,
                    kind="cover",
                    heading=truncate_to(f"{digest_label} AI 值得看的 {len(lines)} 件事", limit(COVER_TITLE_MAX)),
                    subheading=truncate_to("GitHub / arXiv 每日精选", limit(COVER_SUBTITLE_MAX)),
                    scale=effective_scale,
                    footer=digest_label,
                )
            )
            continue

        if slug == "x-card":
            head = lines[0] if lines else CardItem("", "")
            specs.append(
                PageSpec(
                    slug=slug,
                    platform=style.key,
                    width=width,
                    height=height,
                    kind="wide",
                    heading=truncate_to(head.name or f"{digest_label} AI digest", limit(X_TITLE_MAX)),
                    subheading=truncate_to(head.line, limit(X_SUBTITLE_MAX)),
                    scale=effective_scale,
                    footer=digest_label,
                )
            )
            continue

        if slug == "ig-square":
            specs.append(
                PageSpec(
                    slug=slug,
                    platform=style.key,
                    width=width,
                    height=height,
                    kind="square",
                    heading=truncate_to(f"{digest_label} AI picks", limit(IG_TITLE_MAX)),
                    items=tuple(
                        CardItem(truncate_to(it.name, limit(CARD_NAME_MAX)), truncate_to(it.line, limit(IG_LINE_MAX)))
                        for it in lines[:ig_items]
                    ),
                    scale=effective_scale,
                    footer=digest_label,
                )
            )
            continue

        # xhs-content-N
        try:
            page_index = int(slug.rsplit("-", 1)[1]) - 1
        except (IndexError, ValueError):
            page_index = 0
        start = page_index * per_page
        chunk = lines[start : start + per_page]
        if not chunk:
            # 条目不够就省掉这一页，不产出空白页
            continue
        specs.append(
            PageSpec(
                slug=slug,
                platform=style.key,
                width=width,
                height=height,
                kind="cards",
                heading=truncate_to(f"{digest_label} · 第 {page_index + 1} 页", limit(COVER_TITLE_MAX)),
                items=tuple(
                    CardItem(truncate_to(it.name, limit(CARD_NAME_MAX)), truncate_to(it.line, limit(CARD_LINE_MAX)))
                    for it in chunk
                ),
                scale=effective_scale,
                footer=digest_label,
            )
        )

    return specs


def expected_texts(spec: PageSpec) -> list[str]:
    """送去质检时要求"必须出现在图上"的文本。

    只列模板真的画了的字段。列上没画的字段会让质检报 missing_text，
    把一张好图判成坏图 —— 假失败只浪费一轮，但连着三轮就等于扣图。
    """
    texts = [spec.heading, spec.subheading, spec.footer]
    for item in spec.items:
        texts.extend((item.name, item.line))
    return [t for t in texts if t.strip()]


def render_page_html(
    spec: PageSpec,
    style: PlatformStyle,
    font_family: str,
    background_data_url: str | None = None,
) -> str:
    """把页规格渲染成一张定宽定高的 HTML。

    配色、留白、字号都从 style.visual 派生，同一平台的多页共用同一套值 ——
    这是"四张图读起来像一个帖子"的实现方式，不是靠提示词请求一致性。

    `background_data_url` 有值时作为底图铺满，并在其上压一层同色半透明遮罩：
    生成的底图亮度不可控，不加遮罩会让某些天的正文落在浅色区域上读不清，
    而"读不清"是质检的失败类别之一。
    """
    palette = style.visual.palette
    accent = palette[0]
    surface = palette[1] if len(palette) > 1 else "#FFFFFF"
    ink = palette[2] if len(palette) > 2 else "#1A1A1A"
    soft = palette[3] if len(palette) > 3 else surface

    if background_data_url:
        body_background = (
            f"linear-gradient(160deg, {surface}d9 0%, {soft}e6 100%), "
            f"url('{background_data_url}') center / cover no-repeat"
        )
    else:
        body_background = f"linear-gradient(160deg, {surface} 0%, {soft} 100%)"

    s = spec.scale
    if spec.kind == "square":
        heading_px = s.px(52)
        sub_px = s.px(36)
        name_px = s.px(34)
        line_px = s.px(25)
        body_padding = round(spec.width * 0.065)
        cards_gap = round(spec.height * 0.014)
        cards_margin = round(spec.height * 0.020)
        card_padding = round(spec.width * 0.025)
        line_height = 1.35
    else:
        heading_px = s.px(96 if spec.kind == "cover" else 60)
        sub_px = s.px(44)
        name_px = s.px(46)
        line_px = s.px(34)
        body_padding = round(spec.width * 0.085)
        cards_gap = round(spec.height * 0.026)
        cards_margin = round(spec.height * 0.035)
        card_padding = round(spec.width * 0.042)
        line_height = 1.5

    blocks = "".join(
        f"""
        <div class="card">
          <div class="name">{escape(item.name)}</div>
          <div class="line">{escape(item.line)}</div>
        </div>"""
        for item in spec.items
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width:{spec.width}px; height:{spec.height}px; }}
  body {{
    font-family: {font_family};
    background: {body_background};
    color: {ink};
    padding: {body_padding}px;
    display: flex; flex-direction: column; justify-content: space-between;
  }}
  .accent-bar {{ width:{round(spec.width * 0.16)}px; height:{max(8, round(spec.height * 0.010))}px;
    background:{accent}; border-radius:999px; }}
  .heading {{ font-size:{heading_px}px; font-weight:800; line-height:1.22; letter-spacing:-0.5px;
    margin-top:{round(spec.height * 0.03)}px; }}
  .sub {{ font-size:{sub_px}px; color:{accent}; font-weight:600;
    margin-top:{round(spec.height * 0.018)}px; }}
  .cards {{ display:flex; flex-direction:column; gap:{cards_gap}px;
    margin-top:{cards_margin}px; }}
  .card {{ background:rgba(255,255,255,0.72); border:2px solid {accent}22;
    border-radius:{round(spec.width * 0.03)}px; padding:{card_padding}px; }}
  .name {{ font-size:{name_px}px; font-weight:700; line-height:1.3; }}
  .line {{ font-size:{line_px}px; color:{ink}bb; line-height:{line_height};
    margin-top:{round(spec.height * 0.010)}px; }}
  .footer {{ font-size:{s.px(30)}px; color:{ink}88; font-weight:500; }}
</style></head>
<body>
  <div>
    <div class="accent-bar"></div>
    <div class="heading">{escape(spec.heading)}</div>
    {f'<div class="sub">{escape(spec.subheading)}</div>' if spec.subheading else ''}
    {f'<div class="cards">{blocks}</div>' if blocks else ''}
  </div>
  <div class="footer">{escape(spec.footer)} · Daily AI Digest</div>
</body></html>"""
