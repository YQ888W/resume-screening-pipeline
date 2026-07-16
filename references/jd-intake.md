# JD / 岗位需求收集

筛选口径必须以岗位需求为准。原始 JD 可以很粗，但全量筛选前必须把真正影响排序的标准写清楚。

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

如果用户暂时给不全，agent 应先根据已有 JD / 自然语言需求生成 `job_requirements.md` 草稿，只追问关键缺口。可以先跑 3-5 份小样本，用结果帮助用户修正标准，但不能直接跑全量。

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

不要为了追求完美 JD 卡住 pilot。可以先跑 3-5 份，再调口径。
