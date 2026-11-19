# Goodwen Local

在 Codex 里根据自己的材料做问卷，当场用手机填写，答案保存在发起人的电脑。需要发给外部客户时，把同一份问卷发布到 Goodwen，拿到公网链接。电脑关机后仍可收卷。

## 安装

有完整离线 ZIP 时，解压后把其中的 `goodwen-local` 文件夹放入 `~/.codex/skills/`，在 Windows 上放入 `%USERPROFILE%\.codex\skills\`。重开 Codex 会话即可使用。

仓库公开后也可以在 Codex 中输入下面这句话。

> 从 GitHub 仓库 `goodwen-cloud/goodwen-local` 安装 `skills/goodwen-local` 下的 Skill。

本地开发可直接将仓库的 `skills/goodwen-local` 目录安装到宿主的 skills 目录。安装后在新会话中使用 `$goodwen-local`。首版运行器覆盖 Windows x64、macOS Apple Silicon 和 Linux x64，联网首次运行会获取固定版本的 Python 和依赖，逐个校验 SHA-256。完整离线 ZIP 包带有同样的制品，将其中的 `goodwen-local` 目录安装到 Codex 即可离线试填、收卷和导出。自然语言生成问卷使用宿主模型。

## 试一次

> 用 Goodwen Local 把服务回访示例复制到当前目录，打开让我试填。

> 让同一 Wi-Fi 下的两位同事填写，等我填完后导出 CSV。

> 把这份问卷发布到 Goodwen，我要发到客户群。收回答卷后，帮我查看这一版的结果。

作者预览提供“发布到 Goodwen，获取公网链接”和“在局域网发放”。首次联网由 Codex 打开 Goodwen 官方授权页。新用户可以选择页面上支持开户的 GitHub、微信等方式，按提示完成注册，继续发布手上的问卷。所管理的草稿保存在个人工作区，负责人审核具体版本后取得正式链接。既有答卷留在本机，可逐次确认导入。只需要操作已有在线问卷的用户也可以直接在 Codex 连接 Goodwen MCP。 [Goodwen](https://goodwen.cc/)

## 源码开发

开发者可用 Python 3.12 并安装 `requirements.txt` 中的依赖。以下命令从仓库根目录运行。正常安装的用户直接使用 Skill。

```sh
python skills/goodwen-local/scripts/run.py validate skills/goodwen-local/examples/feedback/quiz.md
python skills/goodwen-local/scripts/run.py save skills/goodwen-local/examples/feedback/quiz.md
python skills/goodwen-local/scripts/run.py preview <snapshot_id>
python skills/goodwen-local/scripts/run.py share <snapshot_id>
python skills/goodwen-local/scripts/run.py results <snapshot_id> --output responses.csv --format csv
python -m unittest discover -s tests
python tools/build_release.py
```

`dist/` 包含每个平台可直接安装的离线包及 `SHA256SUMS`。Linux 版针对 glibc。局域网分享选择本机网络接口，需要指定网卡时使用 `share <id> --address <本机 IPv4>`。问卷和 SQLite 答卷库保存在用户数据目录，可用 `GOODWEN_LOCAL_HOME` 显式指定。公网授权与发布需要提供本地问卷工具的 Goodwen MCP 服务，作者在 Web 完成审核。工具名称、已测入口与部署要求见 [联调说明](skills/goodwen-local/references/cloud.md)。

构建顺序、预期交付和验证步骤见[构建与验收计划](docs/build-plan.md)。使用 Apache-2.0 许可证。问卷解析、填写规则、语言资源和评分代码的来源在 NOTICE 中登记。各平台离线包附带其依赖的许可证。
