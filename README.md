<h1 align="center"><img src="packages/chatgpt/assets/icon.png" width="76" height="76" alt=""><br>Goodwen</h1>
<p align="center"><strong>简体中文</strong> · <a href="README.en.md" lang="en">English</a></p>

Goodwen 帮你在智能体对话里把材料做成问卷，发给填写者，再用实际答卷回答问题。在 Codex 里可以先试填、现场收卷。要把问卷发给外地客户，就发布到 goodwen.cc，电脑关机后也能继续收卷。

[用 Codex 安装](#本地-codex) · [连接 ChatGPT 或 WorkBuddy](#chatgpt-和-workbuddy) · [注册或登录 Goodwen](https://goodwen.cc/login)

## 做出第一份问卷

### 本地 Codex

把这段提示词粘贴到本机的 Codex。首次运行需要联网，校验成功时会显示《服务体验回访》、共 2 道题。

```text
$skill-installer 请从下面的 GitHub 地址安装 Goodwen，并用自带的服务回访示例验证安装。
https://github.com/goodwen-cloud/goodwen/tree/main/skills/goodwen
```

安装后，新开一个 Codex 会话，试试这句话。也可以附上自己的材料，说明想问谁、想弄清什么。

> 用 $goodwen 把自带的《服务体验回访》示例复制到当前工作目录。校验并保存问卷，给我作者试填链接。

打开链接，点「开始作答」，逐题保存，在「核对并提交」页检查选项和简答。作者试填单独记录。想改题时，在对话里说明要改哪里，再试填新版本。

<details>
<summary>离线安装（Windows、macOS、Linux）</summary>

在能联网的设备上下载目标电脑对应的 ZIP。三个离线包都内置了运行环境。[Windows x64](https://github.com/goodwen-cloud/goodwen/releases/latest/download/goodwen-windows-x64.zip) · [macOS Apple Silicon](https://github.com/goodwen-cloud/goodwen/releases/latest/download/goodwen-macos-arm64.zip) · [Linux x64（glibc）](https://github.com/goodwen-cloud/goodwen/releases/latest/download/goodwen-linux-x64.zip)

解压并把整个 `goodwen` 文件夹复制到 Codex 技能目录。Windows 默认为 `%USERPROFILE%\.codex\skills\`，macOS 和 Linux 默认为 `~/.codex/skills/`。新开会话，使用上面的试填提示词。

</details>

### ChatGPT 和 WorkBuddy

在客户端添加 Goodwen，按提示在 goodwen.cc 注册或登录并授权。手动添加 MCP 服务时，地址填 `https://goodwen.cc/mcp`，验证方式选 OAuth。支持导入 ZIP 的客户端也可以使用对应安装包。

| 客户端 | 连接步骤 | 最新安装包 |
| --- | --- | --- |
| ChatGPT | [ChatGPT 连接教程](https://goodwen.cc/agents/chatgpt) | [下载 ChatGPT ZIP](https://github.com/goodwen-cloud/goodwen/releases/latest/download/goodwen-chatgpt.zip) |
| WorkBuddy | [WorkBuddy 连接教程](https://goodwen.cc/agents/workbuddy) | [下载 WorkBuddy ZIP](https://github.com/goodwen-cloud/goodwen/releases/latest/download/goodwen-workbuddy.zip) |

回到对话，选择 Goodwen，发出下面的请求。选好工作区后，就能拿到在线草稿的审核链接。

> 列出我可用的 Goodwen 工作区。等我选好后，创建一份不计分的服务回访。第一题问整体体验，选项是「满意」「还可以改进」。第二题问「你希望我们保留或改进什么？」请给我草稿审核链接。

## 把问卷发给填写者

<picture>
  <source media="(max-width: 600px)" srcset="docs/media/survey-flow-mobile.svg">
  <img src="docs/media/survey-flow.svg" alt="从材料生成问卷后，可在同一 Wi-Fi 下收卷，或经负责人审核发布到 goodwen.cc，再按版本查看答卷。">
</picture>

### 发布到 goodwen.cc

1. **打开审核链接。** 本地 Codex 用户在作者试填页点「发布到 Goodwen，获取公网链接」。首次连接时，核对要将哪些本地问卷及其后续修改保存到个人工作区，再按提示注册或登录并授权。ChatGPT 和 WorkBuddy 用户直接打开对话返回的草稿审核链接。
2. **确认发布。** 工作区负责人在 Goodwen 网页核对本版的题目、选项和计分设置，点「确认发布」。
3. **分享填写链接。** 本地用户回到作者试填页，点「我已审核，获取链接」。在线用户在原对话里说「为刚批准的版本创建公开填写链接」。把返回的填写链接发给客户，用另一台设备打开就能检查填写者看到的页面。

同一份 Codex 用户配置会复用有效授权。之前在本机收集的答卷仍在原设备，需要导入一批历史答卷时，先核对目标工作区、已发布的版本和答卷数量，再单独确认。[本地发布操作图](docs/media/publish-guide.svg) · [网页审核教程](https://goodwen.cc/help/review-and-distribute)

### 在同一 Wi-Fi 下收卷

回到本地作者试填页，点「在局域网发放」，把生成的完整地址发给现场的同事。他们在同一网络下用手机打开链接，逐题保存并提交，你的电脑会收到正式答卷。收卷期间保持电脑和本地服务运行。`127.0.0.1` 只供发起人在自己电脑上试填。

<details>
<summary>查看填写者在手机上核对答卷的示例</summary>

<img src="docs/media/answer-review.png" width="300" alt="手机核对页显示所选的「还可以改进」和一条具体建议，填写者可以逐题修改再提交。">

</details>

## 查看答卷

在发放问卷的工作区或本地 Codex 对话里，指明要查看的版本。

- **现场收卷后导出 CSV**　“统计这版服务回访每个选项的人数，把简答原文一起导出到当前目录的 `feedback.csv`。”
- **公网收卷后分析建议**　“查看刚发布的服务回访，按提及人数排列改进建议，每条附上对应的题目和填写者原话。”

## 教程与源码

- 从作者试填到手机作答的完整示例、终端命令及旧版升级步骤，见[图文教程](docs/guide.md)。在线答卷的筛选和分析见[官网教程](https://goodwen.cc/help/read-and-analyze)。
- 本机运行器和示例位于 [skills/goodwen](skills/goodwen/)。[ChatGPT](packages/chatgpt/) 和 [WorkBuddy](packages/workbuddy/) 共用这份技能，各自提供客户端配置。
- 开发使用 Python 3.12。GitHub Actions 自动构建并验证五个安装包。[构建说明](docs/build-plan.md) · [最新发布](https://github.com/goodwen-cloud/goodwen/releases/latest) · [SHA-256 校验清单](https://github.com/goodwen-cloud/goodwen/releases/latest/download/SHA256SUMS)

[Apache-2.0 许可证](LICENSE) · [第三方声明](NOTICE)
