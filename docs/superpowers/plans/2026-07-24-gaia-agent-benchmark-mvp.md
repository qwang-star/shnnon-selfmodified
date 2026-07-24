# GAIA Agent Benchmark MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Shannon 仓库中实现一个可恢复、可审计、与官方 GAIA scorer 行为一致的 Agent Benchmark MVP，并将数据、密钥和运行产物隔离到同级目录 `E:\project\Shannon_selfmodified_test`。

**Architecture:** 在 `tests/benchmarks/` 建立独立 Python 包。纯函数层负责答案提取、GAIA 评分、指标和 Trace 投影；I/O 层负责数据加载、原子 Attempt 日志与报告；`ShannonTaskAdapter` 直接通过 `httpx` 调用 Gateway，以保留幂等响应头、事件 payload、分页和 timeline 参数；Runner 只编排这些边界，不直接解析 HTTP 或写文件。

**Tech Stack:** Python 3.11、标准库 `argparse/dataclasses/pathlib/json/hashlib`、`httpx`、`PyYAML`、`pyarrow`、可选 `datasets`、`pytest`、`pytest-asyncio`、`ruff`。

---

## 实施原则

- 所有功能先写失败测试，再写最小实现，再运行局部和全量测试。
- 默认测试不访问 Hugging Face、不启动 Shannon、不调用 LLM，也不消耗 Provider Token。
- `tests/benchmarks/fixtures/` 只保存人工构造的 scorer 和数据格式夹具，不保存任何 GAIA 题目或答案。
- `E:\project\Shannon_selfmodified_test` 保存真实数据、`.env`、run、raw response 和 trace，并在创建时写入本地 `.gitignore`。
- 不修改 `clients/python` SDK。Benchmark 需要读取 SDK 当前会丢弃的 event payload 和 `X-Idempotency-Cached`，因此使用独立 HTTP adapter。
- 每个任务完成后只提交本任务涉及的文件。不要暂存或提交用户已有的 `docs/Shannon_Gateway_Interface_Guide_CN.docx`。

## 文件职责图

| 路径 | 单一职责 |
|---|---|
| `shannon_bench/models.py` | 跨模块不可变数据契约、Enum、稳定 Attempt/Idempotency ID |
| `shannon_bench/config.py` | YAML、`.env`、环境变量和 CLI override 合并 |
| `shannon_bench/answers.py` | strict/diagnostic answer 提取 |
| `shannon_bench/scorers/gaia.py` | pinned GAIA scorer 的行为等价实现 |
| `shannon_bench/benchmarks/gaia.py` | Parquet、JSONL、HF Dataset 加载和确定性选样 |
| `shannon_bench/persistence.py` | 原子 JSON 发布、Attempt 扫描、resume compatibility |
| `shannon_bench/adapters/shannon_task.py` | Shannon Gateway HTTP、幂等提交和轮询 |
| `shannon_bench/trace.py` | events/timeline 捕获、完整性和脱敏投影 |
| `shannon_bench/trace_probe.py` | Router/Planner/Tool 可观测字段审计 |
| `shannon_bench/provenance.py` | Git、dataset、scorer、config、runtime hash |
| `shannon_bench/runner.py` | Case × repetition 生命周期编排 |
| `shannon_bench/metrics.py` | Outcome、stability、trace aggregate 纯函数 |
| `shannon_bench/reporters/` | 从 terminal Attempt 重建报告和 Compare |
| `shannon_bench/holdout.py` | Holdout 持久化投影和审计解锁 |
| `shannon_bench/cli.py` | argparse 命令、退出码和用户输出 |

## Task 1: 建立独立包并锁定官方 Scorer Parity

**优先级原因：** 这是正式指标的可信基础，必须先于 Runner 和报告实现。

**Files:**

- Create: `tests/benchmarks/pyproject.toml`
- Create: `tests/benchmarks/shannon_bench/__init__.py`
- Create: `tests/benchmarks/shannon_bench/scorers/__init__.py`
- Create: `tests/benchmarks/shannon_bench/scorers/gaia.py`
- Create: `tests/benchmarks/fixtures/gaia_scorer_parity.json`
- Create: `tests/benchmarks/unit/test_gaia_scorer.py`

- [ ] **Step 1: 创建包骨架和测试依赖**

`pyproject.toml` 固定以下入口和测试配置：

```toml
[project]
name = "shannon-bench"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "httpx>=0.26,<1",
  "PyYAML>=6,<7",
  "pyarrow>=16,<24",
]

[project.optional-dependencies]
hf = ["datasets>=3,<5"]
dev = [
  "pytest>=8,<10",
  "pytest-asyncio>=0.23,<2",
  "ruff>=0.6,<1",
]

[project.scripts]
shannon-bench = "shannon_bench.cli:main"

[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["shannon_bench*"]

[tool.pytest.ini_options]
testpaths = ["unit", "contract"]
asyncio_mode = "auto"
markers = ["live: requires a running Shannon Gateway and may consume provider tokens"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

安装开发环境：

```powershell
cd tests/benchmarks
python -m pip install -e ".[dev,hf]"
```

Expected: 安装成功，`python -c "import shannon_bench"` 返回 0。

- [ ] **Step 2: 写 scorer parity 失败测试**

Fixture 每条记录包含 `id`、`model_answer`、`ground_truth`、`expected`。至少覆盖：

```json
[
  {"id":"number_currency","model_answer":"$1,234.50","ground_truth":"1234.5","expected":true},
  {"id":"number_percent","model_answer":"50%","ground_truth":"50","expected":true},
  {"id":"number_invalid_suffix","model_answer":"1,000 USD","ground_truth":"1000","expected":false},
  {"id":"string_space_case_punct","model_answer":" New\nYork! ","ground_truth":"new york","expected":true},
  {"id":"string_no_unicode_fold","model_answer":"Café","ground_truth":"cafe","expected":false},
  {"id":"string_no_article_removal","model_answer":"the answer","ground_truth":"answer","expected":false},
  {"id":"none_prediction","model_answer":null,"ground_truth":"None","expected":true},
  {"id":"list_mixed_delimiters","model_answer":"Alpha; Beta","ground_truth":"alpha,beta","expected":true},
  {"id":"list_numeric","model_answer":"$1,000; 50%","ground_truth":"1000,50","expected":true},
  {"id":"list_preserves_punctuation","model_answer":"AB,C","ground_truth":"A.B,C","expected":false},
  {"id":"list_length","model_answer":"a,b,c","ground_truth":"a,b","expected":false},
  {"id":"list_order","model_answer":"b,a","ground_truth":"a,b","expected":false}
]
```

测试还必须断言：

```python
assert SCORER_NAME == "gaia_official_exact"
assert SCORER_VERSION == "1349a17"
```

Run:

```powershell
python -m pytest unit/test_gaia_scorer.py -q
```

Expected: FAIL，原因是 `shannon_bench.scorers.gaia` 尚未实现。

- [ ] **Step 3: 实现官方 scorer 的行为等价移植**

在 `gaia.py` 中实现：

```python
import re
import string
from typing import Literal

