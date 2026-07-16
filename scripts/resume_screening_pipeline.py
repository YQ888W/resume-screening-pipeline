#!/usr/bin/env python3
"""
Generic resume screening pipeline.

Inputs:
  - a resume directory containing PDF/DOCX/images
  - a JD file in Markdown, text, or JSON

Outputs:
  - cached JSON records
  - CSV summary/evidence tables
  - XLSX workbook when openpyxl is available
  - categorized resume folders
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover - optional runtime dependency
    fitz = None

try:
    from docx import Document
except Exception:  # pragma: no cover
    Document = None

try:
    from openpyxl import Workbook
    from openpyxl import load_workbook
    from openpyxl.comments import Comment
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except Exception:  # pragma: no cover
    Workbook = None
    load_workbook = None


RESUME_EXTS = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
LABELS = ["推荐", "备选", "不推荐", "需复核"]


def is_zhipu_model(model: str) -> bool:
    return model.startswith("glm-") or model.startswith("z-ai/")


def default_extract_model() -> str:
    return "glm-4.7-flash" if os.getenv("ZHIPUAI_API_KEY") else "z-ai/glm-4.7-flash"


def default_vision_model() -> str:
    return "glm-5v-turbo" if os.getenv("ZHIPUAI_API_KEY") else "z-ai/glm-5v-turbo"


def default_screen_model() -> str:
    return os.getenv("GPT_SCREENING_MODEL", "openai/gpt-4.1-mini")


EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", default_extract_model())
VISION_MODEL = os.getenv("VISION_MODEL", default_vision_model())
SCREEN_MODEL = os.getenv("SCREEN_MODEL", default_screen_model())


EXTRACT_SCHEMA = {
    "name": "",
    "phone": "",
    "email": "",
    "links": [],
    "current_location": "",
    "current_title_company": "",
    "highest_degree": "",
    "highest_degree_school": "",
    "highest_degree_major": "",
    "highest_degree_graduation_date": "",
    "all_education": [],
    "work_experience": [],
    "projects_or_research": [],
    "skills": [],
    "tools": [],
    "languages": [],
    "certifications": [],
    "quantified_achievements": [],
    "role_relevant_evidence": [],
    "potential_fit_signals": [],
    "risks_or_missing_info": [],
    "short_summary": "",
    "evidence_quality": "strong | medium | weak",
}


SCREEN_SCHEMA = {
    "recommendation_level": "推荐 | 备选 | 不推荐 | 需复核",
    "best_fit_summary": "",
    "one_line_recommendation_reason": "",
    "must_have_match": "",
    "nice_to_have_match": "",
    "core_related_experience": "",
    "main_risks_or_missing_info": "",
    "suggested_next_step": "",
    "file_rename_key_info_cn": "",
    "interview_questions": [],
}


FEEDBACK_COLUMNS = [
    "人工初筛结果",
    "人工初筛判断依据",
]


FEEDBACK_COLUMN_ALIASES = {
    "人工初筛结果": ["人工初筛结果", "人工反馈结果"],
    "人工初筛判断依据": ["人工初筛判断依据", "反馈说明"],
}


SYSTEM_EXTRACT = """You extract structured candidate facts from resumes.
Return only valid JSON. Do not invent names, schools, dates, locations, employers, or facts.
Use empty strings or empty arrays for unknown fields.
Keep evidence concise and tied to resume text. Preserve original names and emails exactly.
If the user likely works in Chinese, evidence can be bilingual: Chinese summary first, then English resume evidence.
"""


SYSTEM_SCORE = """You screen candidates against the provided job requirements.
Use only the structured extraction JSON and JD. Do not invent facts.
Classify each candidate into exactly one recommendation_level: 推荐, 备选, 不推荐, or 需复核.
推荐 requires clear evidence for the role's must-haves or a well-justified exception.
备选 means useful signals exist but there are gaps, weaker evidence, or non-critical mismatches.
不推荐 means weak relevance or a clear mismatch with must-haves/dealbreakers.
需复核 means the resume is unreadable, too ambiguous, or needs manual review before ranking.
If human feedback is provided, compare previous_screening with human_feedback yourself. Infer whether the previous model judgment was overestimated, underestimated, correct, or a possible false negative. Re-evaluate the candidate and explain changes, but do not invent resume facts. If feedback indicates the model was too strict or too loose, adjust the recommendation only when resume evidence supports it.
Be selective and evidence-based. Mention missing information as risk, not as fact.
Return only valid JSON matching the requested schema.
"""


@dataclass(frozen=True)
class ResumeFile:
    candidate_id: str
    path: Path
    relpath: str
    sha1: str


def load_dotenv(path: Path | None) -> None:
    if not path or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_files(resume_dir: Path) -> list[ResumeFile]:
    files = [p for p in resume_dir.rglob("*") if p.is_file() and p.suffix.lower() in RESUME_EXTS]
    files.sort(key=lambda p: (p.name.lower(), str(p.relative_to(resume_dir)).lower()))
    return [
        ResumeFile(f"C{i:03d}", p, str(p.relative_to(resume_dir)), sha1_file(p))
        for i, p in enumerate(files, 1)
    ]


def extract_pdf_text(path: Path) -> tuple[str, int]:
    if fitz is None:
        return "", 0
    doc = fitz.open(path)
    chunks = []
    for i, page in enumerate(doc):
        text = page.get_text("text") or ""
        if text.strip():
            chunks.append(f"\n--- Page {i + 1} ---\n{text}")
    page_count = doc.page_count
    doc.close()
    return "\n".join(chunks).strip(), page_count


def extract_docx_text(path: Path) -> str:
    if Document is None:
        return ""
    doc = Document(path)
    chunks = []
    for para in doc.paragraphs:
        if para.text.strip():
            chunks.append(para.text)
    for table in doc.tables:
        for row in table.rows:
            vals = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if vals:
                chunks.append(" | ".join(vals))
    return "\n".join(chunks).strip()


def image_to_data_url(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def pdf_pages_to_data_urls(path: Path, max_pages: int = 3) -> list[str]:
    if fitz is None:
        return []
    urls = []
    doc = fitz.open(path)
    for page in list(doc)[:max_pages]:
        pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        urls.append("data:image/png;base64," + base64.b64encode(pix.tobytes("png")).decode("ascii"))
    doc.close()
    return urls


def local_text_for_file(path: Path) -> dict[str, Any]:
    ext = path.suffix.lower()
    result: dict[str, Any] = {
        "text": "",
        "page_count": None,
        "needs_vision": False,
        "parse_status": "ok",
        "error": "",
    }
    try:
        if ext == ".pdf":
            text, pages = extract_pdf_text(path)
            result["text"] = text
            result["page_count"] = pages
            result["needs_vision"] = len(text.strip()) < 250
            if fitz is None:
                result["parse_status"] = "missing_pymupdf"
        elif ext == ".docx":
            text = extract_docx_text(path)
            result["text"] = text
            result["needs_vision"] = len(text.strip()) < 250
            if Document is None:
                result["parse_status"] = "missing_python_docx"
        elif ext == ".doc":
            result["parse_status"] = "unsupported_doc"
            result["needs_vision"] = False
        elif ext in {".jpg", ".jpeg", ".png"}:
            result["needs_vision"] = True
            result["parse_status"] = "image"
        else:
            result["parse_status"] = "unsupported"
    except Exception as e:
        result["parse_status"] = "local_parse_error"
        result["error"] = str(e)
        result["needs_vision"] = True
    return result


def api_base(model: str) -> str:
    if is_zhipu_model(model) and os.getenv("ZHIPUAI_API_KEY"):
        return os.getenv("ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    return os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")


def api_headers(model: str) -> dict[str, str]:
    key = os.getenv("ZHIPUAI_API_KEY") if is_zhipu_model(model) and os.getenv("ZHIPUAI_API_KEY") else os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(f"Missing API key for model {model}")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def chat_completion(model: str, messages: list[dict[str, Any]], max_tokens: int, temperature: float) -> str:
    url = api_base(model).rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err = ""
    for attempt in range(6):
        try:
            r = requests.post(url, headers=api_headers(model), json=payload, timeout=120)
            if r.status_code >= 400:
                last_err = f"{r.status_code}: {r.text[:600]}"
                time.sleep(8 + attempt * 8 if r.status_code == 429 else 2 + attempt * 3)
                continue
            data = r.json()
            content = data["choices"][0]["message"].get("content") or ""
            if not content.strip():
                raise RuntimeError(f"empty response: {str(data)[:500]}")
            return content
        except Exception as e:
            last_err = str(e)
            time.sleep(3 + attempt * 5)
    raise RuntimeError(last_err or "chat completion failed")


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def load_jd(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        data.setdefault("raw_jd", "")
        data["source_format"] = "json"
        data["source_path"] = str(path)
        return data
    return {
        "source_format": path.suffix.lower().lstrip(".") or "text",
        "source_path": str(path),
        "raw_jd": text,
    }


def vision_extract_text(path: Path) -> str:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": "Extract all readable resume text. Preserve names, contact details, dates, schools, employers, titles, tools, and bullet points. Return plain text only.",
        }
    ]
    if path.suffix.lower() == ".pdf":
        for url in pdf_pages_to_data_urls(path):
            content.append({"type": "image_url", "image_url": {"url": url}})
    else:
        content.append({"type": "image_url", "image_url": {"url": image_to_data_url(path)}})
    return chat_completion(VISION_MODEL, [{"role": "user", "content": content}], max_tokens=6000, temperature=0)


def extraction_prompt(resume: ResumeFile, text: str, parse_meta: dict[str, Any]) -> list[dict[str, Any]]:
    payload = {
        "candidate_id": resume.candidate_id,
        "source_file": resume.relpath,
        "filename_hint": resume.path.name,
        "schema": EXTRACT_SCHEMA,
        "instructions": [
            "Extract only facts supported by the resume text or filename.",
            "Do not let the source folder name determine fit.",
            "Use concise evidence; include original wording where helpful.",
        ],
        "parse_meta": {k: v for k, v in parse_meta.items() if k != "text"},
        "resume_text": text[:55000],
    }
    return [
        {"role": "system", "content": SYSTEM_EXTRACT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def score_prompt(record: dict[str, Any], jd: dict[str, Any]) -> list[dict[str, Any]]:
    payload = {
        "job_requirements": jd,
        "candidate_extraction": record.get("extraction") or {},
        "previous_screening": record.get("screening") or {},
        "human_feedback": record.get("human_feedback") or {},
        "schema": SCREEN_SCHEMA,
        "grading_rules": {
            "推荐": "Strong match; worth contacting or interviewing.",
            "备选": "Some relevant signals but not strong, or has meaningful gaps.",
            "不推荐": "Weak relevance or mismatched with must-haves/dealbreakers.",
            "需复核": "Unreadable, ambiguous, or needs manual review before ranking.",
        },
    }
    return [
        {"role": "system", "content": SYSTEM_SCORE},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def record_path(work_dir: Path, resume: ResumeFile) -> Path:
    return work_dir / "records" / f"{resume.candidate_id}.json"


def process_one(
    resume: ResumeFile,
    jd: dict[str, Any],
    work_dir: Path,
    force: bool = False,
    feedback_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    out_path = record_path(work_dir, resume)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not force:
        return json.loads(out_path.read_text(encoding="utf-8"))

    parse_meta = local_text_for_file(resume.path)
    text = parse_meta.get("text") or ""
    if parse_meta.get("needs_vision"):
        try:
            vtext = vision_extract_text(resume.path)
            if len(vtext.strip()) > len(text.strip()):
                text = vtext
                parse_meta["parse_status"] = "vision_text"
        except Exception as e:
            parse_meta["vision_error"] = str(e)

    record: dict[str, Any] = {
        "candidate_id": resume.candidate_id,
        "source_file": resume.relpath,
        "source_file_hash": resume.sha1,
        "local_parse": {k: v for k, v in parse_meta.items() if k != "text"},
        "text_chars": len(text),
    }
    if feedback_map and resume.candidate_id in feedback_map:
        record["human_feedback"] = feedback_map[resume.candidate_id]

    try:
        raw = chat_completion(EXTRACT_MODEL, extraction_prompt(resume, text, parse_meta), max_tokens=7000, temperature=0.05)
        record["extraction"] = parse_json_object(raw)
        record["extract_status"] = "ok"
    except Exception as e:
        record["extraction"] = {}
        record["extract_status"] = "extract_error"
        record["extract_error"] = str(e)
        if "raw" in locals():
            record["extract_raw_excerpt"] = raw[:1200]

    try:
        raw_score = chat_completion(SCREEN_MODEL, score_prompt(record, jd), max_tokens=2600, temperature=0.1)
        record["screening"] = parse_json_object(raw_score)
        record["screen_status"] = "ok"
    except Exception as e:
        record["screening"] = fallback_screening(record, str(e))
        record["screen_status"] = "screen_error"
        record["screen_error"] = str(e)

    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def fallback_screening(record: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "recommendation_level": "需复核",
        "best_fit_summary": "",
        "one_line_recommendation_reason": "模型评分失败，需要人工复核。",
        "must_have_match": "",
        "nice_to_have_match": "",
        "core_related_experience": "",
        "main_risks_or_missing_info": reason[:500],
        "suggested_next_step": "人工查看原始简历并重跑评分。",
        "file_rename_key_info_cn": "需复核",
        "interview_questions": [],
    }


def score_existing(
    resume: ResumeFile,
    jd: dict[str, Any],
    work_dir: Path,
    feedback_map: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    path = record_path(work_dir, resume)
    if not path.exists():
        return process_one(resume, jd, work_dir, force=False, feedback_map=feedback_map)
    record = json.loads(path.read_text(encoding="utf-8"))
    if feedback_map and resume.candidate_id in feedback_map:
        record["human_feedback"] = feedback_map[resume.candidate_id]
    try:
        raw_score = chat_completion(SCREEN_MODEL, score_prompt(record, jd), max_tokens=2600, temperature=0.1)
        record["screening"] = parse_json_object(raw_score)
        record["screen_status"] = "ok"
        record.pop("screen_error", None)
    except Exception as e:
        record["screening"] = fallback_screening(record, str(e))
        record["screen_status"] = "screen_error"
        record["screen_error"] = str(e)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def safe_text(value: Any, limit: int = 1200) -> str:
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append("; ".join(f"{k}: {v}" for k, v in item.items() if v))
            elif item:
                parts.append(str(item))
        return "\n".join(parts)[:limit]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)[:limit]
    return str(value or "")[:limit]


def education_summary(extraction: dict[str, Any]) -> str:
    parts = [
        extraction.get("highest_degree", ""),
        extraction.get("highest_degree_school", ""),
        extraction.get("highest_degree_major", ""),
        extraction.get("highest_degree_graduation_date", ""),
    ]
    return " / ".join(str(part).strip() for part in parts if str(part or "").strip())


def join_lines(*values: Any) -> str:
    parts = []
    for value in values:
        text = safe_text(value, 900).strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def safe_filename_part(value: Any, max_len: int = 42) -> str:
    s = str(value or "").strip()
    s = re.sub(r"[\n\r\t]+", " ", s)
    s = re.sub(r"[/:*?\"<>|]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ._")
    return (s[:max_len].rstrip() or "未知")


def feedback_is_active(feedback: dict[str, str]) -> bool:
    if not feedback:
        return False
    return any(str(feedback.get(k, "")).strip() for k in FEEDBACK_COLUMNS)


def get_feedback_value(row: dict[str, Any], canonical_col: str) -> str:
    for col in FEEDBACK_COLUMN_ALIASES.get(canonical_col, [canonical_col]):
        value = str(row.get(col) or "").strip()
        if value:
            return value
    return ""


def load_feedback_file(path: str) -> dict[str, dict[str, str]]:
    if not path:
        return {}
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"feedback file not found: {p}")
    if p.suffix.lower() == ".csv":
        with p.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    elif p.suffix.lower() in {".xlsx", ".xlsm"}:
        if load_workbook is None:
            raise RuntimeError("openpyxl is required to read Excel feedback files")
        wb = load_workbook(p, data_only=True)
        ws = wb["筛选总表"] if "筛选总表" in wb.sheetnames else wb.active
        headers = [str(c.value or "").strip() for c in ws[1]]
        rows = []
        for values in ws.iter_rows(min_row=2, values_only=True):
            rows.append({headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))})
    else:
        raise ValueError("feedback file must be .csv, .xlsx, or .xlsm")

    feedback: dict[str, dict[str, str]] = {}
    for row in rows:
        cid = str(row.get("Candidate ID") or row.get("candidate_id") or "").strip()
        if not cid:
            continue
        item = {col: get_feedback_value(row, col) for col in FEEDBACK_COLUMNS}
        if feedback_is_active(item):
            feedback[cid] = item
    return feedback


def all_records(work_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted((work_dir / "records").glob("C*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    records.sort(key=lambda r: r.get("candidate_id", ""))
    return records


def rows_from_records(records: list[dict[str, Any]], jd: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows = []
    evidence_rows = []
    for r in records:
        e = r.get("extraction") or {}
        s = r.get("screening") or {}
        base_row = {
            "Candidate ID": r.get("candidate_id", ""),
            "候选人姓名": e.get("name", ""),
            "AI 初筛结果": s.get("recommendation_level", ""),
            "人工初筛结果": get_feedback_value(r.get("human_feedback") or {}, "人工初筛结果"),
            "人工初筛判断依据": get_feedback_value(r.get("human_feedback") or {}, "人工初筛判断依据"),
            "匹配结论": join_lines(
                s.get("one_line_recommendation_reason", ""),
                s.get("must_have_match", ""),
                s.get("nice_to_have_match", ""),
            ),
            "目前（最近）公司和 title": e.get("current_title_company", ""),
            "过往经历概况": s.get("core_related_experience", ""),
            "需要注意的点": s.get("main_risks_or_missing_info", ""),
            "学历背景": education_summary(e),
            "邮箱": e.get("email", ""),
            "电话": e.get("phone", ""),
            "链接": safe_text(e.get("links"), 500),
            "原始文件名": r.get("source_file", ""),
            "解析状态": f"{r.get('extract_status', '')}/{r.get('screen_status', '')}",
        }
        summary_rows.append(base_row)
        evidence_rows.append({
            "Candidate ID": r.get("candidate_id", ""),
            "候选人姓名": e.get("name", ""),
            "工作经历": safe_text(e.get("work_experience")),
            "项目/研究": safe_text(e.get("projects_or_research")),
            "岗位相关证据": safe_text(e.get("role_relevant_evidence")),
            "潜在匹配信号": safe_text(e.get("potential_fit_signals")),
            "技能": safe_text(e.get("skills")),
            "工具": safe_text(e.get("tools")),
            "语言": safe_text(e.get("languages")),
            "量化成果": safe_text(e.get("quantified_achievements")),
            "证据质量": e.get("evidence_quality", ""),
            "建议面试问题": safe_text(s.get("interview_questions")),
            "原始文件名": r.get("source_file", ""),
        })
    return summary_rows, evidence_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(records: list[dict[str, Any]], work_dir: Path, output_dir: Path, jd: dict[str, Any] | None = None) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows, evidence_rows = rows_from_records(records, jd)
    write_csv(work_dir / "screening_summary.csv", summary_rows)
    write_csv(work_dir / "screening_evidence.csv", evidence_rows)
    write_csv(output_dir / "screening_summary.csv", summary_rows)
    write_csv(output_dir / "screening_evidence.csv", evidence_rows)
    (work_dir / "all_records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    if Workbook is not None and summary_rows:
        write_xlsx(output_dir / "resume_screening_results.xlsx", summary_rows, evidence_rows)


def write_xlsx(path: Path, summary_rows: list[dict[str, Any]], evidence_rows: list[dict[str, Any]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "筛选总表"
    add_sheet_rows(ws, summary_rows)
    ev = wb.create_sheet("详细证据表")
    add_sheet_rows(ev, evidence_rows)
    wb.save(path)


def add_sheet_rows(ws: Any, rows: list[dict[str, Any]]) -> None:
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    header_fill = PatternFill("solid", fgColor="17324D")
    feedback_header_fill = PatternFill("solid", fgColor="F4B183")
    feedback_cell_fill = PatternFill("solid", fgColor="FFF2CC")
    thin = Side(style="thin", color="C8D0D8")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    feedback_col_indexes = {idx for idx, header in enumerate(headers, 1) if header in FEEDBACK_COLUMNS}
    for idx, cell in enumerate(ws[1], 1):
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = feedback_header_fill if idx in feedback_col_indexes else header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        if cell.value == "人工初筛结果":
            cell.comment = Comment("抽检或不同意 AI 初筛结果时填写，例如：不该推荐、其实一般、被误杀、需要复核。认可只是可选确认项；无异议可留空。", "resume-screening-pipeline")
        elif cell.value == "人工初筛判断依据":
            cell.comment = Comment("这里写人工判断原因。模型重评时会对比 AI 初筛结果和这段反馈，自动判断是否高估、低估或误杀。", "resume-screening-pipeline")
    for row in ws.iter_rows(min_row=2):
        for idx, cell in enumerate(row, 1):
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = border
            if idx in feedback_col_indexes:
                cell.fill = feedback_cell_fill
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    if "人工初筛结果" in headers and ws.max_row >= 2:
        col = get_column_letter(headers.index("人工初筛结果") + 1)
        dv = DataValidation(
            type="list",
            formula1='"不该推荐,其实一般,被误杀,需要复核,认可"',
            allow_blank=True,
        )
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{ws.max_row}")
    for idx, header in enumerate(headers, 1):
        letter = get_column_letter(idx)
        width = min(max(len(str(header)) + 6, 12), 46)
        if header in FEEDBACK_COLUMNS:
            width = 24 if header == "人工初筛结果" else 44
        elif header == "学历背景":
            width = 32
        ws.column_dimensions[letter].width = width


def copy_categorized(records: list[dict[str, Any]], resume_dir: Path, output_dir: Path) -> None:
    for label in LABELS:
        folder = output_dir / label
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    for r in records:
        e = r.get("extraction") or {}
        s = r.get("screening") or {}
        label = s.get("recommendation_level") if s.get("recommendation_level") in LABELS else "需复核"
        src = resume_dir / r.get("source_file", "")
        if not src.exists():
            continue
        name = safe_filename_part(e.get("name") or src.stem, 36)
        school = safe_filename_part(e.get("highest_degree_school") or "学校不明", 32)
        info = safe_filename_part(s.get("file_rename_key_info_cn") or s.get("one_line_recommendation_reason") or label, 44)
        base = f"{r.get('candidate_id', 'CID')}_{name}_{school}_{info}"
        dest = output_dir / label / f"{base[:170]}{src.suffix}"
        n = 2
        while str(dest) in used or dest.exists():
            dest = output_dir / label / f"{base[:160]}_{n}{src.suffix}"
            n += 1
        used.add(str(dest))
        shutil.copy2(src, dest)


def run_inventory(args: argparse.Namespace) -> None:
    resume_dir = Path(args.resumes).expanduser().resolve()
    work_dir = Path(args.work).expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for rf in collect_files(resume_dir):
        meta = local_text_for_file(rf.path)
        rows.append({
            "candidate_id": rf.candidate_id,
            "relpath": rf.relpath,
            "ext": rf.path.suffix.lower(),
            "sha1": rf.sha1,
            "text_chars": len(meta.get("text") or ""),
            "page_count": meta.get("page_count"),
            "needs_vision": meta.get("needs_vision"),
            "parse_status": meta.get("parse_status"),
            "error": meta.get("error"),
        })
    write_csv(work_dir / "inventory.csv", rows)
    print(f"wrote {work_dir / 'inventory.csv'} ({len(rows)} files)")


def selected_files(args: argparse.Namespace) -> list[ResumeFile]:
    files = collect_files(Path(args.resumes).expanduser().resolve())
    if getattr(args, "ids", ""):
        wanted = {x.strip() for x in args.ids.split(",") if x.strip()}
        files = [f for f in files if f.candidate_id in wanted]
    if getattr(args, "limit", 0):
        files = files[: args.limit]
    return files


def run_batch(args: argparse.Namespace) -> None:
    load_dotenv(Path(args.env).expanduser().resolve() if args.env else None)
    resume_dir = Path(args.resumes).expanduser().resolve()
    work_dir = Path(args.work).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    jd = load_jd(Path(args.jd).expanduser().resolve())
    feedback_map = load_feedback_file(args.feedback_file)
    files = selected_files(args)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"processing {len(files)} resumes with {EXTRACT_MODEL} + {SCREEN_MODEL}")
    records = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_one, rf, jd, work_dir, args.force, feedback_map): rf for rf in files}
        for i, fut in enumerate(as_completed(futs), 1):
            rf = futs[fut]
            try:
                record = fut.result()
                records.append(record)
                print(f"[{i}/{len(files)}] {rf.candidate_id} {record.get('extract_status')} {record.get('screen_status')} {rf.relpath}", flush=True)
            except Exception as e:
                print(f"[{i}/{len(files)}] ERROR {rf.candidate_id} {rf.relpath}: {e}", flush=True)
    records = all_records(work_dir)
    write_outputs(records, work_dir, output_dir, jd)
    if not args.no_copy:
        copy_categorized(records, resume_dir, output_dir)


def run_retry_failures(args: argparse.Namespace) -> None:
    load_dotenv(Path(args.env).expanduser().resolve() if args.env else None)
    work_dir = Path(args.work).expanduser().resolve()
    jd = load_jd(Path(args.jd).expanduser().resolve())
    feedback_map = load_feedback_file(args.feedback_file)
    files_by_id = {f.candidate_id: f for f in collect_files(Path(args.resumes).expanduser().resolve())}
    failed_ids = []
    for record in all_records(work_dir):
        if record.get("extract_status") != "ok" or record.get("screen_status") != "ok":
            failed_ids.append(record["candidate_id"])
    files = [files_by_id[x] for x in failed_ids if x in files_by_id]
    print(f"retrying {len(files)} failures")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_one, rf, jd, work_dir, True, feedback_map): rf for rf in files}
        for i, fut in enumerate(as_completed(futs), 1):
            rf = futs[fut]
            record = fut.result()
            print(f"[{i}/{len(files)}] retry {rf.candidate_id} {record.get('extract_status')} {record.get('screen_status')}")
    run_finalize(args)


def run_score_only(args: argparse.Namespace) -> None:
    load_dotenv(Path(args.env).expanduser().resolve() if args.env else None)
    work_dir = Path(args.work).expanduser().resolve()
    jd = load_jd(Path(args.jd).expanduser().resolve())
    feedback_map = load_feedback_file(args.feedback_file)
    if feedback_map:
        print(f"loaded human feedback for {len(feedback_map)} candidates")
    files = selected_files(args)
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(score_existing, rf, jd, work_dir, feedback_map): rf for rf in files}
        for i, fut in enumerate(as_completed(futs), 1):
            rf = futs[fut]
            record = fut.result()
            print(f"[{i}/{len(files)}] rescored {rf.candidate_id} {record.get('screen_status')}")
    run_finalize(args)


def run_finalize(args: argparse.Namespace) -> None:
    resume_dir = Path(args.resumes).expanduser().resolve()
    work_dir = Path(args.work).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    jd = load_jd(Path(args.jd).expanduser().resolve()) if getattr(args, "jd", "") else None
    records = all_records(work_dir)
    if not records:
        raise RuntimeError(f"No records found under {work_dir / 'records'}")
    write_outputs(records, work_dir, output_dir, jd)
    if not getattr(args, "no_copy", False):
        copy_categorized(records, resume_dir, output_dir)
    counts = {label: 0 for label in LABELS}
    for record in records:
        label = (record.get("screening") or {}).get("recommendation_level")
        counts[label if label in counts else "需复核"] += 1
    print(f"finalized {len(records)} records")
    print(json.dumps(counts, ensure_ascii=False))


def add_common_io(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--resumes", required=True, help="Resume source directory")
    parser.add_argument("--work", required=True, help="Working directory for cache/records")


def add_run_io(parser: argparse.ArgumentParser) -> None:
    add_common_io(parser)
    parser.add_argument("--jd", required=True, help="Job requirements markdown/txt/json")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--env", default="", help="Optional .env file")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ids", default="", help="Comma-separated candidate IDs, e.g. C001,C002")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-copy", action="store_true")
    parser.add_argument("--feedback-file", default="", help="Edited screening_summary.csv or resume_screening_results.xlsx with human feedback columns")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch screen resumes against a JD.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_inv = sub.add_parser("inventory")
    add_common_io(p_inv)
    p_run = sub.add_parser("run")
    add_run_io(p_run)
    p_retry = sub.add_parser("retry-failures")
    add_run_io(p_retry)
    p_score = sub.add_parser("score-only")
    add_run_io(p_score)
    p_fin = sub.add_parser("finalize")
    add_common_io(p_fin)
    p_fin.add_argument("--output", required=True)
    p_fin.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()

    if args.cmd == "inventory":
        run_inventory(args)
    elif args.cmd == "run":
        run_batch(args)
    elif args.cmd == "retry-failures":
        run_retry_failures(args)
    elif args.cmd == "score-only":
        run_score_only(args)
    elif args.cmd == "finalize":
        run_finalize(args)
    else:  # pragma: no cover
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
