# Goodwen 技能构建与验收计划

技能正文与共用参考资料在 `skills/goodwen/` 维护。本机安装包含原生运行器，ChatGPT 和 WorkBuddy 使用同一套在线工作流程，各自通过宿主 OAuth 连接 Goodwen MCP。

产品在所有语言中的展示名统一写作 **Goodwen**。README 标题、技能名称和平台包展示名都使用这一写法，技能调用标识为 `goodwen`。

| 工作项 | 实现 | 验收方式 |
| --- | --- | --- |
| 安装 | 在 `skills/goodwen` 提供技能、示例和启动器，按平台锁定 Python、依赖及其摘要 | 在新宿主安装后，从 Codex 技能目录发现 `goodwen`。解开完整包，在离线环境校验示例 |
| 平台打包 | 两个在线包从同一技能目录取正文和在线参考；清单、图标和 MCP 配置分别从 `packages/chatgpt/`、`packages/workbuddy/` 取 | 核对 ZIP 的七个文件、平台标识、连接配置和 SHA-256，逐字节与共用源码对照 |
| 制作 | 使用 QML v3 解析器校验作者内容、参与者文案、翻译、评分和实际渲染的图片引用 | 带图双语示例可填写，修改图片或题目生成新快照，旧答卷仍指向原版本 |
| 现场发放 | 作者预览只开放在本机，填写者通过独立的局域网地址作答。SQLite 保存每个浏览器的进度和提交 | 两个浏览器同时选择不同答案、刷新、提交，再重开问卷库导出 CSV。正式结果只包含填写者的提交 |
| 登录与在线草稿 | 通过 Codex 原生 OAuth 连接官方 MCP，列出个人工作区。首次说明会保存的问卷数量，支持仅本地和暂停 | 首次同意后保存受管理问卷的 QML 与引用图片。断线后可重试，云端独立修改产生冲突提示，历史答卷仍在设备上 |
| 发布 | 返回 Goodwen 网页审核链接。负责人确认后，使用冻结版本生成公网填写链接或定向邀约 | 同一问卷完成网页审核、公开页面验证和正式提交，关闭本机服务后仍可访问公网链接 |
| 结果 | 通过已授权的 MCP 按版本读取在线结果。作者可以另行授权导入一个确定批次的本地答卷 | 展示目标个人工作区、版本和数量再导入。重复导入返回跳过，网页和 Skill 的来源计数相符 |

本机离线包按 Windows x64、Linux x64 glibc、macOS arm64 分别构建。每个离线包附许可证及校验清单。每次发布分别记录实际运行过的平台、客户端、账号起始状态和问卷版本。

## 自动构建和发布

拉取请求和推送到 `main` 都会在 GitHub Actions 上构建三个本地 ZIP 和两个在线 ZIP。Windows、macOS、Linux 作业分别在原生系统上解开自己的安装包，用随包运行器校验带图问卷。每次构建的版本化文件和各自的摘要可从该次运行的 Artifacts 下载。

当 `main` 通过全部作业，工作流从 `skills/goodwen/scripts/runtime-lock.json` 读取发行版本，自动建立对应的 `vX.Y.Z` 标签和 GitHub Release。每个 Release 使用五个固定的安装包文件名和一份 `SHA256SUMS`，因此 README 的最新下载链接可跨版本使用。已发布的版本保留原有内容。准备下一次发行时更新本机运行器的 `__version__` 和锁文件中的版本号，有变化的在线包单独提升平台清单版本。

在仓库根目录可以本地复现构建。

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests
python tools/build_release.py
python tools/build_agent_packages.py
```

本地版本化文件位于 `dist/local/` 和 `dist/agents/`。Release 打包步骤从同一批 Actions 制品取文件，核对五个 ZIP、摘要和内嵌技能正文，再公开下载。ChatGPT 与 WorkBuddy 的平台提交通过各自的发布入口办理。
