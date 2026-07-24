# Shannon GAIA Agent Benchmark Design

Date: 2026-07-24

## 1. Background

Shannon currently has unit, integration, end-to-end, and memory performance
tests, but it does not have a reusable framework for measuring the end-to-end
quality of an agent workflow against an external benchmark.

The first benchmark integration will use the public GAIA validation data. GAIA
evaluates general AI assistants on questions that can require reasoning, web
research, file analysis, calculation, and tool use. This design intentionally
starts with a small, text-only subset of Level 1 so the evaluation pipeline can
be validated before attachment handling and harder tasks are added.

The system under evaluation is the complete Shannon workflow exposed by
`POST /api/v1/tasks`, not an individual LLM provider.

## 2. Decision Summary

The benchmark implementation is split across two filesystem locations:

- Versioned benchmark source code, configuration, and unit tests live in the
  Shannon repository under `tests/benchmarks/`.
- Downloaded datasets, credentials, caches, logs, and generated reports live
  outside the repository under `E:\project\Shannon_selfmodified_test`.

This keeps benchmark behavior reviewable and reproducible without committing
restricted data, credentials, or large run artifacts.

The MVP is a Python CLI that runs a deterministic GAIA Level 1 text-only sample
against a running Shannon Gateway and produces JSONL, JSON, and Markdown
reports. It does not add a Gateway endpoint, database schema, desktop page, or
new Shannon workflow.

## 3. Goals

The MVP must:

1. Load GAIA validation cases from an external dataset directory.
2. Select a deterministic Level 1 text-only sample.
3. submit every case through Shannon's native task API.
4. Poll task status until completion, failure, or timeout.
5. Preserve the complete Shannon response and execution metadata.
6. Extract a short final answer using deterministic rules.
7. Score the answer with GAIA-compatible normalization and exact matching.
8. Persist every completed case immediately.
9. Resume an interrupted run without repeating completed cases.
10. Generate machine-readable and human-readable summaries.
11. Record enough provenance to reproduce and compare runs.

## 4. Non-Goals

The MVP will not:

- Run GAIA Level 2 or Level 3.
- Run GAIA cases with file attachments.
- Submit results to the public GAIA leaderboard.
- Evaluate an underlying model through `/v1/chat/completions`.
- Add BFCL, tau-bench, WebArena, SWE-bench, or lm-eval adapters.
- Add OpenAI-compatible tool-calling fields to the Gateway.
- Add evaluation tables to PostgreSQL.
- Add a benchmark API or desktop UI.
- Change Shannon's routing, memory, tool selection, or agent workflows.
- Use an LLM judge for answer scoring.

## 5. Considered Architectures

### 5.1 External-Only Harness

All benchmark code and data would live in
`E:\project\Shannon_selfmodified_test`.

This provides strong runtime isolation but makes benchmark behavior easy to
lose, difficult to review, and impossible to associate reliably with a Shannon
commit.

### 5.2 Versioned Harness with External Artifacts

Benchmark code lives in Shannon while data and run artifacts live in the
external test directory.

This is the selected design. It gives the evaluator normal source control,
tests, and CI coverage while keeping datasets and secrets out of the repository.

### 5.3 Evaluation Control Plane

The Gateway would expose evaluation endpoints backed by PostgreSQL and a
desktop dashboard.

This may be useful after the benchmark contracts stabilize, but it would make
the first integration span Go, Python, database migrations, and the desktop
application. It is not justified for the MVP.

## 6. Filesystem Layout

Versioned files:

```text
Shannon_selfmodified/
  tests/
    benchmarks/
      README.md
      pyproject.toml
      configs/
        gaia_level1_smoke.yaml
      shannon_bench/
        __init__.py
        __main__.py
        cli.py
        models.py
        runner.py
        adapters/
          __init__.py
          shannon_task.py
        benchmarks/
          __init__.py
          gaia.py
        scorers/
          __init__.py
          gaia.py
        reporters/
          __init__.py
          jsonl.py
          markdown.py
      unit/
        test_answer_extraction.py
        test_gaia_loader.py
        test_gaia_scorer.py
        test_resume.py
        test_reporters.py
        test_shannon_adapter.py
```

External runtime files:

```text
E:\project\Shannon_selfmodified_test\
  .env
  datasets\
    gaia\
      2023\
        validation\
          metadata.jsonl
  cache\
    huggingface\
  runs\
    <run_id>\
      manifest.json
      cases.jsonl
      summary.json
      report.md
      failed_cases.jsonl
      raw\
        <task_id>.json
```

