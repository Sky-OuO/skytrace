"""为每个题材写至少一条已通过的成片，并画一张不重复的示例图。

黄山和窗边人像各至少三张，方便首页混排。重复执行按标题更新，不另插一行。
"""

from datetime import datetime, timedelta, timezone

from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Media, Note, Subject, SubjectExample, User
from app.placeholders import render_placeholder
from app.services.storage import resolve_storage_path

BYLINES = (
    ("linxia@skytrace.local", "林夏"),
    ("zhouyu@skytrace.local", "周屿"),
    ("chenheng@skytrace.local", "陈衡"),
    ("desk@skytrace.local", "编辑部"),
)
BYLINE_PASSWORD = "byline-not-for-login"


async def _users(session: AsyncSession, helper: PasswordHelper) -> list[User]:
    users: list[User] = []
    for email, name in BYLINES:
        found = await session.execute(select(User).where(User.email == email))
        user = found.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                hashed_password=helper.hash(BYLINE_PASSWORD),
                display_name=name,
                role="author",
                is_active=True,
                is_verified=True,
                is_superuser=False,
            )
            session.add(user)
            await session.flush()
        else:
            user.display_name = name
        users.append(user)
    return users


def _hero_works() -> list[dict]:
    return [
        {
            "slug": "window-portrait",
            "title": "窗边人像 阴天侧窗 侧坐靠窗",
            "body": "阴天窗光作主光，身干与窗大约四十五度，近处暖灯关掉。",
            "example": "咖啡馆窗边",
            "front": 0,
        },
        {
            "slug": "huangshan",
            "title": "黄山 清晨云海 光明顶层次",
            "body": "云海铺开时按亮部曝光，山脊留住纹理，不要剪成死黑。",
            "example": "光明顶",
            "front": 1,
        },
        {
            "slug": "city-night-portrait",
            "title": "城市夜景人像 橱窗侧光 留一盏灯",
            "body": "主光用侧面橱窗，闪光灯先关掉，背后留得见城市光点。",
            "example": "橱窗侧光",
            "front": 2,
        },
        {
            "slug": "hangzhou-west-lake",
            "title": "杭州西湖 晨雾 断桥留白",
            "body": "雾还没散就拍断桥的轮廓，不要等太阳把湖面晒平。",
            "example": "断桥",
            "front": 3,
        },
        {
            "slug": "window-portrait",
            "title": "窗边人像 顺光窗 脸正对窗",
            "body": "人正对窗时反差低，白平衡仍以脸的受光面为准，不要跟着窗外跑。",
            "example": "西餐厅靠窗",
            "front": 4,
        },
        {
            "slug": "mt-fuji",
            "title": "富士山 本栖湖 倒影还在的时候",
            "body": "先看风。湖面还能留住山的倒影时再按快门，不要写死某一个钟点。",
            "example": "本栖湖",
            "front": 5,
        },
        {
            "slug": "window-portrait",
            "title": "窗边人像 火车窗 侧光靠近玻璃",
            "body": "脸靠近车窗一侧，玻璃反光时不要开闪光灯。不写车次。",
            "example": "火车窗边",
            "front": 6,
        },
        {
            "slug": "huangshan",
            "title": "黄山 始信峰 受光的松",
            "body": "长焦只切一棵受光的松和后面的山脊，广角那张留在同一题材里对照。",
            "example": "始信峰",
            "front": 7,
        },
        {
            "slug": "street-natural-light",
            "title": "街头自然光 阴影边缘 脸在亮区旁边",
            "body": "把脸放在建筑阴影靠近亮区的一侧，正午顶光就换到檐下。",
            "example": "建筑阴影边缘",
            "front": 8,
        },
        {
            "slug": "huangshan",
            "title": "黄山 排云亭 云海逆光",
            "body": "逆光云海按亮边曝光，山体留一条能辨认的轮廓，高光不要切死。",
            "example": "排云亭",
            "front": 9,
        },
    ]