SCORER_NAME = "gaia_official_exact"
SCORER_VERSION = "1349a17"

def normalize_number_str(number_str: str) -> float:
    for char in ("$", "%", ","):
        number_str = number_str.replace(char, "")
    try:
        return float(number_str)
    except ValueError:
        return float("inf")

def split_string(value: str) -> list[str]:
    return re.split(r"[,;]", value)

def normalize_str(value: str, *, remove_punct: bool = True) -> str:
    normalized = re.sub(r"\s", "", value).lower()
    if not remove_punct:
        return normalized
    return normalized.translate(str.maketrans("", "", string.punctuation))

def classify_reference(ground_truth: str) -> Literal["number", "list", "string"]:
    try:
        float(ground_truth)
    except ValueError:
        return "list" if "," in ground_truth or ";" in ground_truth else "string"
    return "number"

def score_answer(model_answer: str | None, ground_truth: str) -> bool:
    answer = "None" if model_answer is None else model_answer
    answer_type = classify_reference(ground_truth)
    if answer_type == "number":
        return normalize_number_str(answer) == float(ground_truth)
    if answer_type == "string":
        return normalize_str(answer) == normalize_str(ground_truth)

    answer_elements = split_string(answer)
    truth_elements = split_string(ground_truth)
    if len(answer_elements) != len(truth_elements):
        return False
    comparisons: list[bool] = []
    for answer_element, truth_element in zip(answer_elements, truth_elements, strict=True):
        try:
            numeric_truth = float(truth_element)
        except ValueError:
            comparisons.append(
                normalize_str(answer_element, remove_punct=False)
                == normalize_str(truth_element, remove_punct=False)
            )
        else:
            comparisons.append(normalize_number_str(answer_element) == numeric_truth)
    return all(comparisons)

def normalized_comparison(
    model_answer: str | None, ground_truth: str
) -> tuple[object, object, str]:
    answer = "None" if model_answer is None else model_answer
    answer_type = classify_reference(ground_truth)
    if answer_type == "number":
        return normalize_number_str(answer), float(ground_truth), answer_type
    if answer_type == "string":
        return normalize_str(answer), normalize_str(ground_truth), answer_type
    normalized_answer: list[float | str] = []
    normalized_truth: list[float | str] = []
    for answer_element, truth_element in zip(
        split_string(answer), split_string(ground_truth), strict=False
    ):
        try:
            numeric_truth = float(truth_element)
        except ValueError:
            normalized_answer.append(normalize_str(answer_element, remove_punct=False))
            normalized_truth.append(normalize_str(truth_element, remove_punct=False))
        else:
            normalized_answer.append(normalize_number_str(answer_element))
            normalized_truth.append(numeric_truth)
    return normalized_answer, normalized_truth, answer_type
```

必须保留 pinned scorer 的三个非直觉行为：

- 只移除 ASCII `string.punctuation`，不做 Unicode folding。
- ground truth 含 `,` 或 `;` 时必走 list 分支。
- list 的字符串元素不移除标点。

`normalized_comparison` 只用于审计展示，`score_answer` 必须独立遵循官方判断路径，不能依赖更宽松的通用 normalizer。

- [ ] **Step 4: 运行 parity 和 lint**

```powershell
python -m pytest unit/test_gaia_scorer.py -q
python -m ruff check shannon_bench/scorers unit/test_gaia_scorer.py
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交 scorer 契约**

```powershell
git add tests/benchmarks/pyproject.toml tests/benchmarks/shannon_bench tests/benchmarks/fixtures/gaia_scorer_parity.json tests/benchmarks/unit/test_gaia_scorer.py
git commit -m "test: pin GAIA scorer parity contract"
```

## Task 2: 定义核心数据模型和答案提取

**Files:**

- Create: `tests/benchmarks/shannon_bench/models.py`
- Create: `tests/benchmarks/shannon_bench/answers.py`
- Create: `tests/benchmarks/unit/test_models.py`
- Create: `tests/benchmarks/unit/test_answer_extraction.py`

- [ ] **Step 1: 写模型验证失败测试**

用 frozen dataclass 和字符串 Enum 定义并测试：

- `BenchmarkCase`
- `RunConfig`
- `AttemptState`: `submitting | submitted | polling | terminal | ambiguous`
- `AgentResult`
- `ScoreResult`
- `TraceCompleteness`
- `WorkflowTrace`
- `RunManifest`

关键不变量测试：

```python
def test_attempt_identity_is_case_and_repetition():
    assert make_attempt_id("run-1", "case/1", 2) == make_attempt_id("run-1", "case/1", 2)
    assert make_attempt_id("run-1", "case/1", 2) != make_attempt_id("run-1", "case/1", 3)

def test_run_config_never_serializes_secrets(tmp_path):
    config = RunConfig(
        run_id="run-1",
        dataset_root=tmp_path / "datasets",
        output_root=tmp_path / "runs",
        base_url="http://localhost:8080",
        api_key="secret",
        hf_token="secret",
    )
    assert "secret" not in json.dumps(config.public_dict())
    assert "api_key" not in config.public_dict()
```

Run:

```powershell
python -m pytest unit/test_models.py -q
```

Expected: FAIL，模型尚不存在。

- [ ] **Step 2: 实现类型化模型和稳定 ID**

稳定标识：

