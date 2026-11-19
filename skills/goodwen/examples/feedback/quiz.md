---
id: service-visit
schema_version: 3
format: qml-v3
language: zh-CN
title: 服务体验回访
description: 作者记录，用于调整接待流程
participant:
  title: 今天的服务体验
  description: 花一分钟告诉我们这次到访的感受。
  completion_message: 谢谢，你的反馈已收到。
behavior:
  allow_backtracking: true
  timing: {mode: none}
welcome_image: ./assets/visit.png
translations:
  en:
    participant:
      title: Your visit today
      description: Take a minute to tell us about your visit.
      completion_message: Thank you for your feedback.
    questions:
      Q1:
        stem_md: How was your visit?
        options: {A: Good, B: Could be better}
      Q2:
        stem_md: What would you like us to keep or improve?
---

## Q1 [single] {scoring=none}
这次到访的整体体验如何？
- A) 满意
- B) 还可以改进

## Q2 [short] {scoring=none}
你希望我们保留或改进什么？
