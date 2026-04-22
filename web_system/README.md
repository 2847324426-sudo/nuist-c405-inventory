# 实验室元器件库存管理（公网部署版，带账号加密）

这是一个可以部署到公网的 Flask 网页系统。
部署完成后，实验室里任何一台能联网的电脑，只要打开同一个网址，就能看到同一份库存数据，并且互通修改。

## 已包含的能力

- 账号登录
- 密码加密存储（不是明文）
- 管理员/普通成员角色
- 元器件新增、编辑
- 入库 / 领用 / 库存调整
- 领用记录自动绑定当前登录账号
- 多级分类路径（例如：芯片 - STM32 - STM32F103）
- 低库存提醒
- 云端数据库支持（推荐 PostgreSQL）

## 适合你的用法

你想要的是：

- 实验室任何一台能联网的电脑都能打开
- 所有人看的是同一份数据
- 改动实时互通
- 还要有账号登录和密码加密

这个项目就是按这个思路做的。

## 技术说明

- 后端：Flask
- 数据库：PostgreSQL（推荐部署时使用）
- 登录：Flask-Login
- 密码加密：Werkzeug password hash
- 部署：Gunicorn

## 本地运行

```bash
pip install -r requirements.txt
python app.py
```

默认会在本地使用 SQLite，方便测试。

## 公网部署思路

### 方案一：部署到 Render / Railway / 服务器

你需要准备：

1. 一个公网部署平台
2. 一个 PostgreSQL 数据库
3. 设置环境变量：

```text
SECRET_KEY
DATABASE_URL
DEFAULT_ADMIN_USERNAME
DEFAULT_ADMIN_PASSWORD
DEFAULT_ADMIN_DISPLAY_NAME
COOKIE_SECURE=1
```

### 数据库 URL 例子

```text
postgresql+psycopg://用户名:密码@主机:5432/数据库名
```

## 默认管理员

系统第一次启动时，会自动创建一个管理员账号。

默认读取这些环境变量：

- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_PASSWORD`
- `DEFAULT_ADMIN_DISPLAY_NAME`

如果没设置，就会默认创建：

- 用户名：`admin`
- 密码：`admin123456`

部署完成后，**第一件事就是改密码**。

## 页面说明

- `/login` 登录页
- `/items` 库存页
- `/transactions` 出入库记录
- `/users` 用户管理（仅管理员可见）

## 安全提醒

1. 公网部署时务必设置一个强 `SECRET_KEY`
2. 默认管理员密码部署后要立刻改
3. 部署到 HTTPS 环境时，把 `COOKIE_SECURE=1`
4. 不要把 `.env` 文件上传到公开仓库
