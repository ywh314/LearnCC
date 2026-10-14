---
name: project_uses_utils
description: 本项目工具函数统一放 utils/ 模块
type: project
---

LearnCC 项目采用 utils/ 共享模块架构：
- 工具执行函数（run_bash 等）在 utils/tools.py
- hooks 在 utils/hooks.py
- skills 扫描在 utils/skills.py
- 压缩管线在 utils/compact.py
新增功能时优先考虑放 utils/ 下对应模块，而不是塞进入口 code.py。
