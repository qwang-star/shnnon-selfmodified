# Shannon GAIA Agent Benchmark Design

Date: 2026-07-24

Revision: 2026-07-24, updated after technical review of the current GAIA
dataset, official scorer, and Shannon Gateway capabilities.

## 1. Background

Shannon currently has unit, integration, end-to-end, and memory performance
tests, but it does not have a reusable framework for measuring the end-to-end
quality of an agent workflow against an external benchmark.

The first benchmark integration will use the public GAIA validation data. GAIA
evaluates general AI assistants on questions that can require reasoning, web
research, file analysis, calculation, and tool use. This design intentionally
starts with a small, text-only subset of Level 1 so the evaluation pipeline can
be validated before attachment handling and harder tasks are added.

The current GAIA repository publishes Parquet metadata files. The harness must
pin dataset provenance and match the behavior of the official GAIA scorer rather
than defining a broader, locally convenient interpretation of answer
normalization.

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
12. Distinguish strict answer-format compliance from a diagnostic fallback.
13. Persist each attempt atomically and submit it with an idempotency key.
14. Capture Shannon's persistent events and Temporal timeline for diagnosis.
15. Support repeated attempts without changing the smoke-test default of one.

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
- Automatically infer an Agent root cause with an LLM.
- Require new trace events that Shannon does not currently emit.
- Treat a 5-20 case smoke run as evidence of a workflow improvement.

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
          compare.py
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
          metadata.parquet
          metadata.level1.parquet
  cache\
    huggingface\
  runs\
    <run_id>\
      manifest.json
      cases.jsonl
      summary.json
      report.md
      failed_cases.jsonl
      attempts\
        <case_id>\
          <attempt_id>.json
      traces\
        <attempt_id>.events.json
        <attempt_id>.timeline.json
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
- `partition`: `tune`, `regression`, or `holdout` when a partition manifest is
  used.
- `level`: GAIA difficulty level.
- `prompt`: the original question.
- `expected_answer`: public validation answer.
- `attachments`: empty in the MVP.
- `answer_type`: number, string, or list, derived from the reference answer
  using official scorer rules.
- `capability_labels`: optional human-maintained labels; empty until a reviewed
  capability annotation file exists.
- `metadata`: source fields not used by the runner.

### 7.2 RunConfig

`RunConfig` captures effective execution settings:

- Gateway base URL and authentication source.
- Dataset and output roots.
- Benchmark, split, level, text-only filter, limit, and seed.
- Repetition count and attempt selection policy.
- Trace storage mode: `full_local`, `redacted`, or `metadata_only`.
- Per-task timeout and polling interval.
- Concurrency.
- Resume behavior.
- Shannon task context and optional model or provider overrides.

Secrets are never serialized into `RunConfig` or reports.

### 7.3 AgentResult

`AgentResult` represents one Shannon execution:

- Benchmark case ID, attempt ID, and repetition index.
- Shannon task and workflow IDs.
- Terminal task status.
- Raw response.
- Strict answer, diagnostic fallback answer, and format-compliance flag.
- Model, provider, usage, and metadata returned by the Gateway.
- Submission, completion, and elapsed timestamps.
- Normalized error category and a sanitized error message.
- Paths to the captured persistent-event and Temporal-timeline artifacts.

### 7.4 ScoreResult

`ScoreResult` contains:

- Expected, strict, and diagnostic answers.
- Officially normalized comparison values.
- `strict_correct` as the primary correctness result.
- `diagnostic_correct` for debugging non-compliant output.
- `format_compliant`.
- Scorer name and version.
- A deterministic mismatch reason.

### 7.5 WorkflowTrace

`WorkflowTrace` is derived from APIs Shannon already exposes:

- Persistent app events from `GET /api/v1/tasks/{id}/events`, fetched with
  pagination.
- Deterministic Temporal history from
  `GET /api/v1/tasks/{id}/timeline?mode=full&include_payloads=false&persist=false`.

