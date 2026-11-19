# 联调约定

## 本机登录如何保留

本机运行器通过 Codex App Server 调用官方服务 `https://goodwen.cc/mcp`。首次选择连接或发布时，Codex 打开 Goodwen 授权页。用户在浏览器中注册或登录并授权，Codex 完成 OAuth 回调并保存凭据。已有这个官方地址的 OAuth 连接时，运行器会复用它。日后在同一台电脑、同一 Codex 用户配置下打开新对话或升级技能，仍可复用有效授权。

Codex 管理访问令牌与刷新令牌。存储位置由 `mcp_oauth_credentials_store` 控制，支持 `auto`、`keyring` 和 `file`。Skill 只通过宿主调用工具。SQLite 在本地保存个人工作区 ID、草稿和发布版本的对应关系，以及问卷和答卷。浏览器会话由 goodwen.cc 管理。[Codex MCP 凭据配置](https://developers.openai.com/codex/config-reference/#mcp_oauth_credentials_store)

每次在线操作会用 `workspace_list` 核对授权和权限。账号改变时，已绑定的问卷仍属于原个人工作区。用户可在 Goodwen 的外部连接页撤销授权。要重新授权，可从 Codex 对该连接执行 `codex mcp login <连接名>`。本地试填和局域网收卷可以离线进行。ChatGPT 和 WorkBuddy 各自完成 Goodwen 授权。

## 本机问卷的在线接口

- `workspace_list` 确认个人工作区与有效权限。
- `questionnaire_local_sync` 准备草稿，上传所缺图片，使用上次确认的 digest 提交准确修订。中断后复用同一问卷和请求标识。
- `distribution_public_link_create` 与 `distribution_invitation_create` 使用负责人已批准的 release。返回的链接和回执与本机服务独立。
- `result_local_import` 需要另行授权的 `results:import` 权限及选定数量。读数使用 `questionnaire_response_list` 和 `questionnaire_response_get`，计数同时提供在线和本地导入来源。

`local-only` 仅控制此后的上传。云端已经保存的内容由作者在 Goodwen 中管理。
