# Education API Module

`backend/education/` 是教师端和学生端的业务 API 模块，负责授课文案、问答、题库、学习路径和知识图谱约束生成。

## 核心能力

- 教师登录和学生登录。
- 基于知识图谱生成授课文案。
- 使用 `DEEPSEEK_FLASH_MODEL` 处理问答。
- 使用 `DEEPSEEK_PRO_MODEL` 处理授课文案、自然补充和题库生成。
- 预创建并缓存章节题库。
- 返回 `learning_plan` 和 `consistency_report`，让生成内容可审查。

## 主要入口

```powershell
python backend\education\api_server.py
```

默认地址：

```text
http://127.0.0.1:8001/docs
```

## 详细文档

完整说明见 [docs/modules/education-api.md](../../docs/modules/education-api.md)。
