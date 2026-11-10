"""频道、公开词表和两周原型的 10 个对象 stub。

公开词表不得出现「私房」或性化一级标签。人文频道这两周没有种子对象。
"""

from typing import TypedDict


class ChannelDef(TypedDict):
    code: str
    name: str
    summary: str


CHANNELS: tuple[ChannelDef, ...] = (
    {
        "code": "landscape",
        "name": "风光",
        "summary": "地点对象。季节、时段和天气决定能不能拍。",
    },
    {
        "code": "culture",
        "name": "人文",
        "summary": "人文频道这两周没有种子对象。",
    },
    {
        "code": "portrait",
        "name": "人像",
        "summary": "场景对象。光线、环境和风格是这页要先写清的条件。",
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


class SubjectStub(TypedDict):
    name: str
    slug: str
    type: str
    primary_channel: str
    condition_axes: list[str]


SUBJECT_STUBS: tuple[SubjectStub, ...] = (
    {
        "name": "黄山",
        "slug": "huangshan",
        "type": "location",
        "primary_channel": "landscape",
        "condition_axes": ["季节", "时段"],
    },
    {
        "name": "杭州西湖",
        "slug": "hangzhou-west-lake",
        "type": "location",
        "primary_channel": "landscape",
        "condition_axes": ["季节", "时段"],
    },
    {
        "name": "上海外滩",
        "slug": "shanghai-bund",
        "type": "location",
        "primary_channel": "landscape",
        "condition_axes": ["时段", "天气"],
    },
    {
        "name": "重庆洪崖洞",
        "slug": "chongqing-hongyadong",
        "type": "location",
        "primary_channel": "landscape",
        "condition_axes": ["时段", "夜景"],
    },
    {
        "name": "富士山",
        "slug": "mt-fuji",
        "type": "location",
        "primary_channel": "landscape",
        "condition_axes": ["季节", "天气"],
    },
    {
        "name": "茶卡盐湖",
        "slug": "chaka-salt-lake",
        "type": "location",
        "primary_channel": "landscape",
        "condition_axes": ["季节", "时段"],
    },
    {
        "name": "咖啡馆窗边",
        "slug": "cafe-window",
        "type": "scene",
        "primary_channel": "portrait",
        "condition_axes": ["光线", "环境"],
    },
    {
        "name": "城市夜景人像",
        "slug": "city-night-portrait",
        "type": "scene",
        "primary_channel": "portrait",
        "condition_axes": ["光线", "环境"],
    },
    {
        "name": "漫展 Cos",
        "slug": "expo-cos",
        "type": "scene",
        "primary_channel": "portrait",
        "condition_axes": ["光线", "风格"],
    },
    {
        "name": "窗光棚",
        "slug": "window-light-studio",
        "type": "scene",
        "primary_channel": "portrait",
        "condition_axes": ["布光", "光线"],
    },
)
