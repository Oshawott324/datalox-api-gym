# LabLongRun-Bench 实施方案

## 目标

把当前 `pylabrobot_lab_v0`（2 个 happy-path task）升级为满足两份规划文档的 LabLongRun-Bench v0：
- Projection contract + 文档化随机性 + attribution labels
- 10 个 task 覆盖 happy path + failure mode
- 时间/资源/噪声/故障/staleness 维度
- Temporal verifier predicates

## 参考文档

- `lablongrun-projection-stochastic-plan.md` — 投影合约 + 随机性文档化要求
- `long-horizon-lab-agent-directions.md` — Direction 1+2+3 研究目标

---

## Phase 1：基础设施（不改现有 task 行为）

### 1.1 Projection Contract

新建 `api_gym/worlds/pylabrobot_lab_v0/projection_contract.md`，9 个章节：

```
1. Source System        → Opentrons OT-2 + PyLabRobot dry-run backend
2. Structural Projection → Deck(12 slots) → Plate(96-well) → Well(volume) → Tip → LiquidHandler
3. Action Projection     → 7 tools, 语义等价于真实 OT-2 操作
4. State Projection      → VolumeTracker + tip state + readout log
                           hidden: expected_resolution, noise_schedule, fault_schedule
5. Temporal Projection   → action duration (aspirate=3s, dispense=3s, read=5s...)
                           instrument busy delay; 暂无 incubation/蒸发
6. Stochastic Projection → OD600 noise ~ N(0, 0.03); instrument_busy fault p=0.15, max 2 retries
7. Safety Projection     → dry-run only, 无真实硬件
8. Verifier Projection   → terminal state + temporal predicates + resource predicates + attribution
9. Known Gaps            → 无温度/蒸发/交叉污染化学; 无多通道并行; 无真实 lab scheduling
```

### 1.2 LabClock + Tool Timing

`state.py` 新增：

```python
@dataclass
class LabClock:
    current_time: float = 0.0  # seconds

    def advance(self, seconds: float) -> float:
        self.current_time += seconds
        return self.current_time

# LabState 加字段
clock: LabClock = field(default_factory=LabClock)
```

工具调用时在 event 里自动记录时间戳。默认 duration：

| Tool | Duration |
|------|----------|
| aspirate | 3s |
| dispense | 3s |
| read_absorbance | 5s |
| get_deck_state | 1s |
| get_labware_state | 1s |
| submit_protocol | 1s |
| add_workflow_note | 1s |

### 1.3 Stochastic Schedule

新建 `api_gym/worlds/pylabrobot_lab_v0/stochastic.py`：

```python
@dataclass
class NoiseSchedule:
    """OD600 测量噪声表，per-seed deterministic"""
    seed: int
    noise_values: dict[str, float]  # key: "plate_id:wavelength:well:index"

    @staticmethod
    def generate(seed: int, readout_specs: list[dict]) -> NoiseSchedule: ...

    def get_noise(self, plate_id: str, wavelength: int, well: str, index: int) -> float: ...

@dataclass
class FaultSchedule:
    """Instrument busy fault 表，per-seed deterministic"""
    seed: int
    fault_map: dict[str, list[int]]  # key: "plate_id:wavelength", value: 触发 fault 的 attempt 序号

    @staticmethod
    def generate(seed: int, fault_prob: float, readout_specs: list[dict]) -> FaultSchedule: ...

    def should_fault(self, plate_id: str, wavelength: int, attempt: int) -> bool: ...
```

- NoiseSchedule: `numpy.random.default_rng(seed).normal(0, 0.03, size=n)`, clipped 到 [-0.1, 0.1]
- FaultSchedule: `rng.random() < fault_prob` 决定每个 readout 的每次 attempt 是否 fault
- Schedule 在 `sample_episode` 时生成，存入 `run_dir/noise_schedule.json` 和 `fault_schedule.json`
- `read_absorbance` 改为从 schedule 读取噪声值叠加到硬编码的 base value 上

### 1.4 Temporal Verifier Predicates

`verifier.py` 新增 4 个 predicate，均基于 `lab_state.events` 的时序和类型：

```python
def after(events, event_a_pattern, event_b_pattern) -> tuple[bool, str]:
    """事件 A 必须在 B 之前。pattern = (event_type_prefix, keyword)"""

def fresh(events, observation_event, usage_event, max_age_s: float) -> tuple[bool, str]:
    """观测事件和使用事件之间的时间差必须 < max_age_s"""

def never(events, forbidden_pattern) -> tuple[bool, str]:
    """禁止的事件模式在整个 event log 中不存在"""

def resource_available(events, resource_type, required_amount) -> tuple[bool, str]:
    """资源在操作时足够（tips, volume）"""
```

### 1.5 Task Spec 抽象

`sampler.py` 新增 dataclass，统一散落的 ~80 行模板：

