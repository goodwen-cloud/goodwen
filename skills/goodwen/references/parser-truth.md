# QML Parser 契约与边界

本文档是 `qml-authoring` 的自包含 parser 契约。

- 如果当前环境能访问实际 parser 实现与测试，应以本地实现为准，并把本文档当成“默认口径”
- 如果当前环境不能访问源码，本文档就是该 skill 可依赖的最小事实集

## 默认支持的行为

### Front Matter

- 若存在 Front Matter，必须以 `---` 开始并闭合
- Front Matter 必须是 YAML mapping
- 若缺少 `id`，允许 parser 生成临时 id；但接入 quiz 仓库规范的同步器通常不会接受这种 quiz
- 当前 parser 为历史 Release 回放仍会读取 `llm`，但草稿工作流拒绝新写入；其余 Front Matter 投影以 parser 实现为准
- v3 要求 schema_version: 3 / format: qml-v3 一致；parser 保留 v2 历史支持，拒绝未知或冲突版本。
- v3 必须显式声明 behavior.allow_backtracking 布尔值及 timing.mode: none / per_question；按题限时加可返回被拒绝。
- participant 支持可选字符串 title、description、completion_message 及字符串列表 instructions，拒绝其他字段。
- 所有版本 public spec 均移除内部 description，参与者说明不回退到内部简介。
- estimated_duration_minutes 是独立保存的可选正整数，不能被题目时限合计覆盖。
- `tags` 若出现，推荐为 YAML 字符串列表；parser 应按原始列表值保留
- `trait` 若出现，推荐为 YAML mapping；其中 `dimensions` 常用，`dimension_meanings` 与 `analysis_guidance` 推荐显式维护
- 若题面没有实际使用 `scoring=traits` 或选项级 `traits`，作者侧应删除 `trait` 元数据，避免保留无效说明

### 多语言

- 显式 `language` 必须属于 20 种支持语种；历史源内容缺省时保持原解析快照结构，读取默认中文。
- `translations` 的题号与选项键完全对应正文。每个语种的 participant 与题干/选项分别执行白名单和完整性校验，拒绝评分字段、未知字段和缺失内容。
- 公开投影逐语言排除内部简介、rubric、正确答案等信息。渲染和图片资源清单遍历全部语种。
- 语言资源目录与系统完成文案为 `static/take/locales.json`；浏览器 ES 模块由静态资源同步脚本生成。

### 题头

- v3 拒绝空问卷及带已知题型但格式错误的题头，防止静默漏题；answer_time 等属性必须置于花括号内。v2 历史解析保持原行为。

- 题头正则只接受：
  - `## <label> [single|multiple|short]`
  - 选项题可带 `(points)`
  - 属性块写在 `{...}`
- 若 `label` 不符合 `Q...`，parser 会自动生成 `Q1/Q2/...`
- 重复 QID 会报 `Duplicate QID`
- 题头属性可包含自定义键值；当前文档显式约定了 `scoring=traits` 和 `scoring=completion` 语义

### answer_time

- 支持整数秒，或 `s/m/h` 后缀
- 范围必须在 `1..3600` 秒；v2 与 v3 per_question 每题必填，v3 none 禁止携带。

### 选项题

- `single` / `multiple` 必须有选项
- `single` 默认必须恰好一个正确答案
- 当 `single` 的题头属性包含 `scoring=traits` 时，该题表示量表题：
  - 不需要正确答案
  - 不得出现 `*`
  - 得分来自选项上的 `traits`
  - 仍然只能选择一个选项
- 当 `single` / `multiple` 的题头属性包含 `scoring=completion` 时，该题表示作答计分题：
  - 不需要正确答案
  - 不得出现 `*`
  - 不得出现选项级 `traits`
  - 单选选择任一合法选项即得满分，多选选择至少一个合法选项即得满分
- `multiple` 至少一个正确答案
- 选项尾部可带属性块
- `traits` 的约定格式为 `KEY:INT[,KEY:INT...]`
- trait 量表题的最终人格编码推导属于消费端逻辑，不属于 parser 本身

### 简答题

- 计分 `short` 必须包含 `[rubric]`
- `max_points` 来自 `{max=...}`

### 无评分题

- v3 single/multiple/short 支持 scoring=none，v2 拒绝。
- 禁止题目分值、max、partial、rubric、正确答案标记、选项 points 和 traits。
- 内部计分权重为零，显示无需评分；无评分文字题无需 rubric，不进主观评分任务。

### 首图 / 尾图

- 仅当首题前或末题后是“单独一张 Markdown 图片”时才会被识别
- parser 会保留原始路径字符串，不负责判断这个路径是否可被同步

### 校验诊断

- `QmlParseError.line` 使用从 1 开始的原始源码行号，计入 YAML 头部、分隔符、注释及空行；LF 与 CRLF 的定位一致。
- 题目整体校验失败时定位该题题头，不使用解析结束位置；格式错误的题头定位该行。
- YAML 语法错误由 parser 转为 `QmlParseError`，提示为“Front Matter YAML 无效”，行号指向原始源码位置。草稿工作流沿用错误码 `qml_parse_error`，直接传递 parser 的消息与行号。
- 文件级及元数据语义错误保留第 1 行定位。
- 普通计分选择题缺失或使用非正数分值时，提示展示实际题号、题型对应的正确题头，并说明选项文案中的 `(3)` 不作为题目分值。

## 默认不由 parser 负责的事

以下校验不属于 QML parser，而属于 quiz repo 同步层：

- `id` 是否等于目录名
- 图片是否位于 `assets/`
- 仓库是否有 manifest
- 普通 Markdown 链接是否合法
- 图片是否存在、是否越界、是否超大小限制（欢迎/结尾图 2 MB，其他图片 1 MB）

Workspace 的 Plain 草稿在 parser 之后还有一层 authoring 校验：实际会渲染的图片必须是当前草稿已上传的本地 `assets/` 资源，`data:` 与远程 URL 会被拒绝。资源集合按渲染后的 `<img>` 引用计算，因此 fenced code 或 inline code 中的示例不会进入正式 Release；该清单随不可变 source revision 一起固化，发布事务只读取被审批 revision 的清单。这属于草稿/发布边界，不改变 parser 保留原始路径字符串的职责。

这些问题去看 `skills/quiz-repo-spec/`。

## 使用约束

- 不要把“某个项目里的 parser 文件路径”写成此 skill 的前提
- 不要假设所有接入方都公开了 parser 源码
- 当外部环境的实际 parser 行为与本文档冲突时，应优先记录冲突点，再按接入方实现修正
