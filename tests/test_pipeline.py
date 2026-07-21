from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import resume_screening_pipeline as pipeline  # noqa: E402
import email_attachment_downloader as email_downloader  # noqa: E402


class PipelineTests(unittest.TestCase):
    def test_jd_gate_rejects_download_rules_as_screening_jd(self) -> None:
        download_rules_only = {
            "raw_jd": """# AI 数据分析工程实习生
- JD 状态：临时草稿/待确认
- 最近 7 天
- 邮件主题包含：AI 数据分析工程实习生
- 标题学校明显弱校不下载/不入池
"""
        }
        with self.assertRaisesRegex(RuntimeError, "下载过滤规则不等于完整 JD"):
            pipeline.require_screening_jd(download_rules_only, "preflight")

    def test_confirmed_jd_passes_gate(self) -> None:
        jd = {
            "jd_status": "confirmed",
            "role_title": "数据分析工程师",
            "responsibilities": ["分析业务数据"],
            "must_have": ["SQL"],
            "nice_to_have": ["Python"],
            "dealbreakers": ["无"],
            "evaluation_priorities": ["SQL 项目经验"],
        }
        pipeline.require_screening_jd(jd, "run")
        self.assertEqual(pipeline.jd_status(jd), pipeline.JD_STATUS_CONFIRMED)

    def test_confirmed_label_cannot_bypass_incomplete_jd(self) -> None:
        fake_confirmed = {
            "jd_status": "confirmed",
            "role_title": "AI 数据分析工程实习生",
            "raw_jd": "最近 7 天；按邮件主题和学校过滤",
        }
        with self.assertRaisesRegex(RuntimeError, "当前还缺少"):
            pipeline.require_screening_jd(fake_confirmed, "run")

    def test_confirmed_markdown_template_passes_gate(self) -> None:
        jd = {"raw_jd": """# 岗位需求表
## JD 状态
- JD 状态：已确认
## 岗位基本信息
- 岗位名称：数据分析工程师
## 这个人来了之后主要做什么
- 分析业务数据
## 必须满足（Must-have）
- SQL
## 加分项（Nice-to-have）
- Python
## 一票否决项（Dealbreakers）
- 无
## 筛选优先级
1. SQL 项目经验
"""}
        pipeline.require_screening_jd(jd, "preflight")

    def test_draft_jd_requires_explicit_small_pilot(self) -> None:
        draft = {"jd_status": "draft", "raw_jd": "临时粗口径"}
        pipeline.require_screening_jd(
            draft,
            "pilot",
            allow_draft_pilot=True,
            limit=5,
        )
        for limit in (0, 6, 122):
            with self.assertRaisesRegex(RuntimeError, "最多 5 份"):
                pipeline.require_screening_jd(
                    draft,
                    "pilot",
                    allow_draft_pilot=True,
                    limit=limit,
                )
        with self.assertRaisesRegex(RuntimeError, "全量前仍须获得用户确认"):
            pipeline.require_screening_jd(draft, "run")

    def test_real_incident_is_documented_as_jd_gate_regression(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
        intake_text = (root / "references" / "jd-intake.md").read_text(encoding="utf-8")
        agent_text = (root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("已下载 186 个附件", skill_text)
        self.assertIn("预过滤后保留 122 个", skill_text)
        self.assertIn("下载过滤规则", intake_text)
        self.assertIn("请提供完整 JD，或确认是否仅先完成下载和学校预筛", agent_text)

    def test_skill_requires_source_confirmation_before_file_discovery(self) -> None:
        skill_text = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## 第 0 步：确认简历来源", skill_text)
        self.assertIn("没有默认来源", skill_text)
        self.assertIn("不要扫描工作区之外", skill_text)

    def test_skill_prefers_imap_over_browser_for_bulk_email(self) -> None:
        skill_text = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("邮箱批量下载的工具优先级", skill_text)
        self.assertIn("内置脚本本身就是邮箱连接方式", skill_text)
        self.assertIn("不要用浏览器逐封处理几十或几百封邮件", skill_text)

    def test_candidate_ids_survive_rename_and_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resumes = root / "resumes"
            work = root / "work"
            resumes.mkdir()
            original = resumes / "b.txt"
            original.write_text("original candidate resume", encoding="utf-8")
            first = pipeline.collect_files(resumes, work)
            self.assertEqual(first[0].candidate_id, "C0001")

            original.rename(resumes / "z.txt")
            (resumes / "a.txt").write_text("new candidate resume", encoding="utf-8")
            second = pipeline.collect_files(resumes, work)
            by_name = {item.path.name: item.candidate_id for item in second}
            self.assertEqual(by_name["z.txt"], "C0001")
            self.assertEqual(by_name["a.txt"], "C0002")

    def test_duplicate_files_are_deduplicated_by_hash(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resumes = root / "resumes"
            resumes.mkdir()
            (resumes / "a.txt").write_text("same", encoding="utf-8")
            (resumes / "b.txt").write_text("same", encoding="utf-8")
            self.assertEqual(len(pipeline.collect_files(resumes, root / "work")), 1)

    def test_score_only_rejects_uncached_resume(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resume_path = root / "candidate.txt"
            resume_path.write_text("candidate resume", encoding="utf-8")
            resume = pipeline.ResumeFile("C0001", resume_path, resume_path.name, pipeline.sha1_file(resume_path))
            with self.assertRaisesRegex(RuntimeError, "默认不会处理新简历"):
                pipeline.score_existing(resume, {"raw_jd": "role"}, root / "work")

    def test_cache_reuses_extraction_but_invalidates_changed_jd(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resume_path = root / "candidate.txt"
            resume_path.write_text("B2B SaaS sales experience " * 12, encoding="utf-8")
            resume = pipeline.ResumeFile("C0001", resume_path, resume_path.name, pipeline.sha1_file(resume_path))
            extraction = json.dumps({"name": "测试候选人", "short_summary": "B2B SaaS 销售"}, ensure_ascii=False)
            screening = json.dumps({"recommendation_level": "推荐", "one_line_recommendation_reason": "匹配"}, ensure_ascii=False)
            with patch.object(pipeline, "chat_completion", side_effect=[extraction, screening, screening]) as mocked:
                pipeline.process_one(resume, {"raw_jd": "JD version one"}, root / "work")
                pipeline.process_one(resume, {"raw_jd": "JD version one"}, root / "work")
                pipeline.process_one(resume, {"raw_jd": "JD version two"}, root / "work")
            self.assertEqual(mocked.call_count, 3)

    def test_invalid_model_label_becomes_manual_review(self) -> None:
        result = pipeline.normalize_screening({"recommendation_level": "A+"})
        self.assertEqual(result["recommendation_level"], "需复核")
        self.assertIn("无效推荐标签", result["main_risks_or_missing_info"])

    def test_spreadsheet_formula_is_neutralized(self) -> None:
        self.assertEqual(pipeline.spreadsheet_safe("=HYPERLINK(\"x\")"), "'=HYPERLINK(\"x\")")
        self.assertEqual(pipeline.spreadsheet_safe("正常文本"), "正常文本")

    def test_multi_role_and_source_manifest(self) -> None:
        self.assertTrue(pipeline.jd_is_multi_role({"screening_mode": "multi_role", "roles": ["销售", "市场"]}))
        self.assertTrue(pipeline.jd_is_multi_role({"raw_jd": "这是单一岗位筛选，还是多个岗位一起分流：多个岗位"}))
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with (root / "_source_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["local_file", "source_type", "subject", "date", "original_attachment"])
                writer.writeheader()
                writer.writerow({"local_file": "a.pdf", "source_type": "email", "subject": "应聘销售", "date": "", "original_attachment": "a.pdf"})
            manifest = pipeline.load_source_manifest(root)
            self.assertEqual(manifest["a.pdf"]["subject"], "应聘销售")

    def test_multi_role_output_is_grouped_by_best_fit_role(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resumes = root / "resumes"
            output = root / "results"
            resumes.mkdir()
            (resumes / "candidate.txt").write_text("resume", encoding="utf-8")
            record = {
                "candidate_id": "C0001",
                "source_file": "candidate.txt",
                "extraction": {"name": "测试"},
                "screening": {"recommendation_level": "推荐", "best_fit_role": "销售"},
            }
            pipeline.copy_categorized([record], resumes, output)
            grouped = list((output / "按岗位" / "销售" / "推荐").glob("*.txt"))
            self.assertEqual(len(grouped), 1)

    @unittest.skipIf(pipeline.Workbook is None or pipeline.load_workbook is None, "openpyxl unavailable")
    def test_workbook_contains_feedback_guide_and_freeze(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "result.xlsx"
            summary = [{
                "Candidate ID": "C0001", "候选人姓名": "测试", "AI 初筛结果": "推荐",
                "人工初筛结果": "", "人工初筛判断依据": "", "匹配结论": "匹配",
            }]
            evidence = [{"Candidate ID": "C0001", "候选人姓名": "测试", "岗位相关证据": "证据"}]
            pipeline.write_xlsx(path, summary, evidence)
            wb = pipeline.load_workbook(path)
            self.assertEqual(wb.sheetnames, ["筛选总表", "使用说明", "详细证据表"])
            self.assertEqual(wb["筛选总表"].freeze_panes, "F2")
            self.assertIn("保存 Excel", wb["使用说明"]["A6"].value)
            self.assertTrue(wb["筛选总表"].data_validations.count)

    def test_candidate_index_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            resumes = root / "resumes"
            resumes.mkdir()
            (resumes / "a.txt").write_text("candidate", encoding="utf-8")
            pipeline.collect_files(resumes, root / "work")
            data = json.loads((root / "work" / "candidate_index.json").read_text(encoding="utf-8"))
            self.assertEqual(data["version"], pipeline.CANDIDATE_INDEX_VERSION)

    def test_email_manifest_formula_is_neutralized(self) -> None:
        self.assertEqual(email_downloader.csv_safe("=cmd"), "'=cmd")
        self.assertEqual(email_downloader.csv_safe("招聘简历"), "招聘简历")

    def test_email_link_only_notifications_are_detectable(self) -> None:
        message = MIMEMultipart("alternative")
        message.attach(MIMEText("请查阅 https://jobs.example.com/candidate/123", "plain", "utf-8"))
        message.attach(MIMEText('<a href="https://jobs.example.com/candidate/123">查阅并处理</a>', "html", "utf-8"))
        self.assertEqual(
            email_downloader.extract_http_links(message),
            ["https://jobs.example.com/candidate/123"],
        )

    def test_email_message_manifest_records_attachment_and_link_counts(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "messages.csv"
            row = {
                "mailbox": "INBOX", "sender": "jobs@example.com", "subject": "AI 实习生",
                "date": "", "message_id": "m1", "uid": "1",
                "matching_attachment_count": 0, "new_download_count": 0,
                "web_link_count": 1, "web_links": "https://jobs.example.com/1",
            }
            email_downloader.append_message_manifest(path, [row])
            with path.open(newline="", encoding="utf-8-sig") as handle:
                saved = list(csv.DictReader(handle))
            self.assertEqual(saved[0]["web_link_count"], "1")


if __name__ == "__main__":
    unittest.main()
