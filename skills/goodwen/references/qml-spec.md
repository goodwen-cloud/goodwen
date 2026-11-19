# QML 规范

## 目标

QML 是 quiz markdown 的轻量 DSL。它定义的是 `quiz.md` 文件内容如何写，不定义仓库目录结构。

## Front Matter

推荐字段：

```yaml
---
id: common-ability-2025
title: 共性能力测评
description: |
  面向候选人的基础能力测评。
  本试卷共 10 题，其中单选 6 题、多选 2 题、简答 2 题，预计 34 分钟完成。
tags: [common-ability, recruiting]
schema_version: 3
format: qml-v3
language: zh-CN
participant:
  description: 请根据题目要求填写。
  instructions: []
  completion_message: 提交成功，感谢参与。
behavior:
  allow_backtracking: false
  timing:
    mode: per_question
question_count: 10
question_counts:
  single: 6
  multiple: 2
  short: 2
estimated_duration_minutes: 34
---
```

说明：

- `id`：在采用 `quiz-repo-spec` 的仓库中，应与目录名一致
- `title` 是内部标题；`description` 仅为内部简介，所有版本的对外响应均移除内部简介。
- 新建和修改必须采用 QML v3；v2 仅支持历史读取与执行。仓库 manifest 仍为 v2。
- `tags`：可选，推荐写成 YAML 字符串列表，用于分类、检索和筛选
- 推荐头部补充：
  - `tags`
  - `schema_version: 3`
  - `question_count`
  - `question_counts`
  - `estimated_duration_minutes`
- QML 语法层不定义 manifest、repo path、目录结构

### 语言与完整问卷翻译（v3）

- `language` 为正文语言，也为浏览器没有匹配语种时的默认语言。新生成内容显式声明，历史源码省略时按 `zh-CN` 读取；不向旧冻结解析快照补写字段。
- `translations` 可选，以语言代码为键。译文覆盖参与者标题、说明、填写提示、完成提示，以及每道题的完整题干和全部选项。单语言问卷省略此字段。
- 支持 `zh-CN`、`zh-TW`、`en`、`ja`、`ko`、`id`、`ms`、`th`、`vi`、`fil`、`de`、`fr`、`es`、`pt-BR`、`it`、`ru`、`ar`、`tr`、`hi`、`bn`。不使用 `default_language`、`display_language` 创作配置。
- 各语言题号和选项标识必须完全对应。题型、顺序、计时、行为、分值、正确答案、traits 与 rubric 共用，译文中禁止覆盖；内部简介不进入译文。
- 译文的 `participant` 与正文同结构，`title` 必填；正文有说明、完成文案或填写提示时须有对应译文，提示条目按序对应。缺省完成文案由所选语言的系统词典提供。
- `questions` 使用题号 mapping，每题 `stem_md` 保存完整 Markdown 题干，选项 `options` 使用选项标识到 Markdown 文案的 mapping；文字题省略 `options`。
- 可在语种下覆盖 `welcome_image`、`end_image`，或在译文题目下覆盖 `media`；其余图片共用。所有引用仍受当前问卷本地资源边界、签名和大小限制。
- 草稿可以保存缺失译文的无效 revision，但所选语言全部完整后才能统一审核发布。切换显示语言不会重置答案、进度或截止时间。

新增结构示例（正文仍按原题头和选项写法放在 Front Matter 后）：

```yaml
language: zh-CN
translations:
  en:
    participant:
      title: Customer feedback
      description: Tell us about your experience.
      instructions: []
    questions:
      Q1:
        stem_md: Are you satisfied with our service?
        options:
          A: Satisfied
          B: Dissatisfied
```

### 参与者说明与规则（v3）

