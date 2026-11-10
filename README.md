# Campus Corners 网站

[campus-corners.com](https://campus-corners.com) 的项目代码。前端使用原生 HTML、CSS 和 JavaScript；静态页面不需要单独的构建步骤。本地预览账户、登录和管理后台时，需要运行 Django 服务。

| 页面 | 文件 | 说明 |
| --- | --- | --- |
| 首页 | `index.html` | 标志、Sparko 吉祥物和进入地图的按钮 |
| 探索 | `app.html` | 全屏 Campus Corners 应用 |
| 关于 | `about.html` | Campus Corners 和 Sparko 的介绍 |
| 贴纸 | `stickers.html` | 产品图片展示，不提供购买功能 |

网站视觉设计（夕阳天空、玻璃质感面板、Outfit 和 DM Sans 字体）来自 Figma Make 文件 “Four-Page Campus Website”。共用样式位于 `css/site.css`。

## 应该在哪里编辑应用

自 2026 年 10 月 25 日起，应用文件（`app.html`、`app/app.js`、`app/app.css`）在**本仓库**中维护。当前版本已超出 Campus-Corners 仓库里的旧原型，包含 Shuffle、社团、评论、橙色 Explore 和 Sparko 路线指引，因此 `tools/build_app.py` 已不适用于这里；运行时会显示提示并停止。

Campus-Corners 仓库仍保存网站使用的数据和处理工具：

- 活动：`data/events/`（每周根据 UCLA 日历生成，并使用 `data/scripts/fetch_instagram_week.py`）
- 社团：`data/clubs/ucla-clubs.json`；洗手间和自习地点：`data/explore/spots.json`
- 地图：`tools/recolor_line.py`（粉色和橙色路线图）、`tools/footprints.py`（建筑轮廓）、`tools/walkgrid.py`（路线指引使用的可步行网格）

访客的收藏、关注、评论和新增地点会保留在当前浏览器中。登录后保存的活动和 Sparko 导览进度会通过本地 Django API 同步到账户。

## 账户功能范围

账户支持电子邮件和密码登录，以及个人资料编辑。注册密码长度为 8–128 个字符，并以 Argon2 哈希形式保存。SQL 个人资料保存昵称和 `profile_icon` 键；新账户默认使用网站吉祥物 `sparko`。头像选择器还提供星星、花朵和爱心。数据库只保存这些短键，不存储图片；网站会根据键显示项目内的图片。只有当服务器确认账户的 UCLA 邮箱已验证时，个人资料头像才会显示 UCLA 边框。本次范围不包括发送验证邮件、UCLA 单点登录、修改邮箱或密码、上传头像；注册不会发送邮件。

首页的 **Explore the map** 会直接打开地图。访客会看到悬浮在地图上的登录窗口，也可以继续以访客身份使用；已登录用户会直接进入地图。底部四项导航栏保留 Settings，另有一个独立悬浮的 Account 按钮，用于打开专属账户页面。访客头像使用暖色调的人像剪影。

### 数据库保存的内容

- `accounts_user`：UUID 主键、规范化且唯一的邮箱、昵称、`profile_icon` 键、Argon2 密码哈希、账户时间戳和可选的邮箱验证时间。
- `accounts_userpreferences`：邮件偏好及其时间戳。
- `accounts_useronboarding`：导览状态、当前步骤和 JSON 格式的跳过步骤列表。
- `accounts_savedevent`：每个已保存活动一条记录，含活动键和保存时间。
- `django_session`：服务端会话内容；浏览器 Cookie 只包含不透明的会话标识符。

登录用户的个人资料也会以 JSON 格式通过 `/api/auth/me` 返回。个人资料更新使用 `/api/me/profile`，接口只接受 `nickname` 和允许列表中的 `profile_icon` 键。`/admin/` 员工页面读取同一个数据库；账户列表会遮蔽邮箱，并排除密码哈希和会话内容。

## 员工数据中心

Django 后端在 `/admin/` 提供初步的只读 HTML 数据中心，并由 Django 员工账户登录保护。账户列表会遮蔽邮箱；经授权的账户详情页可显示完整邮箱。员工可以查看账户资料、已保存活动记录、偏好和当前导览进度。密码哈希、活动会话、临时登录限流记录、编辑和删除功能均不开放。

应用数据库迁移后，在运行 Django 的电脑上交互式创建管理员：

~~~sh
server/var/venv/bin/python server/manage.py createsuperuser
~~~

命令会提示输入管理员邮箱、昵称和密码。请勿将该凭据放进仓库。启动本地服务后，打开 `http://localhost:8000/admin/`。默认本地记录保存在 SQLite 文件 `server/var/dev.sqlite3`；`DJANGO_SQLITE_NAME` 可指定其他文件，设置 `DATABASE_URL` 则会选择 PostgreSQL。托管环境中的管理后台需要 Django 服务和共用的持久数据库；单靠静态网站无法安全提供私人账户记录。应用不会自动创建管理员凭据。

### 使用 Django 和持久化 PostgreSQL 托管

仓库根目录的 `render.yaml` 配置了免费的 Render Django Web 服务。搭配 Neon Free PostgreSQL 使用：Blueprint 需要通过私密的 `DATABASE_URL` 接收数据库连接字符串，但不会替你创建 Neon 数据库。数据库独立于应用进程，因此 Render 重启或重新部署不会删除账户记录。Neon Free 当前每个项目提供 1 GB 数据库存储和每月 100 CU-hours；空闲时计算资源会缩到零。账户数量本身不计费，数据库活动量和计划额度才会影响使用情况。需要长期保留的用户数据请另行导出备份。

这是供演示使用的零费用方案，不代表生产环境的可靠性保证。Render 免费 Web 服务在连续 15 分钟没有流量后会休眠；休眠后的首次请求可能需要约一分钟才能响应。它的本地文件系统是临时的，因此部署、重启或休眠会丢失其中的 SQLite 数据和上传文件；账户数据应保存在 Neon。Render 免费服务也不提供 Shell 终端。[Neon Free 计划说明](https://neon.com/blog/neon-free-plan-1-gb-per-project) · [Render 免费服务限制](https://render.com/docs/free)。

准备托管后端：

1. 创建 Neon Free 项目并复制 PostgreSQL 连接字符串。该字符串是数据库凭据，请妥善保密。
2. 分支经过审查并发布后，在 Render 中选择 **New → Blueprint**，连接 CampusCorners_Web 仓库和对应分支。按提示将 Neon 连接字符串填入 `DATABASE_URL`。Blueprint 会生成 `DJANGO_SECRET_KEY`，在构建期间运行数据库迁移和静态文件收集，然后启动 Gunicorn。自动部署已关闭。
3. Render 免费服务没有 Shell，因此首次成功部署后，需要从自己的电脑连接托管数据库创建员工账户。在本地环境中私密设置 `DATABASE_URL` 为 Neon 连接字符串，然后从仓库根目录运行 `server/var/venv/bin/python server/manage.py createsuperuser`。按提示输入管理员邮箱、昵称和密码。此操作会将管理员写入托管 PostgreSQL，不会把密码写入源代码，也不会给新注册用户管理员权限。
4. 打开 Render 服务的 HTTPS 地址并进入 `/admin/`。Django 会在同一域名下提供网页、API 和管理后台。将 `campus-corners.com` 接入该服务需要单独调整域名/DNS，不属于此 Blueprint 的范围。

应用在 Blueprint 部署前仍只在本地运行。数据库迁移会创建数据表，但不会把本地 SQLite 中的账户复制到 Neon。本地数据库仍保留在这台电脑上。Neon Free 当前每个项目的额度为 100 CU-hours 和 1 GB；如果项目超出额度，请先查看供应商的最新价格和备份方案，再决定是否升级。

## 公开上线前的待办事项

- 在 `about.html` 中填写团队联系邮箱（搜索 `TODO`）。
- 确认 UCLA 校园地图可以公开使用。
- 地图中的活动只覆盖应用仓库 `data/events/` 中列出的日期；更新该目录后再运行上文中的处理脚本。

## PM 本地预览：在 localhost 运行当前分支

按以下步骤运行 Django 网站和 API，让 PM 可以在同一个本地预览中检查注册、登录和员工数据中心。托管配置位于 `feat/django-persistent-db-hosting`；运行前请确认当前检出的是这个分支。如果手头还没有该分支，需要先通过已批准的审查流程获取代码。

确认当前分支：

~~~sh
git branch --show-current
~~~

输出应为 `feat/django-persistent-db-hosting`。

本地预览不需要 Neon 或 Render。它使用独立的 SQLite 文件 `server/var/dev.sqlite3`；本地创建的账户会留在运行预览的这台电脑上，不会复制到托管数据库。

### 首次设置

在仓库根目录（`CampusCorners_Web`）运行以下命令。需要 Python 3.12。虚拟环境和服务端依赖只需安装一次：

~~~sh
python3.12 -m venv server/var/venv
server/var/venv/bin/python -m pip install -r server/requirements.txt
~~~

仅当 `server/.env` 尚不存在时，从示例文件创建它：

~~~sh
test -f server/.env || cp server/.env.example server/.env
~~~

打开 `server/.env`，将 `DJANGO_SECRET_KEY` 替换为私密的随机值。可以在终端运行 `python3.12 -c "import secrets; print(secrets.token_urlsafe(48))"` 生成，然后粘贴到文件中的 `DJANGO_SECRET_KEY=` 后面。请勿分享这个值。通过本地 HTTP 预览时，保留 `DJANGO_DEBUG=true` 和 `DJANGO_SECURE_COOKIES=0`。保持 `DATABASE_URL` 注释状态，以使用本地 SQLite；不要把托管数据库连接字符串写进共享文件。

### 启动预览

先将数据库迁移应用到本地 SQLite，再启动 Django：

~~~sh
server/var/venv/bin/python server/manage.py migrate
server/var/venv/bin/python server/manage.py runserver
~~~

请在运行服务的同一台电脑上打开以下地址：

- 首页：<http://localhost:8000/>
- 探索地图和访客登录窗口：<http://localhost:8000/app.html?entry=explore#map>
- 员工数据中心：<http://localhost:8000/admin/>

若要在 `/admin/` 查看注册账户，请在另一个终端中创建本地员工登录。确保数据库迁移已完成：

~~~sh
server/var/venv/bin/python server/manage.py createsuperuser
~~~

按交互提示输入本地管理员邮箱、昵称和密码，然后登录 `/admin/`。PM 也可以在应用中注册一个测试账户，再确认该账户出现在本地数据中心。按 `Ctrl+C` 可停止 Django 服务。如果 8000 端口已被占用，运行 `server/var/venv/bin/python server/manage.py runserver 8001`，并改用 `http://localhost:8001/`。

本地数据库会被 Git 忽略。请勿在评审数据库中使用真实用户资料。托管环境与本地预览分开：Render Blueprint 使用私密的 Neon `DATABASE_URL`，部署时执行迁移和静态文件收集，并通过 Render HTTPS 地址提供同一应用。Neon Free 和 Render Free 的说明见上文“使用 Django 和持久化 PostgreSQL 托管”。

正式部署时，请使用上方的 Render Blueprint，或配置等效的 Django WSGI 主机，并设置持久化 PostgreSQL `DATABASE_URL`、私密的 `DJANGO_SECRET_KEY`、关闭 `DEBUG`、HTTPS/安全 Cookie、允许的主机名和 CSRF 可信源。部署时应用数据库迁移并收集静态文件。允许提供静态文件的目录仅包括 `app/`、`css/`、`img/` 和 `js/`。

运行 Django 和浏览器检查时，先安装 `server/requirements-dev.txt`，再运行 `server/var/venv/bin/python -m playwright install chromium`。随后运行 `server/var/venv/bin/python server/manage.py test accounts` 和 `server/var/venv/bin/python server/accounts/browser_tests.py`。浏览器检查会使用临时数据库和临时预览服务。

地图中较早日期的活动仅用于样例展示，并非当前活动列表。
