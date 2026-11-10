# SkyTrace 数据模型

本文和 `alembic/versions/0001_initial.py` 对齐，描述第 1–2 天已经落库的表、状态机、索引和 `notes.fields`。后面几天可以加列，但不要另起一套精简字段。

## 约定

- 主键都是 UUID。应用负责生成，数据库不依赖额外扩展。
- 时间列是 `timestamptz`。
- 草稿就是 `notes.status = draft`，没有单独的 drafts 表。
- 每种笔记的专属内容进 `notes.fields`（jsonb）。成片的简短拍摄说明写在 `notes.body`，图片进 `media`。
- 公开列表和搜索只应看到 `approved`。未过审笔记对匿名读接口返回 404。
- 对外角色只有 `author` 和 `reviewer`。审核员可以给自己写笔记，但不能改别人的稿。作者不能进审核台。
- FastAPI-Users 额外使用 `is_active`、`is_superuser`、`is_verified`。密码在库里的列名是 `password_hash`；ORM 属性仍叫 `hashed_password`，这是库的字段名。
- `access_tokens` 不是业务表。会话 Cookie 里只放不透明 token，登录态记在这张表。
- 公开词表不含「私房」，也不设性化一级标签。`theme` 类型保留，是为了和方案对齐；两周的 10 个种子用不到。

## 笔记状态机

```text
draft --提交--> pending_review --通过--> approved
                      |
                      +--驳回--> rejected
rejected --改稿--> draft
rejected --再提交--> pending_review
```

`approved` 不再迁出。非法迁移返回 409 `CONFLICT`。

审核工单 `review_tickets.status` 用 `pending`、`approved`、`rejected`。`pending` 对应笔记的 `pending_review`。一篇笔记可以有多条工单，驳回后再提交就新开一张。`notes.status` 应与最新一张工单保持一致；这个同步留到后续审核台实现，第 1–2 天只把表和允许的迁移写下来。

人像频道的笔记，以及 `posing`（动作思路），提交前必须 `portrait_auth_accepted = true`。保存草稿还不检查；提交路由会先做这项检查，但真正写入 `pending_review` 要到后面几天。

## users

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| email | varchar(320) | 唯一，`uq_users_email` |
| password_hash | varchar(1024) | 口令哈希 |
| is_active | boolean | 默认 true |
| is_superuser | boolean | 默认 false，业务权限不看这个字段 |
| is_verified | boolean | 默认 false；演示帐号种子会写成 true |
| display_name | varchar(100) | |
| role | varchar(32) | `author` 或 `reviewer`，`ck_users_role` |
| created_at | timestamptz | |

没有注册接口。演示帐号由 `python -m app.seed` 写入。

## access_tokens

| 列 | 类型 | 说明 |
|---|---|---|
| token | varchar(64) | 主键 |
| user_id | uuid | 外键 `users.id`，删除用户时级联删除 |
| created_at | timestamptz | 用来判断会话是否过期 |

索引：`ix_access_tokens_user_id`、`ix_access_tokens_created_at`。

## subjects

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| slug | varchar(160) | 唯一，`uq_subjects_slug` |
| name | varchar(200) | |
| type | varchar(32) | `location`、`scene`、`theme` |
| primary_channel | varchar(32) | `landscape`、`culture`、`portrait` |
| condition_axes | jsonb | 本页要突出的条件面，字符串数组，默认 `[]` |
| geo_text | text | 可空 |
| safety_notes | text | 可空 |
| cover_media_id | uuid | 可空，外键 `media.id`，媒体删除时置空 |
| guide_summary | text | 可空。第 3–5 天再填静态摘要 |
| created_by | uuid | 可空，外键 `users.id`，用户删除时置空 |
| created_at | timestamptz | |
| search_vector | tsvector | 触发器维护，不由应用写入 |

索引：`ix_subjects_primary_channel_type (primary_channel, type)`，`ix_subjects_search_vector` 为 GIN。

## notes

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| author_id | uuid | 外键 `users.id`，限制删除 |
| subject_id | uuid | 外键 `subjects.id`，限制删除。一篇笔记至少一个对象 |
| type | varchar(32) | 见下方类型 |
| title | varchar(300) | |
| body | text | 默认空字符串。成片的简短拍摄说明放这里 |
| fields | jsonb | 默认 `{}`。键见下一节 |
| status | varchar(32) | `draft`、`pending_review`、`approved`、`rejected`，默认 `draft` |
| portrait_auth_accepted | boolean | 默认 false |
| submitted_at | timestamptz | 可空 |
| published_at | timestamptz | 可空。公开索引只覆盖已过审 |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| search_vector | tsvector | 触发器维护 |

类型：`finished` 成片分享，`spot` 机位示意，`pre` 前期技巧，`post` 后期思路，`lighting` 灯光思路，`posing` 动作思路。

索引：

- `ix_notes_subject_id_type_status (subject_id, type, status)`
- `ix_notes_approved (subject_id, type, published_at) WHERE status = 'approved'`
- `ix_notes_search_vector` GIN

## notes.fields

键名固定，不要另起缩写。除了 `related_note_ids` 和可选的 `exif`，其余都是可空文本。`common_failures` 对编辑种子以后必填，对 UGC 可选；第 1–2 天只预留键。