The external directory will have a local `.gitignore` that excludes `.env`,
datasets, caches, and runs. It is a runtime workspace, not a second source
repository.

## 7. Core Data Contracts

### 7.1 BenchmarkCase

`BenchmarkCase` is the benchmark-neutral input contract:

- `case_id`: stable benchmark task identifier.
- `benchmark`: `gaia`.
- `split`: `validation`.
- `level`: GAIA difficulty level.
- `prompt`: the original question.
- `expected_answer`: public validation answer.
- `attachments`: empty in the MVP.
- `metadata`: source fields not used by the runner.

### 7.2 RunConfig

`RunConfig` captures effective execution settings:

- Gateway base URL and authentication source.
- Dataset and output roots.
- Benchmark, split, level, text-only filter, limit, and seed.
- Per-task timeout and polling interval.
- Concurrency.
- Resume behavior.
- Shannon task context and optional model or provider overrides.

Secrets are never serialized into `RunConfig` or reports.

### 7.3 AgentResult

`AgentResult` represents one Shannon execution:

- Shannon task and workflow IDs.
- Terminal task status.
- Raw response.
- Extracted final answer and extraction method.
- Model, provider, usage, and metadata returned by the Gateway.
- Submission, completion, and elapsed timestamps.
- Normalized error category and a sanitized error message.

### 7.4 ScoreResult

`ScoreResult` contains:

- Expected and extracted answers.
- Normalized expected and predicted values.
- Boolean correctness.
- Scorer name and version.
- A deterministic mismatch reason.

### 7.5 RunManifest

`manifest.json` records:

- Run ID and timestamps.
- Shannon Git commit and dirty-worktree flag.
- Benchmark source and data file hash.
- Effective non-secret configuration and its hash.
- Selected case IDs and seed.
- Gateway base URL.
- Model and provider information observed during the run.
- Benchmark harness version.

## 8. CLI Contract

The primary command is:

```powershell
python -m shannon_bench run `
  --benchmark gaia `
  --split validation `
  --level 1 `
  --text-only `
  --limit 20 `
  --seed 42 `
  --dataset-root E:\project\Shannon_selfmodified_test\datasets\gaia `
  --output-root E:\project\Shannon_selfmodified_test\runs `
  --base-url http://localhost:8080 `
  --resume
