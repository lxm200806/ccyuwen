# 语文培优默写

服务端 FastAPI + PostgreSQL，第一客户端 Vue 3。原始资源分官方目录与用户目录；抽取进草稿库，审核后发布；用户按类型组课程，按 SM-2 默写。

## 启动

本机用 Docker（已有 `postgres:14` 镜像）：

```powershell
docker compose up --build
```

- 客户端：http://localhost:8080/
- API：http://localhost:8000/api/health

账号：`admin` / `admin123`（审核发布），`kid` / `kid123`（学习）。

## 资源目录

- 官方：`server/data/official/{年}/{id}_{文件名}`
- 用户：`server/data/users/{userId}/{id}_{文件名}`

管理员在「审核」页上传官方文件，把 CSV/JSON 抽进草稿，校对后发布。用户只看见已发布库。

导入格式与 `raw/示例导入.csv` 相同：`kind,level,prompt,answer,tags,source`。

## 学习

1. 组课：勾选类型、级别，命名课程（知识点快照）。
2. 今日默写：到期复习 + 每天最多 8 张新卡，合计最多 25 张。
3. 课程掌握：学习次数 / 复习次数 / 错误次数。
4. 覆盖：全库已组课 / 学过 / 已掌握。

卡片上限：易错字 1 字，成语一条，古诗短篇或名句（答案去标点后不超过 80 字）。

## 自检

```powershell
docker compose run --rm api python -m unittest tests.test_logic
```

旧的单页 `index.html` 仍可离线打开，逻辑以服务端为准。