The harness preserves both raw responses and derives best-effort fields for the
selected workflow, agents, plan events, tool calls, tool outcomes, retries,
replanning signals, durations, and stopping conditions. Missing fields remain
explicitly unavailable. The MVP does not invent route or planner facts that are
not present in Shannon's event stream.

Trace collection is diagnostic and best-effort. Delayed persistent events or an
unavailable timeline add a trace warning and completeness flag; they do not
change the answer score or convert a completed Agent task into a failed case.

Trace completeness is recorded explicitly:

```json
{
  "events_available": true,
  "timeline_available": true,
  "events_complete": true,
  "timeline_complete": true,
  "tool_inputs": "not_applicable",
  "tool_outputs": "not_applicable",
  "trace_completeness_score": 1.0
}
```

`events_complete` requires successful pagination through the final event page
without a decode, ordering, or request error. `timeline_complete` requires a
successful full timeline response with a valid event list and stats object.
Tool input and output fields are `available`, `missing`, or `not_applicable`;
they are applicable only when a tool call is present.

`trace_completeness_score` is the number of satisfied applicable checks divided
by the number of applicable checks. The four event/timeline checks always
apply. Tool input and output checks enter the denominator only for attempts that
contain tool calls.

For aggregate reporting, capture success means at least one source is available,
complete means the score is `1.0`, partial means the score is greater than zero
and less than `1.0`, and missing means the score is zero.

### 7.6 RunManifest

`manifest.json` records:

- Run ID and timestamps.
- Shannon Git commit and dirty-worktree flag.
- Dataset repository, revision, config, format, schema, and data file hash.
- Official scorer commit, scorer identity, and local implementation hash.
- Effective non-secret configuration and its hash.
- Selected case IDs and seed.
- Repetition count and attempt IDs.
- Gateway base URL.
- Model and provider information observed during the run.
- Benchmark harness version.
- Hashes of relevant Shannon configuration, synthesis templates, skills, and
  dependency lock files.
- Runtime version, timezone, locale, and available container image digests.

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
  --repetitions 1 `
  --dataset-root E:\project\Shannon_selfmodified_test\datasets\gaia `
  --output-root E:\project\Shannon_selfmodified_test\runs `
  --base-url http://localhost:8080 `
  --resume
```

Additional commands:

- `shannon_bench doctor`: validate Python dependencies, dataset access, output
  permissions, Gateway health, and authentication without running cases.
- `shannon_bench list-cases`: print the cases selected by the current filters.
- `shannon_bench report`: rebuild all derived reports from atomic attempt
  records in an existing run directory.
- `shannon_bench compare`: compare baseline and candidate runs case by case,
  including correctness, latency, cost, configuration, and infrastructure
  differences.
- `shannon_bench holdout unlock`: explicitly generate per-case holdout
  diagnostics with an audit reason and acknowledgment.

CLI arguments override YAML configuration. Environment variables provide
credentials and machine-local defaults.

## 9. Dataset Acquisition

The GAIA loader supports three access paths behind one normalized schema:

1. `datasets.load_dataset` using the pinned `gaia-benchmark/GAIA` repository
   revision.
2. Current local `metadata.parquet` or `metadata.level1.parquet` files.
3. Legacy local `metadata.jsonl` files for previously downloaded snapshots.

Downloading requires a Hugging Face account, acceptance of any dataset access
conditions, and a read-scoped `HF_TOKEN`. The token is read from the process
environment or the external `.env`; it is never printed or written to a report.

The download target is always the external test directory. GAIA data is never
copied into the Shannon repository.

The loader validates required fields, normalizes Parquet and JSONL rows to
`BenchmarkCase`, and computes a SHA-256 hash of every source metadata file.
Dataset provenance includes:

```json
{
  "dataset_repo": "gaia-benchmark/GAIA",
  "dataset_revision": "<resolved-commit-sha>",
  "dataset_config": "2023_level1",
  "dataset_format": "parquet",
  "dataset_schema": ["task_id", "Question", "Level", "Final answer", "file_name", "file_path"]
}
```

The loader filters cases in this order:

1. Validation split.
2. Level 1.
3. Empty `file_name`.
4. Stable sort by `task_id`.
5. Seeded sample of the requested size.

The selected case IDs are written to the run manifest before execution starts.
For reproducible tuning, an optional versioned partition manifest assigns cases
to `tune`, `regression`, and `holdout`. The smoke configuration does not claim
that a random sample is representative. Partition creation and capability
stratification are part of the stable-baseline phase after the loader has been
validated.

### 9.1 Holdout Visibility Policy

The public validation holdout is a soft process control, not a claim that public
answers have become private. In holdout mode:

- The CLI never prints expected answers or per-case correctness.
- Attempt records omit expected answers, normalized reference values, and
  correctness fields.
- `failed_cases.jsonl` and per-case comparison reports are not generated.
- The default report contains aggregate metrics only.
- Raw Agent responses and traces remain local, but are not joined with reference
  answers.

Aggregate scoring occurs in memory. To inspect individual results, the operator
must run:

```powershell
python -m shannon_bench holdout unlock `
  --run-id <run_id> `
  --reason "<reason>" `
  --acknowledge-public-validation
```

