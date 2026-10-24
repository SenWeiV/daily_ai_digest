"""每个平台的声明式风格定义。

刻意做成可读的结构化数据而不是藏在 prompt 字符串里：运营要改小红书的调性
或配色，应该能改这里的字段，而不是去重写一段提示词。生图提示词与文案提示词
都从这里派生。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CopyStyle:
    """文案侧约束。长度是平台硬限，不是建议值。"""

    tone: str
    structure: str
    title_max_chars: int | None
    body_max_chars: int
    hashtag_min: int
    hashtag_max: int
    language: str
    # X 把 CJK 按两个字符计入 280 上限，用字符串长度算会过校验、发帖被拒
    counts_cjk_as_two: bool = False
    allow_hashtags: bool = True


@dataclass(frozen=True)
class VisualStyle:
    """图片侧风格。palette 用十六进制，方便直接进模板与提示词。"""

    mood: str
    palette: tuple[str, ...]
    background: str
    type_scale: str
    layout_density: str
    decoration: str


@dataclass(frozen=True)
class PlatformStyle:
    key: str
    display_name: str
    copy: CopyStyle
    visual: VisualStyle
    # 该平台对应的图片文件名前缀；无图平台为空
    image_slugs: tuple[str, ...] = field(default_factory=tuple)


PLATFORM_STYLES: dict[str, PlatformStyle] = {
    "xiaohongshu": PlatformStyle(
        key="xiaohongshu",
        display_name="小红书",
        copy=CopyStyle(
            tone="第一人称分享，口语化，带真实获得感但不夸张；标题用明确收益或反差形成点击钩子，不做标题党",
            structure="20字内钩子标题 + 空行分段导语 + 编号要点（每点：是什么/为什么值得看）+ 空行 + 行动建议 + 独立标签行",
            title_max_chars=20,
            body_max_chars=1000,
            hashtag_min=3,
            hashtag_max=10,
            language="zh-CN",
        ),
        visual=VisualStyle(
            mood="明亮、亲和、杂志感",
            palette=("#FF2E4D", "#FFF5F6", "#1A1A1A", "#FFD9DE"),
            background="柔和渐变加轻微纸质纹理",
            type_scale="超大标题，中号正文，强对比",
            layout_density="低密度：一页三条以内，留白充足",
            decoration="圆角色块与细描边图形，不放具体产品截图",
        ),
        image_slugs=("xhs-cover", "xhs-content-1", "xhs-content-2", "xhs-content-3"),
    ),
    "wechat": PlatformStyle(
        key="wechat",
        display_name="微信公众号",
        copy=CopyStyle(
            tone="专业克制，信息密度高，标题清楚指出读者收益，不用网络热词",
            structure="64字内信息型标题 + 导语 + 空行分隔的二级小标题分节（每节一个方向）+ 结语",
            title_max_chars=64,
            body_max_chars=4000,
            hashtag_min=0,
            hashtag_max=0,
            language="zh-CN",
            allow_hashtags=False,
        ),
        visual=VisualStyle(
            mood="稳重、编辑部风格",
            palette=("#07C160", "#FFFFFF", "#2C3033", "#EDF7F0"),
            background="纯色或极浅网格",
            type_scale="标题中号，正文偏小，层级靠字重区分",
            layout_density="中密度：允许成段文字",
            decoration="细分割线与小标记，几乎无插图",
        ),
    ),
    "x": PlatformStyle(
        key="x",
        display_name="X (Twitter)",
        copy=CopyStyle(
            tone="直给，一句一个信息点，无寒暄；首条用可验证的反差、判断或新信息吸引继续阅读",
            structure="首条给钩子与结论，后续每条一个项目，最后一条总结并提问；有序 thread 形式",
            title_max_chars=None,
            body_max_chars=280,
            hashtag_min=0,
            hashtag_max=3,
            language="en",
            counts_cjk_as_two=True,
        ),
        visual=VisualStyle(
            mood="暗色、技术感、高对比",
            palette=("#0F1419", "#1D9BF0", "#E7E9EA", "#536471"),
            background="深色底加细微噪点",
            type_scale="单一大标题加一行副标题",
            layout_density="极低密度：一张卡一个主张",
            decoration="几何线条，无插画",
        ),
        image_slugs=("x-card",),
    ),
    "instagram": PlatformStyle(
        key="instagram",
        display_name="Instagram",
        copy=CopyStyle(
            tone="简洁英文，视觉优先，第一句给出清楚主张或反差，caption 服务于图而不夸大",
            structure="一句 hook + 空行 + 三到五个短要点 + 空行 + 讨论问题 + 独立 hashtags 行",
            title_max_chars=None,
            body_max_chars=2200,
            hashtag_min=3,
            hashtag_max=10,
            language="en",
        ),
        visual=VisualStyle(
            mood="强设计感、饱和色块",
            palette=("#C13584", "#F9F5FF", "#1A1A1A", "#FFC63C"),
            background="大色块拼贴",
            type_scale="居中超大标题",
            layout_density="低密度：正方形内只放标题与三行要点",
            decoration="抽象色块与网格，不含任何品牌标识",
        ),
        image_slugs=("ig-square",),
    ),
    "zhihu": PlatformStyle(
        key="zhihu",
        display_name="知乎",
        copy=CopyStyle(
            tone="解释性写作，标题先提出真实问题，正文先给判断再给依据，允许长句但保持段落清晰",
            structure="问题式标题 + 直接回答 + 空行分节论述 + 每节结论句；不使用标签",
            title_max_chars=100,
            body_max_chars=6000,
            hashtag_min=0,
            hashtag_max=0,
            language="zh-CN",
            allow_hashtags=False,
        ),
        visual=VisualStyle(
            mood="克制、偏学术",
            palette=("#0084FF", "#FFFFFF", "#1A1A1A", "#F0F6FF"),
            background="纯白",
            type_scale="正文为主，标题不抢戏",
            layout_density="高密度：以文字为主",
            decoration="无装饰",
        ),
    ),
    "reddit": PlatformStyle(
        key="reddit",
        display_name="Reddit",
        copy=CopyStyle(
            tone="英文，事实优先，不推销；标题明确指出发现或问题，允许直接说局限",
            structure="300字符内事实型标题 + Markdown TL;DR + 空行 + 项目列表（名称 + 为什么值得看）+ 空行 + 开放问题",
            title_max_chars=300,
            body_max_chars=4000,
            hashtag_min=0,
            hashtag_max=0,
            language="en",
            allow_hashtags=False,
        ),
        visual=VisualStyle(
            mood="朴素，无营销感",
            palette=("#FF4500", "#FFFFFF", "#1A1A1B", "#F6F7F8"),
            background="纯色",
            type_scale="单一层级",
            layout_density="不适用：以纯文本发布",
            decoration="无",
        ),
    ),
}

# 平台图片的逻辑尺寸（未乘 DPR）。存储尺寸 = 逻辑尺寸 × render_device_scale_factor。
#
# 小红书用 1242×1656 而不是流传更广的 1242×1660：后者是 621:830，不是 3:4。
# 平台按 3:4 展示，塞一张 1660 高的图进去会被裁掉 4px —— 裁在哪一边不由我们
# 决定，而这正是本次改动要消灭的"边缘截断"。宁可自己精确到比例，
# 也不要把裁剪权交给平台。
IMAGE_FRAMES: dict[str, tuple[int, int]] = {
    "xhs-cover": (1242, 1656),
    "xhs-content-1": (1242, 1656),
    "xhs-content-2": (1242, 1656),
    "xhs-content-3": (1242, 1656),
    "x-card": (1600, 900),
    "ig-square": (1080, 1080),
}

# 每个画幅的目标比例，写成分子分母而不是浮点数：浮点数会让"近似 3:4"
# 蒙混过关，而近似的代价是平台替我们裁边。
FRAME_ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "xhs-cover": (3, 4),
    "xhs-content-1": (3, 4),
    "xhs-content-2": (3, 4),
    "xhs-content-3": (3, 4),
    "x-card": (16, 9),
    "ig-square": (1, 1),
}


def platform_of_slug(slug: str) -> str | None:
    if slug.startswith("xhs-content-"):
        return "xiaohongshu"
    if slug.startswith("ig-square-"):
        return "instagram"
    for style in PLATFORM_STYLES.values():
        if slug in style.image_slugs:
            return style.key
    return None


def enabled_styles(enabled_keys: list[str]) -> list[PlatformStyle]:
    """按配置顺序返回启用的平台风格；未知 key 忽略而不报错。"""
    return [PLATFORM_STYLES[key] for key in enabled_keys if key in PLATFORM_STYLES]