- `participant.title` 可选，缺省用 `title`；`description`、`instructions`、`completion_message` 独立维护，不回退内部简介。全部按纯文本显示。
- `instructions` 为字符串列表；未写完成提示时使用所选语言的系统默认文案，中文为“提交成功，感谢参与。”。
- 必须显式声明 `behavior.allow_backtracking`（布尔值）和 `behavior.timing.mode`（`none` 或 `per_question`）。
- 不限时禁止题目携带 `answer_time`；按题限时每题必填，范围 1..3600 秒。拒绝按题限时与允许返回并用。
- 可返回模式允许修改已到达题目，最后进入核对页；提交后不能修改。所有题目必填，不支持总时限。
- `estimated_duration_minutes` 为独立的可选正整数，不从题目时限相加生成；未提供不显示预计用时。
- 创作完成时总结参与者说明、计时、返回修改、评分方式与完成提示，由发布审核页展示；邀约不配置问卷行为。

### 无评分题（v3）

```markdown
## Q1 [single] {scoring=none}
领取方式
- A) 邮寄
- B) 自取

## Q2 [short] {scoring=none}
请填写收件地址。
```

此例配合 `timing.mode: none`。single、multiple、short 均支持 `scoring=none`，省略分值，禁止 max、partial、rubric、正确答案标记、选项分值及 traits。可以与计分题混用，内部零权重只用于排除计分，结果显示“无需评分”；纯无评分结果的分数和百分比为 null，不计入平均分，文字题不生成主观评分任务。

### trait 元数据（可选）

当问卷包含 `single + {scoring=traits}` 的量表题时，可在 Front Matter 中补充 `trait` 元数据。

推荐结构：

```yaml
trait:
  dimensions: [I, E, S, N, T, F, J, P]
  dimension_meanings:
    I: 更偏向独立思考、独处恢复和表达前先整理。
    E: 更偏向外部互动、即时反馈和从交流中获得能量。
  analysis_guidance:
    paired_dimensions:
      - I/E：比较独立内化与外向互动的主导倾向。
    scoring_method:
      - 将每组对立维度分别累计总分，取分高的一侧作为主倾向。
    interpretation:
      - 优先看成对维度的差值，而不是只看单个标签。
```

说明：

- `trait` 只应在问卷实际包含 traits 量表题时出现；若题面没有 `scoring=traits` 或选项级 `traits`，应删除整段 `trait` 元数据
- `dimensions` 用于声明允许出现的 trait key
- `dimension_meanings` 推荐显式写明每个维度的含义，方便消费端解释
- `analysis_guidance` 推荐写明成对维度、计分方式和解释建议

## 题头格式

```markdown
## Q1 [single] (5) {answer_time=45s}
## Q2 [multiple] (6) {partial=true, answer_time=60s}
## Q3 [short] {max=10, answer_time=10m}
## Q4 [single] (0) {scoring=traits, answer_time=20s}
## Q5 [multiple] (1) {scoring=completion, answer_time=30s}
```

规则：

- 题目以二级标题开头
- 类型：`single` / `multiple` / `short`
- 计分的 `single`、`multiple` 必须在题型后写 `(分值)`，例如 `## Q1 [single] (3)`；选项文案末尾的 `(3)` 只是文字，不作为题目分值
- 计分的 `short` 必须有 `{max=分值}`
- 可选属性：
  - `partial=true`
  - `media=./assets/q1.png`
  - `answer_time=45s`
  - `scoring=traits`
  - `scoring=completion`
- 默认情况下，`single` 是“有正确答案的单选题”
- 当 `single` 使用 `{scoring=traits}` 时，它表示“无正确答案的量表题”
- trait 量表题推荐使用 `(0)`，因为其得分来自选项权重，而不是答题正确性
- 当 `single` / `multiple` 使用 `{scoring=completion}` 时，它表示“作答计分题”：没有正确答案、不做维度评估，只要选择至少一个合法选项就得到该题满分

### 校验提示与行号