Unlocking re-scores stored Agent answers against the external dataset, generates
the per-case artifacts, and writes an audit record containing the time and
reason. It cannot prevent someone from opening the public dataset directly, but
it prevents routine benchmark commands from leaking holdout answers and
failure identities.

## 10. Shannon Adapter

`ShannonTaskAdapter` is the only component that knows the Shannon HTTP API.

For each case it:

1. Creates a unique session ID containing the run ID, case ID, and repetition.
2. Creates a stable idempotency key in the form
   `gaia:<run_id>:<case_id>:<attempt_index>`.
3. Submits `query`, `session_id`, and configured context to
   `POST /api/v1/tasks` with the existing `Idempotency-Key` header.
4. Polls `GET /api/v1/tasks/{task_id}`.
5. Stops on a terminal status or timeout.
6. Fetches all pages from `GET /api/v1/tasks/{task_id}/events`.
7. Fetches the non-persisted full Temporal timeline.
8. Redacts and stores raw trace artifacts, then derives a best-effort
   `WorkflowTrace`.
9. Returns a normalized `AgentResult`.

Each case gets an isolated session so memory from one benchmark question cannot
affect another. The adapter does not retry a completed Shannon task. Shannon's
Gateway already caches successful responses for `Idempotency-Key`, so a
submission can be retried with the same key after a connection loss without
creating a second task. The harness records the key hash and cached-response
indicator, but not authentication headers.

The baseline uses Shannon's automatic routing. Forced strategies, model
overrides, and provider overrides can be configured for later comparison runs,
but they are not enabled by the default smoke configuration.

## 11. Prompt and Answer Extraction

The submitted query contains the original GAIA question followed by a concise
format instruction requiring the final line:

```text
FINAL ANSWER: <short answer>
```

The raw Shannon response is always preserved. Extraction produces two answers:

1. `strict_answer` uses the last valid `FINAL ANSWER:` occurrence,
   case-insensitively. If the marker is absent, the strict answer is null and
   `format_compliant` is false.
2. `diagnostic_answer` equals the strict answer when present. Otherwise it uses
   the last non-empty line as a debugging fallback.
3. Both extractors remove surrounding whitespace and one matching pair of
   quotes without changing the answer's internal representation.
4. If no diagnostic answer remains, classify the case as `empty_answer`.

`strict_correct` is the primary benchmark result. `diagnostic_correct` shows
whether the Agent likely knew the answer but failed the output protocol. The
extractor does not ask another model to rewrite or judge the answer.

## 12. GAIA Scoring

The local scorer is a behaviorally exact port of the official GAIA scorer at
commit `1349a17`. It does not add article removal, Unicode normalization, or
other generalized answer-processing rules.

It follows the official branches:

- Numeric ground truths remove `$`, `%`, and commas from the prediction before
  float comparison.
- String ground truths remove all whitespace, lowercase text, and remove ASCII
  punctuation.