```python
def make_attempt_id(run_id: str, case_id: str, repetition_index: int) -> str:
    material = f"{run_id}\0{case_id}\0{repetition_index}".encode()
    return hashlib.sha256(material).hexdigest()[:24]

def make_idempotency_key(run_id: str, case_id: str, repetition_index: int) -> str:
    safe_case = hashlib.sha256(case_id.encode()).hexdigest()[:16]
    return f"gaia:{run_id}:{safe_case}:{repetition_index}"
```

所有时间写为 UTC RFC3339 字符串；所有 JSON 输出通过模型自己的 `to_dict()` 生成，禁止 `default=str` 掩盖类型错误。

`RunConfig` 的完整字段在本任务固定为：

```python
@dataclass(frozen=True)
class RunConfig:
    run_id: str
    dataset_root: Path
    output_root: Path
    base_url: str
    benchmark: str = "gaia"
    split: str = "validation"
    level: int = 1
    text_only: bool = True
    limit: int = 20
    seed: int = 42
    repetitions: int = 1
    concurrency: int = 1
    task_timeout_seconds: float = 900.0
    poll_interval_seconds: float = 2.0
    resume: bool = True
    trace_storage_mode: TraceStorageMode = TraceStorageMode.FULL_LOCAL
    partition: str | None = None
    dataset_revision: str | None = None
    dataset_config: str = "2023_level1"
    api_key: str | None = field(default=None, repr=False)
    bearer_token: str | None = field(default=None, repr=False)
    hf_token: str | None = field(default=None, repr=False)
    task_context: Mapping[str, JsonValue] = field(default_factory=dict)
    model_tier: str | None = None
    model_override: str | None = None
    provider_override: str | None = None
    holdout: bool = False

    def public_dict(self) -> dict[str, JsonValue]:
        private = {"api_key", "bearer_token", "hf_token"}
        return {
            key: _json_value(value)
            for key, value in asdict(self).items()
            if key not in private
        }
```

`JsonValue`、`_json_value`、其他 dataclass 的字段名必须与设计文档第 7 节一致；`AttemptRecord` 额外包含 `state`、`idempotency_key_hash`、`task_id`、`updated_at` 和可选 terminal `agent_result/score_result/workflow_trace`。

- [ ] **Step 3: 写答案提取失败测试**

覆盖：

- 最后一个、大小写不敏感的 `FINAL ANSWER:` 生效。
- marker 缺失时 strict 为 `None`，diagnostic 为最后非空行。
- 去掉一对匹配的单/双引号。
- 不改动内部逗号、分号、大小写或单位。
- 空结果分类为 `empty_answer`。

核心断言：

```python
result = extract_answers("draft\nFINAL ANSWER: 3\nfinal answer: \"4\"")
assert result.strict_answer == "4"
assert result.diagnostic_answer == "4"
assert result.format_compliant is True
```

- [ ] **Step 4: 实现严格提取器并运行测试**