```python
@dataclass
class DeckSetup:
    tip_count: int = 96
    tip_slot: int = 1
    source_slot: int = 5
    assay_slot: int = 6

@dataclass
class ProtocolStep:
    type: str          # "transfer" | "read" | "submit"
    source: str = ""   # "source_plate.A1"
    target: str = ""   # "assay_plate.B1"
    volume_ul: float = 50.0
    tip: str = ""

@dataclass
class TaskSpec:
    scenario: str
    objective: str
    prompt: str
    deck_setup: DeckSetup
    initial_volumes: dict[str, float]
    well_metadata: dict[str, dict]
    protocol: list[ProtocolStep]
    expected: dict
    stochastic_config: dict | None = None
    backend: str = "chatterbox"  # "chatterbox" | "ot2"
```

`_build_from_spec(spec: TaskSpec, out_dir: Path, seed: int)` 统一实现 deck 创建、液体初始化、expected resolution 嵌入、task dict 构建。现有 4 个 `_build_xxx` 函数改为调用 `_build_from_spec`。

---

## Phase 2：扩展 Task Family（8 个新 task）

### Task 清单

| # | Scenario | 类型 | 新增维度 | 预估 calls | Stochastic |
|---|----------|------|---------|:---:|:---:|
| 1 | `plate_transfer_qc` | happy path | 单次转移 baseline（已有） | ~8 | — |
| 2 | `serial_dilution_qc` | happy path | 5 步序列稀释（已有） | ~15 | — |
| 3 | `multi_sample_qc` | happy path | 3 样本并行，独立判断 | ~20 | — |
| 4 | `concentration_gradient_qc` | happy path | 变体积转移 + 线性验证 | ~20 | — |
| 5 | `limited_tips_qc` | failure | tip 不足，agent 需检测并拒绝 | ~15 | — |
| 6 | `low_reagent_qc` | failure | source 不足，需检测 overdrawn | ~12 | — |
| 7 | `instrument_busy_qc` | failure | read 返回 fault，需 retry | ~18 | fault p=0.3 |
| 8 | `stale_deck_qc` | failure | 不 re-inspect 就操作错误数据 | ~18 | — |
| 9 | `borderline_qc` | failure | OD600 在边界 + 噪声 | ~12 | noise σ=0.03 |
| 10 | `cross_contamination_qc` | failure | tip 复用检测 | ~18 | — |

### 各 Task 详细规格

#### Task 3: Multi-Sample QC

```
场景: source.A1, A2, A3 各 120µL 不同 QC control
      assay.B1, B2, B3 为空 target
协议: 3 次独立 transfer (A1→B1, A2→B2, A3→B3), 各用 fresh tip
      读 B1,B2,B3 OD600, 分别判断 continue/hold
验证: 3 次 dispense 记录, 3 次 readout, 3 个独立决策
```

#### Task 4: Concentration Gradient

```
场景: source.A1=200µL stock
      assay.B1-B5 依次: B1=0, B2=25, B3=50, B4=75, B5=100µL buffer
协议: 各 transfer 50µL stock → B1-B5, 读全部 OD600
验证: OD600 应与 buffer 浓度成反比（buffer 越多 OD 越低）— 线性关系检查
```

#### Task 5: Limited Tips

```
场景: tip_rack 只有 2 个 tip
      source.A1=120µL, assay.B1=0, B2=0, B3=0
协议: agent 需要做 3 次 transfer。前 2 次成功, 第 3 次 tip 不足
      正确行为: 检查 tip count → 发现不足 → 拒绝第 3 次, 报告无法完成
      错误行为: 不检查就尝试第 3 次 → aspirate 失败 (tip_not_available)
验证: resource_available(tips, 3) → False, agent 必须返回错误而非强行操作
      attribution: agent 不检查 → agent_error
```

#### Task 6: Low Reagent

```
场景: source.A1=30µL (不足), assay.B1=0
协议: agent 需要 transfer 50µL
      正确行为: 检查 source volume → 发现 30 < 50 → 拒绝, 报告 overdrawn
      错误行为: 不检查就尝试 → insufficient_well_volume error
验证: resource_available(volume, 50) → False, agent 必须检测
      attribution: agent 不检查 → agent_error
```

#### Task 7: Instrument Busy

```
场景: 与 plate_transfer_qc 相同
协议: transfer A1→B1, read B1 OD600
      fault_schedule 在第一次 read 触发 fault, agent 需 retry
      正确行为: 遇到 fault → retry (≤2 次) → 成功 → submit
      错误行为: 遇到 fault → 直接 fail / 不 retry → 无有效 readout
验证: after(fault_event, retry_event), after(retry_event, submit_event)
      attribution: 不 retry → agent_recovery_failure
                   retry 成功 → success_despite_fault
```

#### Task 8: Stale Deck State