```

Additional commands:

- `shannon_bench doctor`: validate Python dependencies, dataset access, output
  permissions, Gateway health, and authentication without running cases.
- `shannon_bench list-cases`: print the cases selected by the current filters.
- `shannon_bench report`: rebuild summaries from an existing `cases.jsonl`.

CLI arguments override YAML configuration. Environment variables provide
credentials and machine-local defaults.

## 9. Dataset Acquisition

The harness supports two data sources behind the same loader:

1. A local GAIA directory supplied with `--dataset-root`.
2. An explicit `download` command using `huggingface_hub`.

Downloading requires a Hugging Face account, acceptance of any dataset access
conditions, and a read-scoped `HF_TOKEN`. The token is read from the process
environment or the external `.env`; it is never printed or written to a report.

The download target is always the external test directory. GAIA data is never
copied into the Shannon repository.

The loader validates required fields and computes a SHA-256 hash of the source
metadata file. It filters cases in this order:

1. Validation split.
2. Level 1.
3. Empty `file_name`.
4. Stable sort by `task_id`.
5. Seeded sample of the requested size.

The selected case IDs are written to the run manifest before execution starts.

## 10. Shannon Adapter

`ShannonTaskAdapter` is the only component that knows the Shannon HTTP API.

For each case it:

1. Creates a unique session ID containing the run ID and case ID.
2. Submits `query`, `session_id`, and configured context to
   `POST /api/v1/tasks`.
3. Polls `GET /api/v1/tasks/{task_id}`.
4. Stops on a terminal status or timeout.
5. Returns a normalized `AgentResult`.

Each case gets an isolated session so memory from one benchmark question cannot
affect another. The adapter does not retry a completed Shannon task. Network
retries are limited to idempotent status requests; an uncertain submission is
recorded as a submission error unless the Gateway returns a task ID.

The baseline uses Shannon's automatic routing. Forced strategies, model
overrides, and provider overrides can be configured for later comparison runs,
but they are not enabled by the default smoke configuration.

## 11. Prompt and Answer Extraction

The submitted query contains the original GAIA question followed by a concise
format instruction requiring the final line:

```text
FINAL ANSWER: <short answer>
```

The raw Shannon response is always preserved. Extraction uses these rules:

1. Use the last non-empty `FINAL ANSWER:` occurrence, case-insensitively.
2. Remove surrounding whitespace and one matching pair of quotes.
3. If no marker exists, use the last non-empty line and record the fallback
   extraction method.
4. If no answer remains, classify the case as `empty_answer`.

The extractor does not ask another model to rewrite or judge the answer.

## 12. GAIA Scoring

The scorer is deterministic and covered by fixture tests derived from the
public GAIA scoring behavior.

It normalizes:

- Unicode and surrounding whitespace.
- Case for textual answers.
- Articles and punctuation where GAIA normalization permits.
- Numeric formatting without changing numeric value.
- Comma-separated lists by normalizing each element.

The primary metric is case accuracy. A result is correct only when the
normalized predicted answer matches the normalized validation answer according
to the GAIA answer type.

Every result stores both raw and normalized values so scoring can be audited.

## 13. Execution and Resume Semantics

The runner creates the run directory and manifest before submitting tasks.

After every terminal case:

1. The full Gateway response is written to `raw/<task_id>.json`.
2. One complete record is appended to `cases.jsonl`.
3. The file is flushed before the next case starts.

On resume, the runner verifies that benchmark, dataset hash, selected cases, and
effective configuration match the existing manifest. A mismatch fails fast
instead of mixing incomparable results. Completed case IDs are skipped.

Initial concurrency defaults to one. A small configurable concurrency limit can
be introduced without changing data contracts, but the smoke baseline remains
sequential to simplify diagnosis and reduce provider rate-limit effects.

## 14. Error Taxonomy

Every failed case uses one of these stable categories:

- `dataset_error`
- `gateway_unavailable`
- `authentication_error`
- `submission_error`
- `poll_error`
- `task_failed`
- `task_cancelled`
- `task_timeout`
- `empty_response`
- `answer_extraction_error`
- `scoring_error`

Reports group failures by category. Raw responses are retained when available,
while credentials and sensitive headers are redacted.

## 15. Reports and Metrics

`summary.json` and `report.md` include:

- Total, attempted, completed, correct, incorrect, and failed cases.
- Accuracy over the full selected set.
- Accuracy over successfully scored cases.
- Completion and failure rates.
- Median and P95 end-to-end latency.
- Prompt, completion, and total tokens when provided.
- Estimated cost when provided by Shannon.
- Model and provider distribution.
- Failure category counts.
- Answer extraction method counts.

`failed_cases.jsonl` contains only failed and incorrect cases for focused reruns
and analysis.

## 16. Security and Data Handling

- `HF_TOKEN` and Shannon API credentials stay in the external `.env`.
- Reports never contain authorization headers or environment values.
- GAIA data and answers are not committed to Git.
- Error text is sanitized before it is written to summary files.
- The runner does not execute arbitrary benchmark-provided code.
- The MVP does not process attachments.

## 17. Test Strategy

Unit tests cover:

- GAIA field validation and deterministic filtering.
- Seeded case selection.
- Final-answer extraction and fallback behavior.
- Text, numeric, and list normalization.
- Correct, incorrect, and malformed scoring cases.
- HTTP status mapping with a mocked Gateway.
- Timeout and polling behavior.
- Atomic case persistence and resume.
- Manifest mismatch rejection.
- JSONL and Markdown report generation.

A contract smoke test uses a fake HTTP server and runs the entire CLI pipeline.
A live test against Shannon is opt-in and runs one configured case; it is not
part of default unit tests because it consumes provider tokens and requires
services.

## 18. Acceptance Criteria

The MVP is accepted when:

1. `doctor` detects missing data, credentials, and Gateway availability.
2. A fixed 20-case Level 1 text-only sample runs through `/api/v1/tasks`.
3. Each case has an isolated Shannon session.
4. An interrupted run resumes without resubmitting completed cases.
5. Raw responses and deterministic scores are auditable per case.
6. JSONL, JSON, and Markdown outputs are generated successfully.
7. The report contains accuracy, completion, latency, token, cost, and failure
   metrics when the Gateway supplies the underlying fields.
8. Unit and contract tests pass without requiring a live LLM provider.
9. No dataset, credential, or generated run artifact is added to Git.

## 19. Follow-On Work

After the MVP establishes a reliable baseline, the same contracts can support:

1. Full GAIA Level 1 with attachments.
2. GAIA Level 2 and Level 3.
3. Strategy and model comparison runs.
4. Retrieval and memory ablation experiments.
5. BFCL and tau-bench adapters after delegated tool execution exists.
6. SWE-bench through an isolated repository workspace adapter.
7. A persistent evaluation API and desktop dashboard if CLI usage demonstrates
   a clear need.
