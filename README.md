# SkyTrace

摄影题材的拍法站。首页先看图文，点进去是一个题材页：成片、踩点、前期、后期、用光、姿势在同一页。咖啡馆、西餐厅、火车窗是「窗边人像」的例子，不是三个栏目。现行种子是编辑审过的 37 个题材（人像 18、风光 19）。

## 跑起来

不需要 Docker、PostgreSQL 或 Redis。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app.demo
```

浏览器打开 <http://127.0.0.1:8000>。数据库在 `var/skytrace.db`，示例图在 `var/media/seed/`。

再导入一次种子（不会重复插成片）：

```bash
python -m app.seed --subjects seeds/subjects.json --prune
```

测试：

```bash
pytest
```

测试用临时 SQLite，不写开发库。本机没有 Redis 时，worker 那一条会跳过。

可选 PostgreSQL：设置 `DATABASE_URL=postgresql+asyncpg://skytrace:skytrace@localhost:5432/skytrace`，然后 `alembic upgrade head` 和 `python -m app.seed --prune`。没有 Postgres 时不要跑 Alembic。

## 两分钟演示

详见 [DEMO.md](DEMO.md)。最短的一条：

1. 首页是两列图文，人像和风光混在一起。筛选是顶上一排药丸。
2. 点一张「窗边人像」成片，地址是 `/s/window-light-portrait?work=...`，这张图被标成「正在看这一张」。
3. 同一页能看到须知里的展示授权，以及标成「待核实」的店规。用光写的是窗光作主光。
4. 在踩点里展开地点例子：咖啡馆窗边、西餐厅靠窗座、火车/高铁车窗。
5. 回首页，点「山岳云海日出 · 黄山」。黄山是这个题材下的地点例子，不是单独一页。旧地址 `/s/huangshan` 会转到这里。
6. 记一笔：窗边人像 + 成片分享，一张图加一句，勾肖像授权，提交后看到待审。

## 演示帐号

没有注册。

| 角色 | 邮箱 | 密码 |
|---|---|---|
| 作者 | `author@skytrace.local` | `author-demo-pass` |
| 审核员 | `reviewer@skytrace.local` | `reviewer-demo-pass` |

卡片上的林夏、周屿、陈衡、编辑部是种子署名，不是这两个登录帐号。

## 已经能用

- 首页两列图文，筛选默认收起，向下滚动继续加载。点卡片进入题材页并高亮那一张。返回时尽量回到原来的滚动位置。
- 题材页六段固定顺序：成片、踩点、前期、后期、用光、姿势。编辑写的 2–4 条在前，已通过的笔记在后。一段都没有时写「还没有这类笔记」。
- 地点例子收在踩点里，默认折叠。
- 记一笔：选题材和类型，只出现该类型的字段。人像要勾肖像授权。可以选待归类。
- 审核台：待归类的稿子必须先改挂到真实题材才能通过。通过后同时出现在首页和题材成片里。
- 搜索先出题材，再出成片。人像 `/portrait`，风光 `/landscape`。
- 45 个公开题材，种子在 `seeds/subjects.json`。

## 模拟或没做

- 图都是程序画的示例图，每张构图不同，并标明「示例图」。不是实拍，也没有从网上抓图。
- 发布助手是关键词规则，只建议题材和类型，不写正文，没有接大模型。
- 搜索是 `LIKE` 子串，没有中文分词。「黄昏的西湖」这类话会按几条规则改写成关键词。
- 题材六段是编辑写进种子的静态句子，不是模型摘要。
- 不开放注册，没有微信登录，没有地图，没有关注和收藏。
- `/ideas` 还在，说明思想开源后置，但导航里没有入口。
- Redis / ARQ worker 可以空转，演示主路径不依赖它。

## 决定

- 沿用第 1–2 天的 FastAPI、Jinja、HTMX、SQLModel。不改成 Next.js。
- 本机没有 Postgres 时默认 SQLite，这样一条命令就能跑。Postgres 仍走 Alembic，`0002_topics` 加题材字段和 `subject_examples`。
- 题材就是原来的 `subjects`。`notes.subject_id` 仍然必填。待归类使用隐藏题材 `unsorted`，不进首页、频道和搜索。
- 公开导航只有首页、人像、风光、搜索、记一笔。没有「私房」，也没有人文频道。种子清单里原来的人文地点并进风光。
- 咖啡馆窗边、西餐厅靠窗、火车窗边是窗边人像的示例行，不是独立题材。
- 六段在人像和风光上都按同一顺序排开，方便对照。风光的「姿势」写成人物只作尺度，不编造摆拍教程。
- 中文别名按原文写入 JSON。SQLite 的 JSON 不转成 `\uXXXX`，否则 `LIKE` 搜不到「黄山云海」。
- 票价、季节窗口、具体时刻没有核实的，示例标成待核实，正文里不写死数字。
