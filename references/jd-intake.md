# JD / 岗位需求收集

筛选口径必须以岗位需求为准。岗位名、邮件主题、日期范围、发件人和学校预筛规则属于下载过滤规则/入池过滤规则，不是岗位筛选 JD，不能用于生成 AI 推荐等级。

## JD 门槛

进入 inventory、preflight、pilot、全量、重评或校准前，JD 必须包含招聘负责人实际提供或确认的岗位职责和筛选口径，并标记：

```text
JD 状态：已确认
```

agent 可以整理用户的自然语言，但不得自行补写用户没有表达过的 must-have、nice-to-have、岗位职责或一票否决项。只有岗位名和下载/学校过滤规则时，应询问：

```text
请提供完整 JD；或者确认是否仅先完成下载和学校预筛，暂不生成 AI 初筛结果。
```

在用户补充 JD 前，只允许来源收集、邮箱下载、manifest 生成和用户明确指定的学校预过滤/隔离。

## 最低可用标准

全量处理前，这些字段必须已知，或者明确标为“灵活”：

- 岗位名称
- 全职/实习/级别/年限范围
- 地点 / 远程要求
- must-have
- nice-to-have
- 一票否决项
- 筛选优先级
- 输出语言和推荐标签
- 单岗位还是多岗位分流

如果用户暂时给不全，agent 可以生成标有 `JD 状态：临时草稿/待确认` 的文件并追问关键缺口，但默认不能开始筛选。只有用户明确要求先按粗口径试跑时，才可运行最多 3-5 份 pilot；命令必须使用 `--allow-draft-pilot` 和 `--limit 3`（上限 5），结果必须标为临时草稿。全量前必须再次获得用户确认并把状态改为 `已确认`。

## agent 生成：job_requirements.md

`assets/job_requirements_template.md` 是 agent 整理需求的标准模板，不是要求用户手动填写的表单。用户可以直接粘贴 JD 或自然语言描述，agent 负责归纳成这些字段：

- 本次筛选范围
- 岗位基本信息
- 主要工作内容
- 必须满足
- 加分项
- 一票否决项
- 筛选优先级
- 筛选严格度
- 多岗位规则
- 输出偏好
- 原始 JD

## 给自动化系统传入：job_requirements.json

表单、飞书表格、ATS 导出、网页上传可以生成这个结构：

```json
{
  "jd_status": "confirmed | draft",
  "screening_mode": "single_role | multi_role",
  "role_title": "",
  "roles": [],
  "company_context": "",
  "level": "",
  "employment_type": "",
  "location_constraints": "",
  "must_have": [],
  "nice_to_have": [],
  "dealbreakers": [],
  "responsibilities": [],
  "evaluation_priorities": [],
  "screening_strictness": "strict | balanced | broad",
  "allow_cross_role_match": false,
  "source_role_hint_field": "email_subject | filename | ats_field | lark_field | none",
  "output_language": "zh-CN",
  "recommendation_labels": ["推荐", "备选", "不推荐", "需复核"],
  "custom_columns": [],
  "raw_jd": ""
}
```

## 全量前必须问清楚

只问会影响筛选结果的问题：

- 这次是单一岗位，还是多个岗位一起分流？
- 如果是多个岗位，是否允许跨岗位推荐？
- 邮件标题/文件名里写的投递岗位要不要作为参考？
- 岗位是 onsite、hybrid、remote，还是地点灵活？
- 哪些是真正 must-have，哪些只是 nice-to-have？
- 什么情况一票否决？
- 用户想要严格筛选、平衡筛选，还是宽口径探索？
- 实习生/应届生是否接受？
- 最终 Excel 用中文还是英文？

## 表格展示

生成结果表时优先使用压缩主表，避免列数过多：

- `匹配结论` 合并一句话推荐理由、must-have 匹配和 nice-to-have 匹配。
- `过往经历概况` 放候选人和岗位相关的核心经历。
- `需要注意的点` 放风险、缺失信息和需要人工复核的地方。
- `学历背景` 合并学历、学校、专业和毕业时间。实习 / 校招 / 应届岗位可以写得更详细，社招岗位只保留必要摘要。

联系方式不要合并，`邮箱`、`电话`、`链接` 分开保留，方便复制和导入 ATS。

多岗位模式下额外显示 `投递岗位` 和 `最佳匹配岗位`，并把简历整理到 `按岗位/<最佳匹配岗位>/<推荐等级>/`。邮件标题只是投递岗位提示，不是匹配证据。

真实回归案例：已下载 186 个附件，学校预过滤后保留 122 个，但没有真实 JD。此时正确动作是停止并索要 JD；不得把下载规则扩写成 JD，也不得把后续模型判断作为最终交付。
