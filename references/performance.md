# 性能和速度

最快且可靠的方式不是“把所有简历一次性发给 GLM”，而是“每位候选人一个独立记录，并发处理，可缓存续跑”。

## 为什么不要一个巨大 prompt

- 上下文限制：几百份简历容易超过模型上下文，或被迫截断。
- JSON 稳定性：一个超大 JSON 输出更容易格式坏掉。
- 失败恢复：一个附件坏了，整批调用可能失败。
- 审计困难：不如每人一个记录清楚。
- 成本控制：缓存能避免重复处理已完成候选人。

## 推荐速度模式

### 小样本试跑

第一次跑或 JD 不清楚时：

```bash
python3 scripts/resume_screening_pipeline.py run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --limit 5 \
  --workers 1
```

### 正常模式

pilot 口径确认后：

```bash
python3 scripts/resume_screening_pipeline.py run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 2
```

### 快速模式

供应商稳定、限流少时：

```bash
python3 scripts/resume_screening_pipeline.py run \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 4
```

只有在确认 429 / 限流错误很少时，才尝试 `--workers 6` 或 `--workers 8`。扫描件多、图片 PDF 多、网络不稳时，降低并发反而更快，因为失败更少。

## 失败重试

全量后跑：

```bash
python3 scripts/resume_screening_pipeline.py retry-failures \
  --resumes ./resumes \
  --jd ./job_requirements.md \
  --work ./work \
  --output ./results \
  --workers 1
```

重试阶段用低并发，让问题文件更稳定。

## 时间预期

不要承诺固定耗时。可以告诉用户：

- 5 份 pilot 通常很快。
- 50 份适合普通并发模式。
- 200-300 份建议预留较长时间，可以中断续跑。
- 影响速度的主要因素是模型响应、扫描件比例、简历页数、网络、并发和限流。

## 未来 Batch API

如果供应商提供官方批处理/离线 API，可以作为后端扩展。但输出契约仍应保持“一位候选人一个 JSON 记录”，不要退化成一个不可审计的大结果文件。