def _method_notes() -> list[dict]:
    return [
        {
            "slug": "window-portrait",
            "type": "lighting",
            "title": "窗边人像 阴天侧窗：关暖灯、用窗作主光",
            "body": "这一条只写光，不写某一家店。",
            "fields": {
                "key_light": "侧向阴天窗光作唯一主光，人靠近窗坐，不用闪光灯。",
                "fill_light": "暗侧用浅色桌面或菜单做弱反射，不必另架灯。",
                "rim_light": "本方案不用轮廓灯。",
                "ambient_light": "关掉或避开座位附近的暖色筒灯，减少脸上的蓝橙混色。",
                "common_failures": "未关近处暖灯，脸颈出现蓝橙混色；人离窗太远，主光衰减后面部变平。",
            },
        },
        {
            "slug": "window-portrait",
            "type": "posing",
            "title": "窗边人像 阴天侧窗：侧坐靠窗",
            "body": "身干与窗大约四十五度。",
            "fields": {
                "body_orientation": "身干与窗面大约四十五度，侧坐，不要双肩正对相机。",
                "contact_points": "重心在椅面。近窗一侧的前臂轻靠窗台或桌沿，不要整个人贴死玻璃。",
                "light_relationship": "让眼神里留着窗光。鼻影落在鼻翼和嘴角之间，不要盖住嘴。",
                "common_failures": "双肩摆正以后脸变成证件照；整个人贴上玻璃，肩膀变形。",
            },
        },
        {
            "slug": "window-portrait",
            "type": "post",
            "title": "窗边人像 阴天侧窗：白平衡看脸",
            "body": "先处理混色，再谈风格。不写滤镜名字。",
            "fields": {
                "white_balance_exposure": "白平衡以脸部受光面为准，先去掉窗光偏冷和室内灯偏暖的混色。皮肤高光不切掉。",
                "crop_advice": "留头顶和近窗一侧的呼吸边。窗框如果入画，竖线保持垂直。",
                "material_color": "皮肤保留纹理。木头和杯子保持中性，不要整张推向同一个色偏。",
                "common_failures": "为了拉回窗外把脸拉灰；混色没处理，脸颈出现蓝橙渐变。",
            },
        },
        {
            "slug": "huangshan",
            "type": "spot",
            "title": "黄山 光明顶 云海机位",
            "body": "光明顶、始信峰、排云亭是同一题材下的机位。",
            "fields": {
                "arrival": "从索道或步道到光明顶，具体班次以当日管委会公告为准。",
                "time_window": "云海多在雨后转晴的清晨。没有云就改拍山脊，不要空等一个未核实的钟点。",
                "focal_length": "全景和长焦各留一张。具体焦段按你手里的镜头写，不写死一支。",
                "exposure": "按云的亮部曝光，山体保留纹理。",
                "common_failures": "只拍到一片白雾，没有山的结构；把临时封路写成永远开放。",
            },
        },
        {
            "slug": "huangshan",
            "type": "pre",
            "title": "黄山 行前：预约和风",
            "body": "票价和封路不写死。",
            "fields": {
                "tickets_permits": "须在黄山旅游官方平台实名、分时预约。票价以当日公告为准，笔记里标待核实，不填一个过期数字。",
                "transport_arrival": "索道和换乘随季节调整。出发前看管委会公告，不抄旧攻略的班次。",
                "season_window": "云海和雾凇都看天气，不把某一年的日期写成每年如此。",
                "gear_advice": "防风层和贴身电池比滤镜重要。三脚架在大风里挂包增重。",
                "safety_tips": "山路湿滑不退着走。未开放岔路不写坐标。",
                "common_failures": "没预约就上山；按旧攻略的索道时间做计划。",
            },
        },
        {
            "slug": "huangshan",
            "type": "post",
            "title": "黄山 后期：保住云和山的交界",
            "body": "层次比色彩优先。",
            "fields": {
                "white_balance_exposure": "白平衡以受光岩壁为准，不要把云海统一拉成死白。",
                "crop_advice": "裁掉没有信息的灰天，留下山和云的交界。",
                "material_color": "松针和岩石分开处理，不要全局加清晰度。",
                "common_failures": "云海过曝成白纸；远山被清晰度磨出白边。",
            },
        },
    ]