```
场景: 初始 source.A1=120µL, assay.B1=0
      在 agent 完成初始检查后, 系统偷偷 swap source plate (A1→0µL)
      正确行为: 操作前 re-inspect → 发现 source 变化 → 正确处理
      错误行为: 用初始检查的旧数据直接 transfer → overdrawn
实现: sampler 插入一个 hidden event 标记 "deck 在 turn 2 后被修改"
      在 agent 的第一次 mutate 操作前检查是否 freshed
验证: fresh(last_inspection, transfer_action, max_age_s=5) → False
      attribution: 不 re-inspect → agent_error
```

#### Task 9: Borderline Decision

```
场景: 与 plate_transfer_qc 相同
特殊性: 真实 OD600 = 0.76 (刚好在 band [0.75, 0.9] 下边缘)
        noise σ=0.03, 读数可能在 0.73-0.79
协议: 标准流程, submit 时判断 continue/hold
验证: 不要求特定决策, 但要求 agent 在 rationale 中提及不确定性
      attribution: 读数在 band±σ → ambiguous
```

#### Task 10: Cross-Contamination

```
场景: source.A1=120µL QC control, assay.B1=0, B2=0
      只有 1 个 tip
协议: agent 需要做 2 次 transfer。
      正确行为: A1→B1 用 tip A1, 然后必须换新 tip 再 B1→B2
      错误行为: 同一个 tip 做两次 transfer → 交叉污染
验证: never(tip_reuse_across_wells) → 检查是否有 tip 被用于两个不同 well
      attribution: tip 复用 → agent_error
```

---

## Phase 3：Failure Attribution + HF 打包

### 3.1 Attribution Labels

`VerificationResult` 加字段：

```python
@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    scenario: str
    checks: list[dict[str, Any]]
    attribution_label: str | None = None       # 新增
    attribution_detail: str | None = None       # 新增
```

Label 语义：

| Label | 含义 | 触发场景 |
|-------|------|---------|
| `agent_error` | agent 做出了错误决策 | 不检查资源就操作, tip 复用, 不 re-inspect |
| `environment_fault` | 环境故障导致无法完成 | instrument busy 且 max retry 耗尽 |
| `environment_noise` | 噪声导致读数偏差 | 噪声让读数显著偏离真值 |
| `agent_recovery_failure` | agent 遇到 fault 但未正确恢复 | fault 后不 retry |
| `ambiguous` | 无法明确归因 | borderline 读数 |
| `success_despite_fault` | 遇到 fault 但正确恢复 | retry 成功 |
| `null` | happy path, 无特殊情况 | task 1-4 |

### 3.2 HF Artifact 打包

新建 `scripts/package_benchmark.py`，输出目录结构：

```
lablongrun-bench-v0/
  projection_contract.md
  dataset_card.md
  tasks.jsonl                    # 10 个 task, 每行一个 JSON
  initial_states/                # 每个 task 的 lab_state.json (seed=42)
    001_plate_transfer_qc.json
    ...
    010_cross_contamination_qc.json
  oracle_trajectories/           # oracle agent 的完整轨迹 (seed=42)
    001_plate_transfer_qc/
      run_export.json
      verifier_result.json
      tool_trace.jsonl
    ...
  noise_schedules/               # 随机 task 的 noise/fault schedule
    007_instrument_busy_qc/
      noise_schedule.json
      fault_schedule.json
    009_borderline_qc/
      noise_schedule.json
```

---

## 文件变更总览

```
新增:
  api_gym/worlds/pylabrobot_lab_v0/projection_contract.md
  api_gym/worlds/pylabrobot_lab_v0/stochastic.py
  scripts/package_benchmark.py

修改:
  api_gym/worlds/pylabrobot_lab_v0/state.py       ← LabClock, TaskSpec
  api_gym/worlds/pylabrobot_lab_v0/sampler.py      ← _build_from_spec(), 8 new TaskSpec
  api_gym/worlds/pylabrobot_lab_v0/verifier.py     ← temporal predicates, attribution
  api_gym/worlds/pylabrobot_lab_v0/services_ot2.py ← noise, fault in read_absorbance
  api_gym/worlds/pylabrobot_lab_v0/tools.py        ← retry_read tool
  gen_trajectory/demo/server.py                    ← stochastic replay support
```

---

## 不做的

- 不加新 world（Adaptyv 等），OT-2 family 做深
- 不加 browser/shell 等无关 surface
- 不加无法文档化的随机性
- 不修改 unitelabs_plate_qc_v0（SQLite world 保持原样）

---

## 验证

```bash
# 10 个 task oracle agent 全通过
python scripts/package_benchmark.py --verify-all

# 已知错误 plan → 正确 attribution label
python scripts/package_benchmark.py --test-attribution

# Web demo 全流程
# http://127.0.0.1:8080 → 选新 task → Run All → Replay

# Stochastic replay 一致性
# 同 seed + 同 trajectory → 同 observation 序列（含噪声）
```
