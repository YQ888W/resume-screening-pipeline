#!/usr/bin/env python3
"""Regenerate the public, fictional Excel example with the production formatter."""

from __future__ import annotations

from pathlib import Path

from resume_screening_pipeline import write_xlsx


SUMMARY_ROWS = [
    {
        "Candidate ID": "C0001",
        "候选人姓名": "林若宁（虚构）",
        "AI 初筛结果": "推荐",
        "人工初筛结果": "",
        "人工初筛判断依据": "",
        "匹配结论": "有 HR SaaS 销售经验，客户画像与岗位高度重合。\n满足：3 年以上 B2B SaaS 销售。\n加分：有 outbound 和大客户推进经验。",
        "目前（最近）公司和 title": "Senior AE / 示例科技",
        "过往经历概况": "4 年 B2B SaaS 销售，负责 HR 系统企业客户，年度 quota 128%。",
        "需要注意的点": "需确认英文口语和可到岗时间。",
        "学历背景": "本科 / 示例大学 / 市场营销 / 2019",
        "邮箱": "candidate1@example.com",
        "电话": "13800000001",
        "链接": "https://example.com/candidate-1",
        "原始文件名": "fictional_candidate_1.pdf",
        "解析状态": "ok/ok",
    },
    {
        "Candidate ID": "C0002",
        "候选人姓名": "周启明（虚构）",
        "AI 初筛结果": "备选",
        "人工初筛结果": "其实一般",
        "人工初筛判断依据": "销售经验有，但客户群体偏 IT，不应进入第一优先级。",
        "匹配结论": "销售能力不错，但 HR Tech 相关性不足。\n部分满足：B2B 软件销售经验明确。\n加分不足：没有 HR/招聘系统买家经验。",
        "目前（最近）公司和 title": "Account Manager / 示例云服务",
        "过往经历概况": "云服务 AM，做过续约和 upsell，客户多为 IT 部门。",
        "需要注意的点": "可能需要较长行业转换；是否能销售 HR 场景待验证。",
        "学历背景": "硕士 / 示例大学 / 信息管理 / 2021",
        "邮箱": "candidate2@example.com",
        "电话": "13800000002",
        "链接": "https://example.com/candidate-2",
        "原始文件名": "fictional_candidate_2.pdf",
        "解析状态": "ok/ok",
    },
    {
        "Candidate ID": "C0003",
        "候选人姓名": "王嘉禾（虚构）",
        "AI 初筛结果": "不推荐",
        "人工初筛结果": "",
        "人工初筛判断依据": "",
        "匹配结论": "履历偏纯后端研发，缺少销售、客户或市场证据。",
        "目前（最近）公司和 title": "Backend Engineer / 示例数据公司",
        "过往经历概况": "5 年后端开发，主要负责数据平台和 API 性能优化。",
        "需要注意的点": "可能适合工程岗；不适合当前销售岗位。",
        "学历背景": "本科 / 示例大学 / 计算机科学 / 2020",
        "邮箱": "candidate3@example.com",
        "电话": "13800000003",
        "链接": "https://example.com/candidate-3",
        "原始文件名": "fictional_candidate_3.pdf",
        "解析状态": "ok/ok",
    },
    {
        "Candidate ID": "C0004",
        "候选人姓名": "陈安琪（虚构）",
        "AI 初筛结果": "需复核",
        "人工初筛结果": "",
        "人工初筛判断依据": "",
        "匹配结论": "扫描件文字提取不完整，无法安全判断。",
        "目前（最近）公司和 title": "",
        "过往经历概况": "仅识别到部分公司名，关键经历缺失。",
        "需要注意的点": "需要本地 OCR 或人工打开原始文件查看。",
        "学历背景": "",
        "邮箱": "",
        "电话": "",
        "链接": "",
        "原始文件名": "fictional_candidate_4_scan.pdf",
        "解析状态": "needs_local_review/needs_local_review",
    },
]


EVIDENCE_ROWS = [
    {
        "Candidate ID": row["Candidate ID"],
        "候选人姓名": row["候选人姓名"],
        "工作经历": row["过往经历概况"],
        "项目/研究": "",
        "岗位相关证据": row["匹配结论"],
        "潜在匹配信号": "",
        "技能": "",
        "工具": "",
        "语言": "",
        "量化成果": "",
        "证据质量": "strong" if row["AI 初筛结果"] != "需复核" else "weak",
        "建议面试问题": "请核实简历中的关键经历和岗位要求。",
        "原始文件名": row["原始文件名"],
    }
    for row in SUMMARY_ROWS
]


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "assets" / "resume_screening_results_sample.xlsx"
    write_xlsx(destination, SUMMARY_ROWS, EVIDENCE_ROWS)
    print(destination)


if __name__ == "__main__":
    main()