async def _upsert_note(
    session: AsyncSession,
    *,
    subject: Subject,
    author: User,
    type_: str,
    title: str,
    body: str,
    fields: dict,
    published_at: datetime,
    example_id,
) -> Note:
    found = await session.execute(
        select(Note).where(Note.subject_id == subject.id, Note.type == type_, Note.title == title)
    )
    note = found.scalar_one_or_none()
    portrait = subject.primary_channel == "portrait" or type_ == "posing"
    if note is None:
        note = Note(
            author_id=author.id,
            subject_id=subject.id,
            example_id=example_id,
            type=type_,
            title=title,
            body=body,
            fields=fields,
            status="approved",
            portrait_auth_accepted=portrait,
            submitted_at=published_at,
            published_at=published_at,
        )
        session.add(note)
        await session.flush()
        return note
    note.body = body
    note.fields = fields
    note.status = "approved"
    note.example_id = example_id
    note.portrait_auth_accepted = portrait or note.portrait_auth_accepted
    note.published_at = published_at
    note.submitted_at = note.submitted_at or published_at
    return note


async def _upsert_photo(
    session: AsyncSession,
    *,
    note: Note,
    subject: Subject,
    author: User,
    index: int,
    caption: str,
) -> Media:
    key = f"seed/{subject.slug}/{index}.png"
    data, width, height = render_placeholder(subject.slug, index, subject.primary_channel, caption)
    path = resolve_storage_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    found = await session.execute(select(Media).where(Media.storage_key == key))
    media = found.scalar_one_or_none()
    if media is None:
        media = Media(
            storage_key=key,
            mime="image/png",
            byte_size=len(data),
            width=width,
            height=height,
            role="photo",
            alt=f"{caption}，示例图",
            note_id=note.id,
            subject_id=subject.id,
            created_by=author.id,
        )
        session.add(media)
        await session.flush()
    else:
        media.byte_size = len(data)
        media.width = width
        media.height = height
        media.alt = f"{caption}，示例图"
        media.note_id = note.id
        media.subject_id = subject.id
        media.mime = "image/png"
    if index == 0 or subject.cover_media_id is None:
        subject.cover_media_id = media.id
    return media


async def seed_works(session: AsyncSession, helper: PasswordHelper) -> int:
    users = await _users(session, helper)
    result = await session.execute(select(Subject).where(Subject.slug != "unsorted").order_by(Subject.slug))
    subjects = list(result.scalars())
    by_slug = {subject.slug: subject for subject in subjects}
    heroes = _hero_works()
    hero_slugs = {item["slug"] for item in heroes}
    plans = list(heroes)
    for subject in subjects:
        if subject.slug in hero_slugs:
            continue
        lines = list((subject.guide or {}).get("finished_points") or [])
        tip = lines[0] if lines else f"先把{subject.name}的主体拍清楚，再补机位。"
        example_name = None
        plans.append(
            {
                "slug": subject.slug,
                "title": f"{subject.name}：{tip}"[:120],
                "body": tip,
                "example": example_name,
                "front": None,
            }
        )
    ordered = sorted(plans, key=lambda item: (item["front"] is None, item["front"] if item["front"] is not None else 0, item["slug"], item["title"]))
    base = datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc)
    written = 0
    per_slug_index: dict[str, int] = {}
    for offset, plan in enumerate(ordered):
        subject = by_slug.get(plan["slug"])
        if subject is None:
            continue
        example_id = None
        if plan.get("example"):
            found = await session.execute(
                select(SubjectExample).where(
                    SubjectExample.subject_id == subject.id,
                    SubjectExample.name == plan["example"],
                )
            )
            example = found.scalar_one_or_none()
            if example is not None:
                example_id = example.id
        index = per_slug_index.get(subject.slug, 0)
        per_slug_index[subject.slug] = index + 1
        author = users[offset % len(users)]
        published_at = base - timedelta(minutes=offset)
        note = await _upsert_note(
            session,
            subject=subject,
            author=author,
            type_="finished",
            title=plan["title"],
            body=plan["body"],
            fields={"related_note_ids": []},
            published_at=published_at,
            example_id=example_id,
        )
        await _upsert_photo(
            session,
            note=note,
            subject=subject,
            author=author,
            index=index,
            caption=subject.name,
        )
        written += 1
    for offset, plan in enumerate(_method_notes()):
        subject = by_slug.get(plan["slug"])
        if subject is None:
            continue
        await _upsert_note(
            session,
            subject=subject,
            author=users[-1],
            type_=plan["type"],
            title=plan["title"],
            body=plan["body"],
            fields=plan["fields"],
            published_at=base - timedelta(days=1, minutes=offset),
            example_id=None,
        )
    return written