- List ground truths split on commas or semicolons and require equal lengths.
- Numeric list elements use numeric normalization.
- String list elements remove whitespace and lowercase text without removing
  punctuation.

The manifest records official scorer commit `1349a17`, the local scorer source
hash, and a scorer contract version. Committed parity fixtures contain inputs
and expected Boolean outputs generated by the pinned official implementation.
The local implementation must match every fixture.

The primary metric is strict case accuracy. A result is correct only when the
strict answer exists and the pinned scorer considers it equal to the validation
answer. Diagnostic correctness is reported separately and never silently
improves the primary score.

Every result stores both raw and normalized values so scoring can be audited.

## 13. Execution and Resume Semantics

The runner creates the run directory and manifest before submitting tasks.

Before the HTTP request starts, the runner atomically publishes an attempt
journal entry in `submitting` state. A successful response updates it with the
task ID. A lost connection retries with the same idempotency key. Shannon keeps
idempotent responses for 24 hours; an unresolved submission older than that TTL
is not silently retried because doing so could create a duplicate billable task.
It is reported for explicit operator resolution.

After every terminal attempt:

1. The full Gateway response is written to `raw/<task_id>.json`.
2. Event and timeline artifacts are written under `traces/`.
3. The complete attempt record is written to
   `attempts/<case_id>/<attempt_id>.json.tmp`.
4. The file is flushed and synced to disk.
5. An atomic rename publishes `<attempt_id>.json`.

On resume, the runner verifies that benchmark, dataset hash, selected cases, and
effective configuration match the existing manifest. A mismatch fails fast
instead of mixing incomparable results. Published attempt files are the source
of truth; temporary or corrupt files are ignored and reported. Completed
`case_id + attempt_index` pairs are skipped.

`cases.jsonl`, `summary.json`, and `report.md` are deterministic derived
artifacts rebuilt from the atomic attempt files. They are not the resume
journal.

Initial concurrency defaults to one. A small configurable concurrency limit can
be introduced without changing data contracts, but the smoke baseline remains
sequential to simplify diagnosis and reduce provider rate-limit effects.

## 14. Error and Diagnosis Taxonomy

Execution failures use stable system categories:

- `dataset_error`
- `gateway_unavailable`
- `authentication_error`
- `submission_error`
- `poll_error`
- `provider_rate_limit`
- `tool_timeout`
- `task_failed`
- `task_cancelled`
- `task_timeout`
- `persistence_error`
- `empty_response`
- `answer_extraction_error`
- `scoring_error`

Incorrect completed cases may also carry manually reviewed Agent diagnosis:

- `wrong_route`
- `unnecessary_complex_route`
- `planning_missing`
- `planning_incomplete`
- `tool_not_called`
- `wrong_tool_selected`
- `tool_call_failed`
- `retrieval_miss`
- `wrong_source_selected`
- `navigation_failure`
- `evidence_extraction_error`
- `calculation_error`
- `reasoning_error`
- `context_overflow`
- `evidence_ignored`
- `synthesis_error`
- `format_error`
- `scorer_mismatch`
- `budget_exhausted`

The MVP stores system failures automatically and leaves Agent diagnosis
unassigned. A later `review` command will support `primary_root_cause`,
`secondary_causes`, and reviewer notes without using an LLM judge. Reports never
infer a root cause from the final answer alone.

## 15. Reports and Metrics

`summary.json` and `report.md` organize metrics in four layers.

Outcome metrics:

- Total, attempted, completed, correct, incorrect, and failed cases.
- Strict and diagnostic accuracy.
- Format-compliance rate.
- Completion and failure rates.
- Median and P95 end-to-end latency.
- Prompt, completion, and total tokens when provided.
- Total cost and cost per strict-correct answer when provided by Shannon.

The formal primary metric is attempt-weighted mean strict accuracy:

```text
mean_strict_accuracy =
  sum(strict_correct for every scheduled attempt)
  / (selected_cases * repetitions)
```

Failed, timed-out, empty, and non-compliant attempts contribute zero. This keeps
completion failures visible in the primary score.

Stability metrics when `repetitions > 1`:

