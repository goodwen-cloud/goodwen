# Goodwen

用一份材料做问卷，在电脑上试填、同一 Wi-Fi 下现场收卷，或把问卷放到 goodwen.cc，发给外部填写者。问卷发布到 Goodwen 后，发起人的电脑关机也能继续收卷。[Goodwen 官网](https://goodwen.cc/)

## 安装和使用

| 使用场景 | 安装什么 | 能做什么 |
| --- | --- | --- |
| 本地智能体（如 Codex） | 将对应系统离线 ZIP 内的 `goodwen/` 放入宿主的技能目录 | 制作、校验、试填、局域网收卷、导出。用 Codex 授权后可发布当前版本并回读网上的答卷 |
| ChatGPT | 导入 `goodwen-chatgpt-<版本>.zip`，连接 Goodwen | 在对话中创建在线草稿、交给负责人审核、发放和分析 |
| WorkBuddy | 导入 `goodwen-connector-<版本>.zip`，通过连接器授权 | 在所选工作区制作问卷、发放并跟进答卷 |

本地包覆盖 Windows x64、macOS Apple Silicon 和 Linux x64（glibc）。在 Codex 中可将解压出的 `goodwen/` 放到 `~/.codex/skills/`（Windows 为 `%USERPROFILE%\.codex\skills\`），在新会话中用 `$goodwen` 调用。使用源码安装时复制 `skills/goodwen/`，首次运行会下载并校验对应系统的固定依赖。离线包自带这些文件。旧版用户从 `goodwen-local` 升级时，先停掉运行中的本地服务，用新的 `goodwen/` 替换旧技能目录。本地问卷和答卷保存在独立的用户数据目录。

> 把这份材料做成服务回访问卷，打开让我试填。
>
> 让同一 Wi-Fi 下的两位同事填写，然后帮我导出 CSV。
>
> 把这份问卷发布到 Goodwen，我要发到客户群。收回答后帮我总结最常见的改进意见。

第一次发布时，跟随官方授权页注册或登录 Goodwen。作者可在个人工作区审核这份问卷，批准后获取公网填写链接。本机已有的答卷可留在原处。作者也可以选定一个批次，确认后导入。直接连接 Goodwen MCP 的宿主可管理已有的在线工作区。

### 换一个会话还要登录吗

同一台电脑、同一份 Codex 用户配置会复用有效的 Goodwen 授权。更新技能后也可以继续使用。本机通过 Codex 保存 OAuth 凭据，问卷库只记录工作区与草稿、版本的对应关系及业务数据。换设备、换宿主或撤销授权后，在对应宿主重新连接即可。纯本机试填和收卷可以离线使用。

## 源码与构建

仓库名和技能名均为 `goodwen`。三个入口共用 [技能正文](skills/goodwen/SKILL.md) 和在线参考资料。

| 维护内容 | 在仓库里改哪里 | 构建产物 |
| --- | --- | --- |
| 共同工作流程、本机运行器、示例和填写页面 | `skills/goodwen/` | `dist/local/goodwen-local-<版本>-<平台>.zip` |
| ChatGPT 插件清单、图标和 MCP 连接配置 | `packages/chatgpt/` | `dist/agents/goodwen-chatgpt-<版本>.zip` |
| WorkBuddy 连接器清单、图标和 MCP 连接配置 | `packages/workbuddy/` | `dist/agents/goodwen-connector-<版本>.zip` |

开发使用 Python 3.12。在仓库根目录运行以下命令。

```sh
python -m pip install -r requirements.txt
python skills/goodwen/scripts/run.py validate skills/goodwen/examples/feedback/quiz.md
python -m unittest discover -s tests
python tools/build_release.py
python tools/build_agent_packages.py
```

两个输出目录各有一份 `SHA256SUMS`。本地包包含运行器和该系统的 Python 及依赖。两个在线包各包含同一份技能正文和三份在线参考资料，加上该平台的清单、图标和 MCP 配置。发布时提交相应的 ZIP，平台各自沿用原有包标识和版本序列。

局域网发放可用 `share <snapshot_id> --address <本机 IPv4>` 选网卡，本地数据目录可用 `GOODWEN_LOCAL_HOME` 指定。源码和运行器使用 Apache-2.0 许可证，复用部分及依赖许可证见 [NOTICE](NOTICE)。[构建与验收计划](docs/build-plan.md) · [本地发布接口说明](skills/goodwen/references/cloud.md)
