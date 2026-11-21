"""公开频道和筛选词表。

题材清单在 seeds/subjects.json，不在这里。公开导航只有人像和风光。
公开词表不得出现「私房」或性化一级标签。
"""

from typing import TypedDict


class ChannelDef(TypedDict):
    code: str
    name: str
    summary: str


CHANNELS: tuple[ChannelDef, ...] = (
    {
        "code": "portrait",
        "name": "人像",
        "summary": "按题材学拍法。窗边、街头、夜景和棚内光线都是题材，不是某一家店。",
    },
    {
        "code": "landscape",
        "name": "风光",
        "summary": "一座山、一片湖或一段江岸是一个题材。机位写在同一页，不拆成地点树。",
    },
)

CHANNEL_CODES = {item["code"] for item in CHANNELS}
CHANNEL_BY_CODE = {item["code"]: item for item in CHANNELS}

FACETS: tuple[tuple[str, str], ...] = (
    ("environment", "环境"),
    ("style", "风格"),
    ("season", "季节"),
    ("time_of_day", "时段"),
    ("weather", "天气"),
    ("light", "光线"),
)

FACET_NAMES = dict(FACETS)

# (facet, slug, name)
TAGS: tuple[tuple[str, str, str], ...] = (
    ("environment", "indoor", "室内"),
    ("environment", "outdoor", "室外"),
    ("environment", "mixed", "混合"),
    ("style", "casual", "常服"),
    ("style", "cos", "Cos"),
    ("style", "street", "街拍"),
    ("style", "travel", "旅拍"),
    ("season", "spring", "春季"),
    ("season", "summer", "夏季"),
    ("season", "autumn", "秋季"),
    ("season", "winter", "冬季"),
    ("time_of_day", "dawn", "清晨"),
    ("time_of_day", "morning", "上午"),
    ("time_of_day", "midday", "午间"),
    ("time_of_day", "dusk", "黄昏"),
    ("time_of_day", "night", "夜晚"),
    ("weather", "sunny", "晴"),
    ("weather", "cloudy", "多云"),
    ("weather", "overcast", "阴"),
    ("weather", "rain", "雨"),
    ("weather", "snow", "雪"),
    ("weather", "fog", "雾"),
    ("light", "window-light", "窗光"),
    ("light", "available-light", "自然光"),
    ("light", "studio-light", "棚灯"),
    ("light", "night-light", "夜景灯光"),
    ("light", "mixed-light", "混合光"),
)