- 缺少有效分值时，提示使用实际题号、题型展示正确题头；普通计分选择题要求正整数分值。
- 校验行号从 1 开始，指向原始 QML 源码，包含 YAML 头部、分隔符、注释和空行。
- 缺选项、缺正确答案、缺 rubric 等题目整体错误指向本题题头；格式错误的题头指向该行，YAML 语法错误指向 YAML 在源码中的实际位置。
- 文件级错误及元数据语义错误仍使用第 1 行作为文件级定位。

## 题干与图片

- 题干是题头后的正文
- 题干中可使用 Markdown 图片或 HTML `<img>`
- 示例路径统一使用 `./assets/...`
- Workspace 源码编辑仅接受已上传到当前草稿的本地 `./assets/...` 图片；在光标处粘贴或拖入图片会先校验并上传，再插入内容寻址 Markdown。`data:`、`http:`、`https:` 等内联或外链图片不能发布。
- 发布资源以实际 Markdown 渲染得到的图片引用为准，并随不可变源码 revision 固化；代码块、行内代码或普通说明文字中的图片示例不会被复制到 Release。

## 选项题

格式：

```markdown
- A) 选项文本
- B*) 正确选项
```

trait 量表题示例：

```markdown
## Q1 [single] (0) {scoring=traits, answer_time=20s}

我通常会在做决定前先把计划排到比较细。

- A) 非常同意 {traits=J:2}
- B) 比较同意 {traits=J:1}
- C) 中立
- D) 比较不同意 {traits=P:1}
- E) 非常不同意 {traits=P:2}
```

规则：

- 默认模式下，正确答案在选项字母后加 `*`
- `single` + `{scoring=traits}` 模式下不得出现 `*`
- `single` / `multiple` + `{scoring=completion}` 模式下不得出现 `*`，也不得写选项级 `traits`
- trait 量表题的得分来自选项上的 `traits`
- 选项可追加 traits / points 等属性
- `traits` 的格式为 `KEY:INT[,KEY:INT...]`
- 当题目使用 `{scoring=traits}` 时，建议至少一个非中立选项带 `traits`

作答计分题示例：

```markdown
## Q2 [multiple] (1) {scoring=completion, answer_time=30s}

您目前可以持续深耕并直接触达资金资源的城市或地区有哪些？可多选。

- A) 北京
- B) 上海
- C) 深圳
- D) 其他城市或地区
```

## 简答题

计分文字题必须包含 `[rubric]...[/rubric]`；无评分文字题禁止评分标准。

```markdown
[rubric]
1) 关键点一
2) 关键点二
3) 表达清晰
[/rubric]
```

新建或修改的 QML 禁止使用 Front Matter `llm` 或 `[llm]...[/llm]`。
历史冻结 Release 的 parser 仍可读取旧字段，但评分上下文始终忽略它；简答题只以
`[rubric]` 作为人工与外部智能体共同可见的评分标准。

## 首图与尾图

- 首题前仅支持单独一张 Markdown 图片，映射为 `welcome_image`
- 末题后仅支持单独一张 Markdown 图片，映射为 `end_image`
- `intro` / `outro` 图片都属于可选项，不是问卷必填内容
- 首图和尾图统一推荐 `1600 × 800 px`（`2:1`）；较小文件可用 `1200 × 600 px`，尺寸是建议而非上传限制
- 答题开始页与提交完成页按原比例完整显示首尾图，横幅最高 256 CSS px，手机随宽度缩小，两侧以同图虚化背景衔接；管理端 160 CSS px 高的预览条不代表原图应只有 160 px 高
- 主体放大居中，四周留约 10% 安全边距，避免小字、二维码和绘制按钮；页面单独显示标题、说明与操作。插画优先 JPEG/WebP，扁平图形可用 PNG
- GW 中每张欢迎图、结尾图最多 2 MB（2,097,152 字节）；限制由资源上传/同步层校验，不由 parser 判断
- Plain 草稿可通过 `questionnaire_draft_image_set` 接收外部生成的图片，自动写入内容寻址路径；Git 仓库仍使用当前 quiz 的 `./assets/...`

