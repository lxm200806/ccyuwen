# 家长账号

语文培优现在有三种角色：管理员 `admin`、学生 `user`、家长 `parent`。

## 能做什么

家长登录后进入「家庭」页，可以：

- 看已绑定孩子的今日一句结论、还差多少能量、相对容易错的类型
- 看近 7 日简报（练了几天、平均正确率、容易错的类型）
- 打开孩子某门课的掌握情况和错题本
- 勾选「到期复习默认用测试模式」，以及设置今日大约练几分钟
- 用年级向导给孩子组课
- 复制「让孩子打开今日默写 / 错题再练」的提示

孩子仍然用自己的账号做今日默写。家长不能改 SM-2，也不能进原始资料、审核和覆盖页。

## 怎么绑定

1. 孩子登录后，在「课程」页能看到家庭码。
2. 家长注册或登录后，填写孩子账号 + 家庭码完成绑定。
3. 一个家长可以绑定多个孩子。

演示环境（仅 DEV / `demoHints`）预置：

- 家长 `parent` / `parent123`
- 学生 `kid` / `kid123`，家庭码 `KID123`
- 管理员 `admin` / `admin123`

## 接口要点

- `POST /api/register`：注册学生或家长
- `GET /api/family`、`POST /api/family/link`：家长首页与绑定
- `GET /api/courses?studentId=`：家长查看孩子课程
- `POST /api/courses` 带 `studentId` / `wizard`：给孩子组课
- `GET /api/courses/{id}/week`：近 7 日简报
- `GET /api/courses/{id}/wrong-book`：错题本
- `GET /api/courses/{id}/today?wrongBook=1`：孩子一键再练（测试模式）
- `POST /api/courses/{id}/study-time`：累计今日时长，超过上限只提示「今天先到这儿」

今日默写和学习记录接口只接受孩子自己的登录。
