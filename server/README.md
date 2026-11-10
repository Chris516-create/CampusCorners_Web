# 本地 Django 评审服务

该服务在同一个源站上运行网站和 JSON API。默认使用 `server/var/dev.sqlite3` 中的 SQLite 数据库。配置 `DATABASE_URL` 时必须提供有效的 PostgreSQL 地址；连接无效时服务会报错，不会静默改用 SQLite。

PM 本地预览的完整步骤（分支确认、localhost 地址和本地员工登录）请参阅仓库根目录的[中文 README](../README.md)。

本地启动前，从 `.env.example` 创建 `server/.env`，把示例 `DJANGO_SECRET_KEY` 替换为稳定的随机值，安装 `requirements.txt`，应用数据库迁移，然后运行 `manage.py runserver`。本地 HTTP Cookie 安全设置只对 localhost 放宽；评审部署仍需要 HTTPS 和安全 Cookie。

静态文件只开放公开 HTML 页面以及 `app/`、`css/`、`img/` 和 `js/` 目录。本地由 Django 开发服务器提供这些文件。仓库根目录的 Render Blueprint 会收集这些允许的文件，并通过 WhiteNoise 提供访问。它需要将 Neon Free PostgreSQL 连接字符串放在 `DATABASE_URL` 中，并在构建期间应用数据库迁移。Render 免费 Web 服务的本地文件是临时的，空闲时会休眠，也不提供服务 Shell；托管账户资料应放在 PostgreSQL 中，不要存入托管应用的 SQLite 文件。

首次成功部署后，需要将员工账户交互式创建在托管 PostgreSQL 数据库中。请在自己的电脑上私密设置 `DATABASE_URL` 为 Neon 连接字符串，然后从仓库根目录运行：

~~~sh
server/var/venv/bin/python server/manage.py createsuperuser
~~~

这样管理员凭据不会写入应用代码，新注册用户也不会自动获得管理员权限。本地开发默认继续使用 Git 忽略的 SQLite 数据库；只有设置 `DATABASE_URL` 才会切换到 PostgreSQL。Neon Free 当前每个项目提供 1 GB 存储和每月 100 CU-hours；账户数量本身不决定费用。请关注最新计划额度，并为需要保留的数据准备独立备份。