示例：

```markdown
![intro](./assets/welcome.png)
...
![bye](./assets/thanks.png)
```

## 最小示例

```markdown
---
id: common-ability-2025
title: 共性能力测评
description: |
  面向候选人的基础能力测评。
  本试卷共 2 题，其中单选 1 题、多选 0 题、简答 1 题，预计 12 分钟完成。
tags: [common-ability, demo]
schema_version: 3
format: qml-v3
language: zh-CN
participant:
  description: 请根据题目要求填写。
  instructions: []
  completion_message: 提交成功，感谢参与。
behavior:
  allow_backtracking: false
  timing:
    mode: per_question
question_count: 2
question_counts:
  single: 1
  multiple: 0
  short: 1
estimated_duration_minutes: 12
---

![intro](./assets/welcome.png)

## Q1 [single] (5) {media=./assets/q1.png, answer_time=45s}
选择正确描述：

- A) 选项A
- B*) 选项B

## Q2 [short] {max=10, answer_time=10m}
请简述原因。

[rubric]
1) 观点准确
2) 论证清晰
3) 表达完整
[/rubric]

![bye](./assets/thanks.png)
```

## 人格量表示例

```markdown
---
id: personality-type-5d-80
title: 人格类型测试（五维版·80题）
description: |
  基于公开人格维度框架设计的原创量表。
  本试卷共 80 题，均为 5 级同意度单选题，预计 27 分钟完成。
tags: [personality, mbti-style, traits]
schema_version: 3
format: qml-v3
language: zh-CN
participant:
  description: 请根据题目要求填写。
  instructions: []
  completion_message: 提交成功，感谢参与。
behavior:
  allow_backtracking: false
  timing:
    mode: per_question
question_count: 80
question_counts:
  single: 80
  multiple: 0
  short: 0
estimated_duration_minutes: 27
trait:
  dimensions: [I, E, S, N, T, F, J, P, A, TU]
  dimension_meanings:
    I: 更偏向独立思考、独处恢复精力、表达前先内化整理。
    E: 更偏向外部互动、即时表达、从社交和讨论中获得能量。
    S: 更偏向经验、事实与可验证细节，重视现实可行性。
    N: 更偏向可能性、趋势和抽象联想，重视概念与潜在机会。
    T: 更偏向一致标准、逻辑推理和客观判断。
    F: 更偏向关系感受、共情反馈和人的影响。
    J: 更偏向计划、秩序、提前安排和明确边界。
    P: 更偏向灵活应变、边走边看和根据变化调整。
    A: 更偏向情绪稳定、自我接纳和压力下保持平衡。
    TU: 更偏向敏感波动、反复反思和更强的不确定感受。
  analysis_guidance:
    paired_dimensions:
      - I/E：比较独处内化与外向互动的主导倾向。
      - S/N：比较经验务实与抽象联想的主导倾向。
      - T/F：比较逻辑标准与关系感受的主导倾向。
      - J/P：比较计划秩序与灵活应变的主导倾向。
      - A/TU：比较稳定果断与敏感波动的主导倾向。
    scoring_method:
      - 将每组对立维度分别累计总分，取分高的一侧作为该组主倾向。
      - 若同组平分，则依次比较 +2 次数、+1 次数；若仍平分，固定落位 I/S/T/J/A。
    interpretation:
      - 优先看每组两侧的相对差值，差值越大说明偏好越稳定。
      - 若某组差值很小，更适合解释为情境依赖，而不是强行贴类型标签。
---

## Q1 [single] (0) {scoring=traits, answer_time=20s}
我通常会在做决定前先把计划排到比较细。

- A) 非常同意 {traits=J:2}
- B) 比较同意 {traits=J:1}
- C) 中立
- D) 比较不同意 {traits=P:1}
- E) 非常不同意 {traits=P:2}
```