```powershell
python -m pytest unit/test_models.py unit/test_answer_extraction.py -q
python -m ruff check shannon_bench/models.py shannon_bench/answers.py unit/test_models.py unit/test_answer_extraction.py
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交模型和提取器**

```powershell
git add tests/benchmarks/shannon_bench/models.py tests/benchmarks/shannon_bench/answers.py tests/benchmarks/unit/test_models.py tests/benchmarks/unit/test_answer_extraction.py
git commit -m "feat: add benchmark contracts and answer extraction"
```

## Task 3: 实现 GAIA 数据加载和确定性选样

**Files:**

- Create: `tests/benchmarks/shannon_bench/benchmarks/__init__.py`
- Create: `tests/benchmarks/shannon_bench/benchmarks/gaia.py`
- Create: `tests/benchmarks/unit/test_gaia_loader.py`

- [ ] **Step 1: 用合成数据写失败测试**

测试在 `tmp_path` 动态创建相同内容的 Parquet 和 legacy JSONL，不提交真实 GAIA 内容。字段固定为：

```python
{
    "task_id": "case-003",
    "Question": "Synthetic question 3",
    "Level": "1",
    "Final answer": "3",
    "file_name": "",
    "file_path": ""
}
```

覆盖：

- Parquet 与 JSONL 归一化结果一致。
- 缺少 `task_id/Question/Level/Final answer` 时抛出带字段名的 `DatasetError`。
- 过滤顺序固定为 validation、level、text-only、`task_id` 排序、seed sampling。
- 同 seed 同 case IDs，不同输入行顺序不改变结果。
- 每个源文件记录 SHA-256、schema、format。
- `datasets.load_dataset` 通过注入的 loader callable 测试 repo、revision、config、split 参数，不访问网络。

Run:

```powershell
python -m pytest unit/test_gaia_loader.py -q
```

Expected: FAIL，loader 尚不存在。

- [ ] **Step 2: 实现三种加载路径**

公开入口固定为 `load_local_gaia(path: Path) -> LoadedDataset`、
`load_huggingface_gaia(repo, revision, config, split, cache_dir, token,
dataset_loader) -> LoadedDataset` 和
`select_cases(cases, level, text_only, limit, seed) -> list[BenchmarkCase]`。
`LoadedDataset` 是 frozen dataclass，字段为 `cases`、`repo`、`revision`、
`config`、`split`、`format`、`schema`、`source_hashes`。

HF revision 不能为空；若用户未提供 immutable commit SHA，loader 必须记录 `datasets` 返回的 resolved fingerprint/commit 信息并由 `doctor` 警告不可完全复现。

- [ ] **Step 3: 运行 loader 测试和 scorer 回归**

```powershell
python -m pytest unit/test_gaia_loader.py unit/test_gaia_scorer.py -q
```

Expected: 全部 PASS。

- [ ] **Step 4: 提交数据层**

```powershell
git add tests/benchmarks/shannon_bench/benchmarks tests/benchmarks/unit/test_gaia_loader.py
git commit -m "feat: add reproducible GAIA dataset loader"
```

## Task 4: 实现原子 Attempt Journal 和崩溃恢复

**优先级原因：** 在任何真实 Agent 调用前证明落盘和恢复语义，避免重复计费。

**Files:**

- Create: `tests/benchmarks/shannon_bench/persistence.py`
- Create: `tests/benchmarks/unit/test_atomic_persistence.py`
- Create: `tests/benchmarks/unit/test_resume.py`

- [ ] **Step 1: 写原子发布失败测试**

`AtomicAttemptStore` 的目标接口：

```python
store = AtomicAttemptStore(run_dir)
store.publish(record)
loaded = store.load_attempts()
```

测试必须断言：

- 文件写入 `{attempt_id}.json.tmp` 后执行 file flush 和 `os.fsync`。
- 最终发布使用同目录 `os.replace(tmp, final)`。
- Windows 和 POSIX 都保证目标文件只出现完整旧版本或完整新版本。
- POSIX 支持时额外 fsync parent directory；Windows 不把目录 fsync 不支持当成失败。
- orphan `.tmp`、非法 JSON、identity 不匹配的 JSON 不进入有效 Attempt 集合，并返回 recovery warning。

- [ ] **Step 2: 写真实子进程崩溃测试**

测试启动子进程调用私有测试钩子：

```python
store.publish(record, _before_replace=lambda: os._exit(91))
```

父进程断言：

```python
assert process.returncode == 91
assert store.load_attempts().attempts == []
assert store.load_attempts().warnings[0].kind == "orphan_temp"
```

然后正常重写同一 attempt，断言只有一个可解析 final 文件。

Run:

```powershell
python -m pytest unit/test_atomic_persistence.py -q
```

Expected: FAIL，store 尚未实现。

- [ ] **Step 3: 实现原子写和恢复扫描**

实现：

```python
def atomic_write_json(
    path: Path,
    value: Mapping[str, object],
    *,
    _before_replace: Callable[[], None] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    if _before_replace is not None:
        _before_replace()
    os.replace(temporary, path)
    if os.name != "nt":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
```

`AtomicAttemptStore.publish` 调用上述函数；`load_attempts` 只接收文件名与
JSON 内 `attempt_id` 一致的 `.json`，将 `.json.tmp` 记为 `orphan_temp`，
将 decode/identity 错误分别记为 `corrupt_json`/`identity_mismatch`；
`completed_keys` 只返回 `state == terminal` 的 `(case_id, repetition_index)`。
临时文件名固定为 `{attempt_id}.json.tmp`，不能使用跨目录临时文件。

- [ ] **Step 4: 写 resume 与 manifest mismatch 测试**

覆盖：

- terminal Attempt 被跳过。
- `submitting`/`submitted` 状态保留并进入恢复决策。
- 小于 24 小时的 `submitting` 使用原 idempotency key 恢复。
- 大于等于 24 小时且没有 task ID 的 Attempt 标为 `ambiguous`，禁止自动重提交。
- dataset hash、case IDs、scorer version、public config hash 任一变化都抛 `ManifestMismatchError`。
- `cases.jsonl` 等派生产物存在与否不影响 resume。

- [ ] **Step 5: 运行崩溃和恢复测试**

```powershell
python -m pytest unit/test_atomic_persistence.py unit/test_resume.py -q
```

Expected: 全部 PASS，包含子进程退出码 91 的测试。

- [ ] **Step 6: 提交持久化边界**

```powershell
git add tests/benchmarks/shannon_bench/persistence.py tests/benchmarks/unit/test_atomic_persistence.py tests/benchmarks/unit/test_resume.py
git commit -m "feat: add atomic attempt journal and recovery"
```

## Task 5: 实现 Shannon HTTP Adapter 和幂等提交状态机

**Files:**

- Create: `tests/benchmarks/shannon_bench/adapters/__init__.py`
- Create: `tests/benchmarks/shannon_bench/adapters/shannon_task.py`
- Create: `tests/benchmarks/unit/test_shannon_adapter.py`

- [ ] **Step 1: 用 `httpx.MockTransport` 写失败测试**

不引入 `respx`。构造可记录请求的 `MockTransport`，覆盖：

- POST body 包含 `query/session_id/context`。
- header 使用稳定 `Idempotency-Key`。
- `X-Workflow-ID`、`X-Session-ID`、`X-Idempotency-Cached` 被记录。
- 401 → `authentication_error`，429 → `provider_rate_limit`，5xx → `submission_error`。
- status 兼容 `COMPLETED` 和 `TASK_STATUS_COMPLETED` 前缀形式。
- timeout 由注入的 monotonic clock 和 sleep 驱动，不让单元测试真实等待。

- [ ] **Step 2: 写连接丢失后的幂等重试测试**

第一次 POST 在服务端“已接受”后模拟 `httpx.ReadError`，第二次返回相同 task：

```python
assert post_requests[0].headers["Idempotency-Key"] == stable_key
assert post_requests[1].headers["Idempotency-Key"] == stable_key
assert result.task_id == "task-1"
assert result.idempotency_cached is True
```

还要测试从 `submitting` journal 恢复时不生成新 key；从 `submitted` 恢复时直接轮询已有 task ID，不再 POST。

Run:

```powershell
python -m pytest unit/test_shannon_adapter.py -q
```

Expected: FAIL，adapter 尚不存在。

- [ ] **Step 3: 实现 adapter**

`ShannonTaskAdapter` 构造器参数固定为 `config`，以及 keyword-only 的
`client`、`clock=time.monotonic`、`sleep=asyncio.sleep`。公开异步方法固定为
`submit(attempt, prompt) -> SubmissionResult`、
`poll(task_id, deadline) -> Mapping[str, JsonValue]`、
`fetch_events(task_id) -> EventCapture`、
`fetch_timeline(task_id) -> TimelineCapture` 和 `aclose() -> None`。

认证优先级固定为 bearer token，其次 `X-API-Key`。任何日志或异常只包含 sanitized URL、status code 和截断后的错误摘要，不包含 header。

- [ ] **Step 4: 运行 adapter、persistence 联合回归**

```powershell
python -m pytest unit/test_shannon_adapter.py unit/test_atomic_persistence.py unit/test_resume.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交 HTTP 状态机**

```powershell
git add tests/benchmarks/shannon_bench/adapters tests/benchmarks/unit/test_shannon_adapter.py
git commit -m "feat: add idempotent Shannon task adapter"
```

## Task 6: 捕获 Trace、计算完整性并探测可观测能力

**优先级原因：** 这一结果决定后续只增强 Harness，还是必须给 Shannon 增加更细的 Router/Planner/Tool 事件。

**Files:**

- Create: `tests/benchmarks/shannon_bench/trace.py`
- Create: `tests/benchmarks/shannon_bench/trace_probe.py`
- Modify: `tests/benchmarks/shannon_bench/adapters/shannon_task.py`
- Create: `tests/benchmarks/unit/test_trace_capture.py`
- Create: `tests/benchmarks/unit/test_trace_projection.py`
- Create: `tests/benchmarks/unit/test_trace_probe.py`
- Create: `tests/benchmarks/live/test_live_trace_probe.py`

- [ ] **Step 1: 写 events 分页和 timeline 契约测试**

events 每页 `limit=200`、offset 依次为 `0, 200, 400`，直到 `count < limit`。测试：

- payload 原样保留。
- seq 非单调或请求/JSON 解码失败时 `events_complete=false`。
- timeline 请求必须精确带：

```text
mode=full&include_payloads=false&persist=false
```

- timeline 只有同时包含 list 类型 `events` 和 object 类型 `stats` 才算 complete。
- events 或 timeline 失败不能改变已完成 Agent 的答案分数。

- [ ] **Step 2: 写完整性公式测试**

固定断言：

```python
no_tools = TraceCompleteness(
    events_available=True,
    timeline_available=True,
    events_complete=True,
    timeline_complete=True,
    tool_inputs="not_applicable",
    tool_outputs="not_applicable",
)
assert no_tools.score == 1.0

missing_tool_payloads = replace(
    no_tools, tool_inputs="missing", tool_outputs="missing"
)
assert missing_tool_payloads.score == 4 / 6
assert missing_tool_payloads.category == "partial"
```

capture success 单独定义为任一 source available；category 只允许 `complete/partial/missing`。

- [ ] **Step 3: 写三种 Trace 存储投影测试**

输入必须包含 URL、query、tool input/output、Authorization、cookie、API key 和普通 metadata。断言：

- `full_local` 保留诊断内容，但永远删除认证 header、cookie、token 和 configured secrets。
- `redacted` 保留 tool name、domain、status、timing、content hash，移除 query/body/content。
- `metadata_only` 只保留 event type、计数、时序、状态、hash。
- shared projection 与 storage mode 无关，永远使用 redacted。

- [ ] **Step 4: 实现 Trace capture、projection 和 capability probe**

能力探测输出固定为：

```json
{
  "task_id": "task-1",
  "router": {
    "status": "observed",
    "sources": ["events:DELEGATION"],
    "fields": ["message", "payload.workflow"]
  },
  "planner": {
    "status": "partial",
    "sources": ["events:PROGRESS", "timeline:ACT_*"],
    "fields": ["message"],
    "missing": ["structured_plan", "planner_decision"]
  },
  "tools": {
    "status": "observed",
    "sources": ["events:TOOL_INVOKED", "events:TOOL_OBSERVATION"],
    "fields": ["tool_name", "input", "output"]
  }
}
```

`status` 只能是 `observed | partial | missing`。探测规则使用明确白名单：

- Router: `DELEGATION`、payload 中 `route/workflow/mode/strategy`。
- Planner: `PROGRESS`、`RESEARCH_PLAN_*`、agent ID 含 `planner`、timeline activity 名含 `plan`。
- Tool: `TOOL_INVOKED`、`TOOL_OBSERVATION`、timeline activity 名含 `tool`。

Probe 只报告“观察到什么”，不能从自然语言 final answer 推断 route 或 planner 决策。

- [ ] **Step 5: 添加 opt-in live test**

`live/test_live_trace_probe.py` 只在同时存在以下变量时运行：

```text
SHANNON_BENCH_LIVE=1
SHANNON_BASE_URL
SHANNON_TRACE_TASK_ID
SHANNON_API_KEY 或 SHANNON_BEARER_TOKEN
```

它读取一个已经完成的 task，不新建 LLM 任务，保存探测 JSON 到外部 run 目录，并断言 events/timeline 至少一个 source available。缺少变量时 `pytest.skip`。

- [ ] **Step 6: 运行 Trace 测试**

```powershell
python -m pytest unit/test_trace_capture.py unit/test_trace_projection.py unit/test_trace_probe.py -q
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交 Trace 能力**

```powershell
git add tests/benchmarks/shannon_bench/trace.py tests/benchmarks/shannon_bench/trace_probe.py tests/benchmarks/shannon_bench/adapters/shannon_task.py tests/benchmarks/unit/test_trace_capture.py tests/benchmarks/unit/test_trace_projection.py tests/benchmarks/unit/test_trace_probe.py tests/benchmarks/live/test_live_trace_probe.py
git commit -m "feat: capture and audit Shannon workflow traces"
```

## Task 7: 实现 Runner、Attempt 生命周期和 Manifest

**Files:**

- Create: `tests/benchmarks/shannon_bench/provenance.py`
- Create: `tests/benchmarks/shannon_bench/runner.py`
- Create: `tests/benchmarks/unit/test_manifest.py`
- Create: `tests/benchmarks/unit/test_runner.py`

- [ ] **Step 1: 写 manifest 失败测试**

Manifest 必须记录：

- Shannon commit 和 dirty flag。
- dataset repo/revision/config/format/schema/file hash。
- scorer name/version/source hash。
- public config hash、selected case IDs、repetitions、attempt IDs。
- Python/runtime/timezone/locale。
- requirements/lock/config/template/skill 文件 hash。
- 可用 container image digest。

断言 API key、bearer token、HF token、`.env` 内容不出现。Manifest 一旦存在，只允许补充 observed model/provider 和完成时间，不允许改变 identity 字段。

- [ ] **Step 2: 写 Runner 生命周期失败测试**

用 fake dataset、fake adapter、real `AtomicAttemptStore` 覆盖：

1. manifest 在第一次 POST 前发布。
2. `submitting` Attempt 在第一次 POST 前发布。
3. submission response 后立即把 task ID 写成 `submitted`。
4. poll terminal 后保存 raw、trace、score，再发布 `terminal`。
5. failed/timeout/noncompliant 都在主指标分母中且贡献 0。
6. 重启后 terminal 不提交；submitted 直接 poll；可恢复 submitting 使用同 key。
7. 每个 `case_id + repetition_index` 有独立 session：

```text
bench-run-20260724-a94a8fe5-r0
```

8. prompt 以原问题开头，以示例格式指令 `FINAL ANSWER: 4` 结束。

- [ ] **Step 3: 实现 provenance 和 Runner**

Runner 公开入口固定为
`run_benchmark(config, cases, adapter, store) -> RunOutcome`。它为
`case_id` 计算 8 位 SHA-256 hash，并据此生成不超过 Gateway ID 限制的 session ID。

MVP 默认 `concurrency=1`。如果配置大于 1，用 `asyncio.Semaphore` 限制，但 Attempt 身份、文件名和报告排序必须与调度完成顺序无关。

- [ ] **Step 4: 运行 Runner 回归**

```powershell
python -m pytest unit/test_manifest.py unit/test_runner.py unit/test_resume.py unit/test_shannon_adapter.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交执行编排**

```powershell
git add tests/benchmarks/shannon_bench/provenance.py tests/benchmarks/shannon_bench/runner.py tests/benchmarks/unit/test_manifest.py tests/benchmarks/unit/test_runner.py
git commit -m "feat: orchestrate resumable benchmark attempts"
```

## Task 8: 实现主指标、稳定性指标和两层 Compare

**Files:**

- Create: `tests/benchmarks/shannon_bench/metrics.py`
- Create: `tests/benchmarks/shannon_bench/reporters/__init__.py`
- Create: `tests/benchmarks/shannon_bench/reporters/jsonl.py`
- Create: `tests/benchmarks/shannon_bench/reporters/markdown.py`
- Create: `tests/benchmarks/shannon_bench/reporters/compare.py`
- Create: `tests/benchmarks/unit/test_metrics.py`
- Create: `tests/benchmarks/unit/test_reporters.py`
- Create: `tests/benchmarks/unit/test_compare.py`

- [ ] **Step 1: 写主指标和稳定性失败测试**

构造 2 cases × 3 repetitions，其中 strict 结果为：

```text
case-a: true, false, false
case-b: true, true, failed
```

必须得到：

- mean strict accuracy = `3 / 6`。
- case-a majority incorrect。
- case-b majority correct，因为正确 normalized answer 获得 2/3 scheduled attempts。
- at-least-one-correct = `2 / 2`，但标记为 diagnostic。
- failed Attempt 进入分母并贡献 0。
- consistency 根据 normalized strict answers 在 scheduled attempts 中的占比计算，缺失答案作为独立常量 `"__missing__"`。

- [ ] **Step 2: 写 Compare 失败测试**

Attempt-level：

- 只按 `(case_id, repetition_index)` 配对。
- repetitions 不等时拒绝。
- case selection、scorer version 不兼容时拒绝。

Case-level：

- 先对每个 run 独立做 strict-majority，再分类：
  `improved | regressed | unchanged_correct | unchanged_incorrect`。
- 正式回归摘要默认 case-level。
- repetitions 不同时允许 aggregate mean 摘要，但不输出 attempt pairs，也不比较 at-least-one-correct。

- [ ] **Step 3: 实现 deterministic reporters**

每次从 `attempts/**/{attempt_id}.json` 重建：

- `cases.jsonl`
- `summary.json`
- `report.md`
- `failed_cases.jsonl`
- compare JSON 和 Markdown

排序固定为 `case_id, repetition_index`；JSON `sort_keys=True`；共享输出只引用 redacted Trace projection。

报告必须含：

- Outcome、format、latency、token/cost。
- repetitions/stability。
- Trace capture success、complete/partial/missing、mean completeness。
- 可用的 route/planner/tool 统计。
- answer type、model、provider 和 failure breakdown。

- [ ] **Step 4: 运行指标和报告测试**

```powershell
python -m pytest unit/test_metrics.py unit/test_reporters.py unit/test_compare.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交报告层**

```powershell
git add tests/benchmarks/shannon_bench/metrics.py tests/benchmarks/shannon_bench/reporters tests/benchmarks/unit/test_metrics.py tests/benchmarks/unit/test_reporters.py tests/benchmarks/unit/test_compare.py
git commit -m "feat: report GAIA outcomes stability and comparisons"
```

## Task 9: 实现 Holdout 软隔离和显式解锁

**Files:**

- Create: `tests/benchmarks/shannon_bench/holdout.py`
- Create: `tests/benchmarks/unit/test_holdout.py`

- [ ] **Step 1: 写泄漏防护失败测试**

Holdout 默认输出必须同时满足：

- Attempt JSON 不含 `expected_answer`、normalized reference、`strict_correct`、`diagnostic_correct`。
- CLI stdout 不含 expected answer、case correctness 或 failed case IDs。
- 不生成 `failed_cases.jsonl` 和 per-case compare。
- `summary.json` 只含 aggregate score/count。

在测试中使用可识别 sentinel `DO_NOT_LEAK_EXPECTED_9f0c`，递归读取整个 run 目录并断言 sentinel 不存在。

- [ ] **Step 2: 写 unlock 审计测试**

缺少 `--reason` 或 `--acknowledge-public-validation` 时拒绝。成功后：

- 从外部 dataset 重新加载 references。
- 生成逐题 score 和 failed cases。
- 写 `holdout_unlocks.jsonl`，含 UTC time、reason、dataset hash、run ID。
- audit 不含标准答案。
- 同一次 CLI 执行使用原子写，失败不能留下半生成报告。

- [ ] **Step 3: 实现 Holdout projection 和 unlock**

不要把 expected answer 从 `BenchmarkCase` 永久删除；Runner 在内存中评分后，只对持久化模型应用 holdout projection。Unlock 必须重新校验 dataset hash，防止用不同快照解锁。

- [ ] **Step 4: 运行 Holdout 和 reporter 回归**

```powershell
python -m pytest unit/test_holdout.py unit/test_reporters.py -q
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交 Holdout 控制**

```powershell
git add tests/benchmarks/shannon_bench/holdout.py tests/benchmarks/unit/test_holdout.py
git commit -m "feat: protect and audit GAIA holdout results"
```

## Task 10: 实现配置、CLI、Doctor 和 Fake Gateway Contract

**Files:**

- Create: `tests/benchmarks/shannon_bench/config.py`
- Create: `tests/benchmarks/shannon_bench/cli.py`
- Create: `tests/benchmarks/shannon_bench/__main__.py`
- Create: `tests/benchmarks/configs/gaia_level1_smoke.yaml`
- Create: `tests/benchmarks/unit/test_config.py`
- Create: `tests/benchmarks/unit/test_doctor.py`
- Create: `tests/benchmarks/contract/test_cli_fake_gateway.py`

- [ ] **Step 1: 写配置优先级和 Secret 测试**

优先级固定：

```text
CLI > process environment/.env > YAML > defaults
```

`.env` 只从显式 `--env-file` 或默认外部根目录读取，不从仓库根目录自动搜索。测试 public config 和 error 输出均不含 secret。

Smoke YAML 默认值：

```yaml
benchmark: gaia
split: validation
level: 1
text_only: true
limit: 20
seed: 42
repetitions: 1
concurrency: 1
task_timeout_seconds: 900
poll_interval_seconds: 2
trace_storage_mode: full_local
dataset_root: E:\project\Shannon_selfmodified_test\datasets\gaia
output_root: E:\project\Shannon_selfmodified_test\runs
base_url: http://localhost:8080
resume: true
```

- [ ] **Step 2: 写 Doctor 失败测试**

`doctor` 分项返回 `ok/warn/error`：

- Python dependencies。
- dataset path/schema 或 HF credential。
- output root create/write/atomic replace。
- Gateway health/auth。
- scorer fixture parity。
- Git safety：外部根目录不位于 Shannon repo 内，且 `.gitignore` 覆盖 `.env/datasets/cache/runs`。

增加只读参数：

```powershell
$taskId = "task-00000000-0000-0000-0000-000000000002-1761545271"
python -m shannon_bench doctor --trace-task-id $taskId
```

它调用 Task 6 的 probe，打印 Router/Planner/Tool coverage，并保存 JSON，不提交新 Agent task。

- [ ] **Step 3: 写完整 CLI contract 测试**

使用标准库 `ThreadingHTTPServer` 模拟：

- POST `/api/v1/tasks`
- GET `/api/v1/tasks/task-1`
- 两页 GET `/events`
- GET `/timeline`
- health/auth 检查

运行真实 CLI subprocess：

```powershell
$configPath = Join-Path $TestDrive "smoke.yaml"
$runA = Join-Path $TestDrive "runs\baseline"
$runB = Join-Path $TestDrive "runs\candidate"
python -m shannon_bench run --config $configPath --run-id baseline
python -m shannon_bench report --run-dir $runA
python -m shannon_bench compare --baseline $runA --candidate $runB
python -m shannon_bench list-cases --config $configPath
python -m shannon_bench doctor --config $configPath
```

断言：

- POST 恰好一次，idempotency key 正确。
- CLI 退出码 `0`。
- attempt/raw/events/timeline/manifest/cases/summary/report 全部存在。
- 删除 derived reports 后执行 `report` 可完全重建且 hash 相同。
- 第二次 `run --resume` 不再 POST。

- [ ] **Step 4: 实现 CLI 子命令**

子命令固定为：

- `run`
- `doctor`
- `list-cases`
- `report`
- `compare`
- `holdout unlock`

`run` 必须接受 `--run-id`。省略时生成 UTC timestamp + 8 位随机 suffix；
`--resume` 时必须同时提供 `--run-id`，防止误把新 run 当成恢复。

使用 `argparse`；`main(argv: Sequence[str] | None = None) -> int` 返回稳定退出码：

```text
0 success
2 invalid config/CLI
3 dataset/doctor prerequisite failure
4 gateway/auth failure
5 run completed with execution failures
6 ambiguous resume requires operator action
```

- [ ] **Step 5: 运行 unit + contract**

```powershell
python -m pytest unit contract -q
python -m ruff check shannon_bench unit contract
```

Expected: 全部 PASS，且 fake Gateway 测试不访问外网。

- [ ] **Step 6: 提交 CLI**

```powershell
git add tests/benchmarks/shannon_bench/config.py tests/benchmarks/shannon_bench/cli.py tests/benchmarks/shannon_bench/__main__.py tests/benchmarks/configs tests/benchmarks/unit/test_config.py tests/benchmarks/unit/test_doctor.py tests/benchmarks/contract/test_cli_fake_gateway.py
git commit -m "feat: expose GAIA benchmark CLI and doctor"
```

## Task 11: 文档、外部 Workspace 初始化和 CI

**Files:**

- Create: `tests/benchmarks/README.md`
- Modify: `.github/workflows/ci.yml`
- Create outside Git: `E:\project\Shannon_selfmodified_test\.gitignore`
- Create outside Git: `E:\project\Shannon_selfmodified_test\.env.example`
- Create outside Git: `E:\project\Shannon_selfmodified_test\datasets\gaia\.gitkeep`
- Create outside Git: `E:\project\Shannon_selfmodified_test\runs\.gitkeep`
- Create outside Git: `E:\project\Shannon_selfmodified_test\cache\huggingface\.gitkeep`

- [ ] **Step 1: 写 README**

README 必须解释：

- GAIA 是什么、MVP 为什么只跑 Level 1 text-only。
- `HF_TOKEN` 是 Hugging Face 的 read-scoped access token，仅下载 gated dataset 时使用。
- Shannon 认证变量：`SHANNON_API_KEY` 或 `SHANNON_BEARER_TOKEN`。
- 安装、doctor、下载/本地数据、run、resume、report、compare、holdout unlock。
- `full_local/redacted/metadata_only` 的差异。
- 主指标和辅助/诊断指标定义。
- live trace probe 不会提交新任务，但需要已有 task ID。
- 真实 live run 可能产生模型费用。

- [ ] **Step 2: 创建外部 Workspace**

用 PowerShell 创建目录；`.gitignore` 内容固定为：

```gitignore
.env
datasets/
cache/
runs/
*.log
```

`.env.example` 只包含空值：

```dotenv
HF_TOKEN=
SHANNON_API_KEY=
SHANNON_BEARER_TOKEN=
SHANNON_BASE_URL=http://localhost:8080
```

确认外部目录不执行 `git init`，也不被 Shannon 的 `git status` 看到。

- [ ] **Step 3: 增加独立 CI job**

在 `.github/workflows/ci.yml` 新增 `benchmark-harness`：

```yaml
benchmark-harness:
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: tests/benchmarks
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
        cache: pip
        cache-dependency-path: tests/benchmarks/pyproject.toml
    - run: python -m pip install -e ".[dev]"
    - run: python -m pytest unit/test_gaia_scorer.py -q
    - run: python -m pytest unit contract -q
    - run: python -m ruff check shannon_bench unit contract
```

CI 不安装 HF extra、不下载数据、不读取 secret。

- [ ] **Step 4: 执行完整本地验证**

```powershell
cd E:\project\Shannon_selfmodified\tests\benchmarks
python -m pytest unit/test_gaia_scorer.py -q
python -m pytest unit contract -q
python -m ruff check shannon_bench unit contract
python -m shannon_bench doctor --config configs/gaia_level1_smoke.yaml
```

Expected:

- scorer parity 全部 PASS。
- unit/contract 全部 PASS。
- ruff PASS。
- doctor 对尚未配置的真实 dataset/token/Gateway 给出明确 error/warn，不泄漏 secret，不崩溃。

- [ ] **Step 5: 验证仓库没有运行产物**

```powershell
cd E:\project\Shannon_selfmodified
git status --short
git ls-files | rg "Shannon_selfmodified_test|tests/benchmarks/.+(parquet|jsonl|events.json|timeline.json|manifest.json|summary.json)"
```

Expected:

- `git status` 只出现本次源码/文档变更和用户原有 docx。
- `git ls-files` 不匹配 dataset、trace、run artifact；唯一允许的 JSONL 是人工 fixture 时需改为 `.json`。

- [ ] **Step 6: 提交文档和 CI**

```powershell
git add tests/benchmarks/README.md .github/workflows/ci.yml
git commit -m "ci: verify GAIA benchmark harness"
```

## Task 12: 用真实 Shannon 做一次只读 Trace 审计和最小 Smoke

**Files:**

- Generated outside Git: `E:\project\Shannon_selfmodified_test\runs\trace-probe-{timestamp}\trace_capabilities.json`
- Generated outside Git: `E:\project\Shannon_selfmodified_test\runs\{run_id}\`
- Modify only if evidence requires it: `docs/superpowers/specs/2026-07-24-gaia-agent-benchmark-design.md`

- [ ] **Step 1: 对已有 task 做只读 Trace probe**

在 Shannon Gateway 已运行且存在 completed task 后：

```powershell
$env:SHANNON_BENCH_LIVE="1"
$env:SHANNON_BASE_URL="http://localhost:8080"
$env:SHANNON_TRACE_TASK_ID="task-00000000-0000-0000-0000-000000000002-1761545271"
python -m pytest live/test_live_trace_probe.py -q -m live
python -m shannon_bench doctor --trace-task-id $env:SHANNON_TRACE_TASK_ID
```

Expected: 输出 Router、Planner、Tool 三类的 observed/partial/missing 和实际字段来源。

- [ ] **Step 2: 作出可观测性分支决策**

使用以下硬标准，不凭主观判断：

- Router 可用：至少有 route/workflow/mode 的结构化字段，或稳定的 `DELEGATION` 事件。
- Planner 可用：至少有 plan created/updated/replanned 的结构化事件和关联 agent/activity。
- Tool 可用：`TOOL_INVOKED` 能识别 tool name，`TOOL_OBSERVATION` 能与调用配对并判断 success/failure；输入输出缺失必须反映到 completeness。

若三类都满足，继续完善 Harness，不改 Shannon。

若某类只拿到自然语言 message 或完全 missing，先记录 gap；另起设计和 PR 为 Shannon 增加事件字段。不要在本 MVP 中临时从字符串猜测结构化事实。

- [ ] **Step 3: 运行 1-case 真实 smoke**

先确保 `doctor` 全绿，再执行：

```powershell
$runId = "gaia-smoke-" + (Get-Date -Format "yyyyMMdd-HHmmss")
python -m shannon_bench run `
  --config configs/gaia_level1_smoke.yaml `
  --run-id $runId `
  --limit 1 `
  --repetitions 1 `
  --resume
```

验证：

- 只创建一个 task。
- Attempt 从 submitting → submitted/polling → terminal。
- raw response、events、timeline、score 可相互追踪。
- 报告的主指标分母为 1。
- 使用同一个 `$runId` 再次运行不提交新 task。

- [ ] **Step 4: 运行 5-case MVP smoke**

```powershell
python -m shannon_bench run `
  --config configs/gaia_level1_smoke.yaml `
  --run-id ("gaia-smoke5-" + (Get-Date -Format "yyyyMMdd-HHmmss")) `
  --limit 5 `
  --repetitions 1 `
  --resume
```

Expected: 生成完整 JSONL、JSON、Markdown 报告。准确率高低不是本阶段验收门槛；可恢复性、审计性和 scorer correctness 才是。

- [ ] **Step 5: 最终验证并推送**

```powershell
cd E:\project\Shannon_selfmodified\tests\benchmarks
python -m pytest unit contract -q
python -m ruff check shannon_bench unit contract
cd E:\project\Shannon_selfmodified
git diff --check
git status --short
git log --oneline --max-count=15
git push origin main
```

Expected: 测试和 lint 全绿，工作树只保留用户原有的未提交 docx（若用户尚未处理），所有 Benchmark 源码提交均已推送到 `qwang-star/shnnon-selfmodified`。

## 最终验收映射

| Acceptance Criteria | 实现任务 |
|---|---|
| Doctor 检查数据、凭证、Gateway | Task 10 |
| Parquet/JSONL/HF loader 与 provenance | Task 3、7 |
| 官方 Scorer parity | Task 1 |
| 5-20 case `/api/v1/tasks` smoke | Task 10、12 |
| session 隔离与稳定 idempotency key | Task 5、7 |
| strict/diagnostic/format 分离 | Task 2、7 |
| fsync + atomic rename | Task 4 |
| crash resume 且不重复提交 | Task 4、5、7 |
| raw/events/timeline/score 可审计 | Task 6、7 |
| 完整无 secret Manifest | Task 7 |
| JSONL/JSON/Markdown/compare | Task 8、10 |
| 主指标与稳定性定义 | Task 8 |
| attempt-level/case-level compare | Task 8 |
| Trace 完整性和聚合率 | Task 6、8 |
| Trace 三种存储模式 | Task 6 |
| Holdout 默认隐藏与审计解锁 | Task 9、10 |
| 默认测试不依赖 live provider | Task 1-11 |
| Git 不包含数据、密钥和 run | Task 11 |
