# SkyTrace

摄影对象知识库的本地原型。主线是对象页和结构化笔记，不是照片流。

这个仓库目前只做第 1–2 天的骨架：能从空库启动、用预置帐号登录、把图片存到本地磁盘，并让 ARQ worker 空转。频道浏览、发布表单、审核台、搜索查询和发布助手都还是占位。

## 技术栈

- FastAPI、Pydantic、Uvicorn。同一个进程提供页面和 `/api/v1`。
- Jinja2 模板，HTMX 已放进基础布局。第 1–2 天只用它刷新首页上的对象库存。
- Tailwind CSS 使用官方 Play CDN（`https://cdn.tailwindcss.com`）。不单独构建样式。页面在加载不到 CDN 时仍然能读，只是没有这套排版。
- PostgreSQL 16、SQLModel、Alembic。
- 登录是会话 Cookie，会话行在 `access_tokens`。用的是 FastAPI-Users 的数据库策略，不是 JWT。没有注册，也不接 OAuth / 微信。Authlib 已列入依赖，留给以后。
- Redis 和 ARQ。不要同时加 Celery。
- 媒体默认写到 `var/media`。`storage_key` 是相对这段目录的路径。

依赖写在 `pyproject.toml`。安装方式是 `pip install -e ".[dev]"`，没有另附锁文件。

## 从空库跑起来

需要 Docker，用来起 PostgreSQL 16 和 Redis。应用本身在本机用 Uvicorn 跑。

```bash
cp .env.example .env
docker compose up -d
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另开一个终端启动 worker。它会连上 Redis 后空转，队列里没有任务：

```bash
source .venv/bin/activate
arq app.worker.WorkerSettings
```

浏览器打开 <http://127.0.0.1:8000>。

`alembic upgrade head` 可以重复执行。`python -m app.seed` 也可以重复执行：标签和 10 个对象按 slug 更新，演示帐号的密码会改成当前 `.env` 里的值。

媒体目录由 `MEDIA_ROOT` 决定，预览地址由 `MEDIA_PREVIEW_BASE_URL` 决定。单张图片默认不超过 10MB。本地 http 请保持 `SESSION_COOKIE_SECURE=false`。

ARQ 0.28 不允许一个函数都不注册，所以 worker 挂了占位函数 `reserved_idle`。Web 进程没有入队代码。第 9 天之前不要往这个队列投任务。

## 演示帐号

没有注册入口。邮箱和密码写在 `.env.example`，复制到 `.env` 后由种子脚本创建。下面是这份示例里的默认值，只给本地演示用，不要拿去部署。

| 角色 | 邮箱 | 密码变量 | 示例密码 |
|---|---|---|---|
| 作者 | `author@skytrace.local` | `DEMO_AUTHOR_PASSWORD` | `author-demo-pass` |
| 审核员（可兼作者） | `reviewer@skytrace.local` | `DEMO_REVIEWER_PASSWORD` | `reviewer-demo-pass` |

显示名默认是「演示作者」和「演示审核员」。

## 第 1–2 天怎么验收

自动化：

```bash
source .venv/bin/activate
pytest
```

测试会另建 `skytrace_test`，重复跑迁移和种子，不写你的开发库。本机需要已经能用 `.env.example` 里的帐号连上 PostgreSQL 和 Redis（`docker compose up -d` 之后即可）。

手工：

1. 首页能看到风光、人文、人像、搜索、思想开源（标着「后置」）和登录。公开页面里没有「私房」。
2. 思想开源打开 `/ideas`，只说明本期后置、无功能，并能回到摄影频道。人文频道写明这两周没有种子对象。
3. 用作者帐号登录后再登出。未登录打开 `/publish` 会去登录页。作者打开 `/review` 得到 403，审核员可以进入占位审核台。
4. `GET /api/v1/auth/me`、`/api/v1/vocab`、`/api/v1/channels`、`/api/v1/subjects` 可用。对象列表里有 10 条 stub，人文频道数量是 0。
5. 登录后 `POST /api/v1/media` 上传一张图片，用返回的 `preview_url` 能读回同一份字节。未登录上传会 401。
6. `DATA_MODEL.md` 与迁移一致。worker 能启动并因为队列为空而空转。

交互式接口说明在 <http://127.0.0.1:8000/docs>。未实现的写接口挂在 `/api/v1` 上，返回约定错误码，而不是 501。

## 这几天故意没做

- 完整的频道、对象、笔记浏览器，以及发布表单。
- 审核台的通过和驳回。
- 搜索的实际查询，以及自然语言解析。全文索引已经建好。
- 发布助手和任何大模型调用。
- OAuth、微信登录、域名和对象存储服务。图片只进本地磁盘。
