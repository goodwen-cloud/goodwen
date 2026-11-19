# 批量处理、成果保存与恢复

用户要求处理整批回答、保存可回读分析、继续未完成工作或查询上轮结果时使用本流程。一次普通解释可以直接在对话中完成；只有工具确认保存的成果才可称为跨会话可回读。

## 固定要求与本轮范围

1. 沿用选定的 `workspace_id`、`pack_id`、可选 `release_id` 和用户目的。使用稳定 `reference` 调用 `processing_task_ensure`，明确 `purpose`、`purpose_version` 与 `grade_answers`。Member 只分析时用 `grade_answers=false`；评分写入仍要求相应角色和 scope。
2. 把返回的 `task_id` 与稳定引用保留在当前工作或宿主任务指令中，运行后同时保留 `run_id` 和该轮幂等键。跨会话按这些已保存引用回读，不为每次运行新建一份同义任务；引用缺失时先从已保存的宿主任务定位，不能虚构“上轮结论”。改变目的、评分要求或主动重算时使用新引用及目的版本；新任务重新明确是否覆盖旧回答。
3. 用 `processing_run_start(task_id, scope, idempotency_key, workspace_id)` 固定本轮实际可见成员。范围的问卷和版本须与任务一致，`grading_status` 留空，待处理项由成果状态决定。同一次运行恢复时复用幂等键；下一轮用新键发现晚到回答，并复用适用的已完成成果。
4. 普通查看可保留用户的时间和评分状态筛选；持续处理不要使用滚动时间上界或把“最近24小时”当作进度。用户指定固定起点时保留该起点，不随每轮时间推进。

## 逐项处理

- 用 `processing_run_get` 回读本轮结论、成员和完成情况，跟随 `next_cursor` 取齐需要的记录。`processing_items_claim` 每次领取最多20项，租约30分钟。未完成计数大于零但没有领取到项目，表示其他有效租约仍在处理，不代表没有待办。
- 对每个领取项调用 `result_get`。复用 `analyzed` 项中已经保存的发现，只补缺少的评分或保存步骤。以处理项 `id` 作为该项评分的稳定幂等键；网络重试保持原键，来源冲突后先重读。
- 要求评分时，调用 `result_grading_proposal_submit` 或 `result_grading_proposal_submit_batch`，使用最新 `grading_context_digest`、完整主观题和真实原文证据。保留人工调整，不把自动采用称为人工批准。
- 评分后重新读取 `result_get`，把实际使用的 `effective_review.id` 作为 `grading_revision_id`，未采用的 `current_proposal.id` 作为 `grading_proposal_id`；均不存在时传空值。不能保存基于旧分数的分析。
- 调用 `processing_items_save_batch`，逐项传入领取回执的 `item_id`、`lease_token`、`source_digest`，以及 `summary`、`analysis` 和实际评分引用。分析包含发现、建议及相应答卷原文证据；有必要时附计时观察和口径。
- 批量工具每次最多20项、1 MiB，逐项检查成功或错误。顶层 `ok=true` 不是全部成功；保留成功项，按原范围继续剩余批次，无需用户反复指定“下一批”。宿主原生写审批仍按实际权限执行。
- 租约失效时重新领取并重读最新来源；不要重复使用过期租约。人工改分、建议退回或来源改变后，检查 `needs_reprocessing`，只重做受影响项并保留历史。

## 结束、交付与恢复

用 `processing_run_finish` 保存本轮 `conclusion`、可选 `sections`；引用必须来自本轮实际成员与题目。服务端按实际保存情况判断完成，不能把部分失败记作全部完成。

先保存结论时保持默认 `delivery_status=not_recorded`；只有宿主确实已报告交付时才记录 `host_reported`，它不表示用户已读。通知失败后回读已保存成果重新交付，不重新评分。

若评分写入被宿主审批阻止，而其他写入仍可执行，可以保存分析检查点；宿主仍能回复时先交付结论并说明“评分尚未写入”。全部写入都受阻时，不宣称已有检查点。恢复后只继续未成功步骤。

完成后用 `response_list_show` 传入本轮 `processing_run_id`，保留该轮完整成员及目的，说明本次新处理和复用数量。处理中到达的新回答放入下一轮，不混入已完成轮次。

## 示例请求

> 处理这份问卷当前全部未完成回答，保存逐份分析和本轮结论；中断后继续，不重复已经完成的部分。

> 回读上轮已经保存的分析，保留原结论与回答依据，只补上次尚未写入的评分。
