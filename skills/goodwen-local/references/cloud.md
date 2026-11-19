# 联调约定

官方服务为 `https://goodwen.cc/mcp`。使用 Codex 原生 MCP OAuth，授权凭据由宿主管理。Codex 必须支持 App Server 的 `mcpServer/tool/call`、`mcpServer/oauth/login` 与临时线程。服务端部署本地导入接口后，通过一次干净账号的真实注册、审核、发放和提交确认完整兼容性。

- `workspace_list` 确认个人工作区与有效权限。
- `questionnaire_local_sync` 准备草稿，上传所缺图片，使用上次确认的 digest 提交准确修订。中断后复用同一问卷和请求标识。
- `distribution_public_link_create` 与 `distribution_invitation_create` 使用负责人已批准的 release。返回的链接和回执与本机服务独立。
- `result_local_import` 需要另行授权的 `results:import` 权限及选定数量。读数使用 `questionnaire_response_list` 和 `questionnaire_response_get`，计数同时提供在线和本地导入来源。

`local-only` 仅控制此后的上传。云端已经保存的内容由作者在 Goodwen 中管理。