| type | 键 |
|---|---|
| finished | `related_note_ids`（回链机位或灯光笔记的 uuid 数组） |
| spot | `arrival`，`time_window`，`focal_length`，`exposure`，`common_failures`，可选 `exif` 对象 |
| pre | `tickets_permits`，`transport_arrival`，`season_window`，`gear_advice`，`safety_tips`，`common_failures` |
| post | `white_balance_exposure`，`crop_advice`，`material_color`，`common_failures` |
| lighting | `key_light`，`fill_light`，`rim_light`，`ambient_light`，`common_failures` |
| posing | `body_orientation`，`contact_points`，`light_relationship`，`common_failures` |

图片不进 jsonb。机位、布光、动作的示意用 `media.role = annotation`；成片和普通照片用 `photo`；对象封面用 `cover`。

对应的 Pydantic 模型在 `app/domain.py`。未知键会被拒绝，避免以后悄悄改字段名。

## media

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| storage_key | varchar(500) | 相对 `MEDIA_ROOT` 的路径，唯一 |
| mime | varchar(100) | |
| byte_size | integer | |
| width | integer | 可空 |
| height | integer | 可空 |
| role | varchar(32) | `cover`、`annotation`、`photo`，默认 `photo` |
| alt | text | 可空 |
| note_id | uuid | 可空，外键 `notes.id`，笔记删除时置空 |
| subject_id | uuid | 可空，外键 `subjects.id`，对象删除时置空 |
| created_by | uuid | 可空，外键 `users.id`，用户删除时置空 |
| created_at | timestamptz | |

第 1–2 天的上传可以先不挂笔记或对象。单文件上限默认 10MB，超过返回 413。

## review_tickets

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| note_id | uuid | 外键 `notes.id`，笔记删除时级联删除工单 |
| status | varchar(32) | `pending`、`approved`、`rejected` |
| submitter_id | uuid | 外键 `users.id`，限制删除 |
| reviewer_id | uuid | 可空，外键 `users.id`，用户删除时置空 |
| reason | text | 可空。驳回理由 |
| submitted_at | timestamptz | |
| decided_at | timestamptz | 可空 |

索引：`ix_review_tickets_status_submitted_at (status, submitted_at)`。

## tags

| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid | 主键 |
| slug | varchar(80) | 唯一，`uq_tags_slug` |
| name | varchar(80) | 中文显示名 |
| facet | varchar(32) | `environment`、`style`、`season`、`time_of_day`、`weather`、`light` |

索引：`ix_tags_facet (facet)`。

词表：

- 环境：`indoor` 室内，`outdoor` 室外，`mixed` 混合
- 风格：`casual` 常服，`cos` Cos，`street` 街拍，`travel` 旅拍
- 季节：`spring` 春季，`summer` 夏季，`autumn` 秋季，`winter` 冬季
- 时段：`dawn` 清晨，`morning` 上午，`midday` 午间，`dusk` 黄昏，`night` 夜晚
- 天气：`sunny` 晴，`cloudy` 多云，`overcast` 阴，`rain` 雨，`snow` 雪，`fog` 雾
- 光线：`window-light` 窗光，`available-light` 自然光，`studio-light` 棚灯，`night-light` 夜景灯光，`mixed-light` 混合光

## subject_tags 与 note_tags

联合主键就是唯一约束。

| 表 | 列 | 删除行为 |
|---|---|---|
| subject_tags | subject_id，tag_id | 两边都级联删除 |
| note_tags | note_id，tag_id | 两边都级联删除 |

第 1–2 天的种子只导入标签和对象，不预连 `subject_tags`。

## 搜索向量

`simple` 文本搜索配置，不安装中文分词扩展。因此索引先按整词保存，查询逻辑留到后面。

- 对象：`name` 权重 A，加上关联标签名权重 A。
- 笔记：`title` 权重 A，`body` 权重 B，加上关联标签名权重 A。

触发器：

- `trg_subjects_search_vector`、`trg_notes_search_vector`：插入或更新行时重算。
- `trg_subject_tags_search`、`trg_note_tags_search`：关联变化时回头更新对象或笔记。
- `trg_tags_search`：标签显示名变化时，刷新挂过这个标签的对象和笔记。

函数名以 `skytrace_` 开头，降级迁移时会删掉。

## 种子对象

人文频道没有种子。名称必须是「咖啡馆窗边」和「窗光棚」。

| 名称 | slug | type | primary_channel | condition_axes |
|---|---|---|---|---|
| 黄山 | huangshan | location | landscape | 季节、时段 |
| 杭州西湖 | hangzhou-west-lake | location | landscape | 季节、时段 |
| 上海外滩 | shanghai-bund | location | landscape | 时段、天气 |
| 重庆洪崖洞 | chongqing-hongyadong | location | landscape | 时段、夜景 |
| 富士山 | mt-fuji | location | landscape | 季节、天气 |
| 茶卡盐湖 | chaka-salt-lake | location | landscape | 季节、时段 |
| 咖啡馆窗边 | cafe-window | scene | portrait | 光线、环境 |
| 城市夜景人像 | city-night-portrait | scene | portrait | 光线、环境 |
| 漫展 Cos | expo-cos | scene | portrait | 光线、风格 |
| 窗光棚 | window-light-studio | scene | portrait | 布光、光线 |