- Per-repetition strict accuracy and standard deviation.
- Per-case answer consistency.
- At-least-one-correct and majority-vote accuracy.
- Route, tool-selection, and latency consistency when trace data is available.

Majority-vote accuracy is an auxiliary metric. A case is majority-correct only
when one normalized strict answer receives more than half of its scheduled
attempts and that answer is correct. At-least-one-correct and answer consistency
are diagnostic metrics. At-least-one-correct is never compared across runs with
different repetition counts because it increases mechanically with more
attempts.

Process metrics derived from available trace events:

- Workflow selection distribution.
- Agent and tool invocation counts.
- Tool success, failure, timeout, and retry counts.
- Planning, replanning, budget, and stopping signals.
- Per-event and per-workflow durations when timestamps are available.
- Trace capture success, complete, partial, and missing rates.
- Mean trace completeness score and missing tool input/output counts.

Breakdowns:

- Accuracy by answer type, workflow, tool, model, provider, latency bucket, and
  token bucket.
- Accuracy by capability after reviewed capability labels are introduced.
- Model and provider distribution.
- Failure category counts.
- Answer extraction method counts.

`failed_cases.jsonl` contains only failed and incorrect cases for focused reruns
and analysis.

`compare` supports two explicit pairing modes:

- Attempt-level comparison pairs identical case IDs and repetition indexes:
  baseline attempt 0 with candidate attempt 0, and so on. It requires equal
  repetition counts and is used for stability diagnosis.
- Case-level comparison aggregates each case with the strict-majority rule,
  then classifies it as improved, regressed, unchanged-correct, or
  unchanged-incorrect. This is the primary regression view.

Both modes report score, latency, cost, configuration, and infrastructure
deltas. `compare` rejects incompatible case selections or scorer versions.
Runs with different repetition counts may use aggregate mean summaries, but
cannot produce attempt-level pairs or compare at-least-one-correct.

## 16. Security and Data Handling

- `HF_TOKEN` and Shannon API credentials stay in the external `.env`.
- Reports never contain authorization headers or environment values.
- GAIA data and answers are not committed to Git.
- Error text is sanitized before it is written to summary files.
- The runner does not execute arbitrary benchmark-provided code.
- The MVP does not process attachments.

Trace storage is configurable:

- `full_local`: preserve URLs, queries, tool inputs, and tool outputs in the
  external test directory for diagnosis. This is the default for local
  development runs.
- `redacted`: remove configured secret and personal-data patterns while
  retaining tool names, domains, status, timing, and content hashes.
- `metadata_only`: retain event types, counts, timings, statuses, and hashes but
  omit content-bearing fields.

Regardless of storage mode:

- Shared Markdown, `cases.jsonl`, `failed_cases.jsonl`, and compare reports use
  redacted trace projections.
- The manifest stores only hashes and non-sensitive metadata.
- Full local traces remain under `Shannon_selfmodified_test`, are excluded from
  Git, and receive restrictive local filesystem permissions where supported.
- Authorization headers, API keys, cookies, and configured secret patterns are
  always removed, including in `full_local` mode.

## 17. Test Strategy

Unit tests cover:

- Parquet, JSONL, and `datasets.load_dataset` schema parity.
- GAIA field validation and deterministic filtering.
- Seeded case selection.
- Strict and diagnostic answer extraction.
- Exact parity with pinned official scorer fixtures for number, string, and
  list answers.
- HTTP status mapping with a mocked Gateway.
- Idempotent submission retry behavior.
- Timeout and polling behavior.
- Event pagination, timeline capture, and trace redaction.
- Trace completeness calculation, including tool-call applicability.
- Full-local, redacted, and metadata-only trace projections.
- Atomic case persistence and resume.
- Corrupt and abandoned temporary-file handling.
- Manifest mismatch rejection.
- Attempt-weighted primary score, strict-majority aggregation, and diagnostic
  stability metrics.
- Attempt-level and case-level baseline-candidate pairing.
- Holdout output suppression and explicit unlock behavior.
- JSONL, Markdown, and baseline-candidate comparison reports.

A contract smoke test uses a fake HTTP server and runs the entire CLI pipeline.
A live test against Shannon is opt-in and runs one configured case; it is not
part of default unit tests because it consumes provider tokens and requires
services.

## 18. Acceptance Criteria

The MVP is accepted when:

1. `doctor` detects missing data, credentials, and Gateway availability.
2. The loader supports current Parquet, legacy JSONL, and pinned Hugging Face
   dataset access with recorded provenance.
3. Local scorer results match the pinned official scorer for all parity
   fixtures.
4. A fixed 5-20 case Level 1 text-only smoke sample runs through
   `/api/v1/tasks`.
5. Each attempt has an isolated Shannon session and stable idempotency key.
6. Strict correctness, diagnostic correctness, and format compliance remain
   separate.
7. Every attempt is published through a synced temporary file and atomic rename.
8. An interrupted run resumes without resubmitting completed attempts or
   consuming corrupt temporary records.
9. Raw responses, persistent events, Temporal timelines, and deterministic
   scores are auditable per attempt.
10. The manifest records dataset, scorer, source, configuration, dependency,
    runtime, and available container provenance without secrets.
11. JSONL, JSON, Markdown, and comparable-run outputs are generated
    successfully.
12. Reports include outcome, stability, available process, and supported
    breakdown metrics.
13. The primary metric is attempt-weighted mean strict accuracy; majority vote
    remains auxiliary and at-least-one-correct remains diagnostic.
14. Compare supports validated attempt-level and strict-majority case-level
    pairing.
15. Every trace records explicit completeness fields and reports aggregate
    complete, partial, and missing rates.
16. Trace storage modes preserve local diagnostic value without leaking secrets
    into shared reports or manifests.
17. Holdout mode suppresses per-case references and correctness until an
    audited explicit unlock.
18. Unit and contract tests pass without requiring a live LLM provider.
19. No dataset, credential, trace, or generated run artifact is added to Git.

## 19. Follow-On Work

The work proceeds in stages so pipeline correctness is not confused with Agent
quality.

### 19.1 Stable Baseline

- Run the complete Level 1 text-only subset.
- Use three repetitions with fixed model and effective parameters.
- Create reviewed `tune`, `regression`, and hidden-result `holdout` partitions.
- Establish the first baseline and require explanations for stable-case
  regressions.

### 19.2 Diagnostic Evaluation

- Add reviewed capability labels.
- Add the interactive manual root-cause review command.
- Normalize additional route, planner, tool, retrieval, and synthesis signals
  when Shannon emits enough evidence.
- Run layered upper-bound experiments: automatic execution, forced workflow,
  forced workflow plus allowed tools, and supplied gold evidence.

These experiments estimate routing, planning/tool-selection, retrieval, and
reasoning/formatting losses without assuming the final score identifies a
specific component.

### 19.3 Broader Agent Coverage

- Add GAIA Level 2 text-only cases.
- Add GAIA attachments and then Level 3.
- Add a Shannon-owned routing benchmark with
  `question -> expected_workflow_type`.
- Add internal tasks for research, browser use, multi-agent collaboration,
  memory, failure recovery, and budget control.

### 19.4 Additional External Benchmarks

- Add BFCL and tau-bench adapters after delegated tool execution exists.
- Add SWE-bench through an isolated repository workspace adapter.
- Add a persistent evaluation API and desktop dashboard only if CLI usage
  demonstrates a clear need.

## 20. References

- GAIA dataset and current Parquet files:
  https://huggingface.co/datasets/gaia-benchmark/GAIA
- GAIA leaderboard submission contract:
  https://huggingface.co/spaces/gaia-benchmark/leaderboard
- Pinned official scorer (`1349a17`):
  https://huggingface.co/spaces/gaia-benchmark/leaderboard/blob/1349a17/scorer.py
- Shannon task submission, event, timeline, and idempotency contracts:
  `go/orchestrator/cmd/gateway/README.md`,
  `docs/task-history-and-timeline.md`, and `docs/event-types.md`.
