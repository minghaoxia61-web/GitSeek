# GitSeek Agent 评测协议(v0.2)

延续 GitSeek 检索评测的可复现口径:固定数据集、公开指标定义、失败分类必须带真实案例。

## 数据集

| 数据集 | 内容 | 用途 |
|---|---|---|
| B:自建 good-first-issue | 20 个已关闭的 Python 项目 issue,要求:描述完整、有修复 commit 作为 ground truth | 主评测集,直接对应"新手贡献"定位 |
| A:SWE-bench Lite 子集 | 30–50 个分层抽样实例 | 后续里程碑;必须使用官方 Docker 镜像与官方 fail-to-pass 判定,不自造环境 |

清单格式(`--manifest`,JSON 数组):

`test_command` 必填且不能全为空白；缺少时在创建任务和调用模型前拒绝整个清单。
命令只来自受信任的离线评测配置，通过 `fixer_runs.test_command` 持久化后传给 worker，
公开创建任务 API 不接受此执行配置。
`execution` 同样必填，绑定数据集版本、修复前 commit、环境与依赖锁文件身份，详见
[固定版本评测说明](execution-spec.md)。旧版无 execution 的清单需要补齐后才能运行。
自 2026-10-29 起，`execution.acceptance` 也必须提供，绑定评测方持有的测试包和修复前后验收命令，
详见[干净检出验收](clean-acceptance.md)。以下只展示基础结构，完整运行前还需补充该字段。

```json
[
  {
    "instance_id": "owner__repo-123",
    "repo": "owner/repo",
    "issue_number": 123,
    "gold_files": ["src/owner/repo/module.py"],
    "test_command": "python -m pytest tests/test_module.py -x",
    "execution": {
      "dataset_version": "good-first-issues-v1",
      "base_commit": "<完整小写commit SHA>",
      "environment": {
        "backend": "docker",
        "image": "<已准备的镜像>@sha256:<64位摘要>",
        "platform": "linux/amd64"
      },
      "dependency_lock": {
        "path": "requirements.lock",
        "sha256": "<64位文件摘要>"
      }
    }
  }
]
```

上面是结构模板，所有占位哈希必须替换成真实值。

## 指标定义

| 指标 | 定义 | 计算 |
|---|---|---|
| 定位命中率 Top-1/5/10 | locator 候选文件列表(去重保序)前 K 个中命中 gold patch 文件的比例 | `packages.agent_core.bench.topk_hit` |
| 补丁产出率 | 最终 `git diff` 非空且能解析出改动文件的比例 | `diff_files(diff)` |
| 工作区验证 | 模型 FINISH、diff 非空、当前工作区补丁检查通过、显式测试已执行且退出码为 0、未超时 | `verification` 证据；不等于独立验收 |
| 独立验收通过率（`e2e_success`） | 身份与工作区验证通过；修复前指定断言失败；补丁在另一个固定版本检出中应用；受保护测试完整；缺陷与回归测试均通过 | `acceptance_passed()` 与任务/补丁记录共同核对 |
| 成本/时效 | 模型与 embedding 调用估算、未知费用数、平均轮数 | 新版 billing 收据；未知值不填零，不把估算当账单 |

## 消融矩阵(同一子集)

1. 完整版 vs 纯 BM25(去掉向量通道)vs 纯向量(去掉关键词通道)
2. 完整版 vs 单轮(去掉反思重试,max_rounds=1)
3. DeepSeek 主力 vs Qwen3-coder 备选(模型维度)

## 失败分类 taxonomy

| 类别 | 判定 | 案例(待补) |
|---|---|---|
| localization_error | 候选 Top-10 未命中 gold 文件 | TODO |
| issue_comprehension_error | 命中文件但补丁改错方向 | TODO |
| patch_logic_error | FINISH 但测试失败 | TODO |
| test_environment_error | 测试命令本身无法运行 | TODO |
| token_budget_exhausted | 触达 token 硬预算 | TODO |
| round_limit_exhausted | 轮数耗尽未 FINISH | TODO |

## 复现

```bash
python -m packages.agent_core.bench --manifest data/bench-manifest.json --backend docker --config-id fixer-v1
# 产出:eval-results/fixer-v1-<时间戳>.json + agent_bench_results 逐条指标
```

## 诚实边界

- gold 文件级命中不等于补丁正确;端到端成功率必须以测试通过为准。
- 数据集 B 由单一策划者维护,存在确认偏差;发布数字时必须同时给出失败分类明细。
- 20% 成功率 + 严谨失败分析 > 40% 成功率 + 只报喜:基线本身就是贡献。

## 2026-10-28：A2/A3 验证口径与兼容性

- `FixerResult` 分别记录模型结束、补丁存在、补丁检查、测试执行、测试通过、退出码及超时。
- `verification.version = fixer-verification-v1`，`scope = workspace_tests`。
- 补丁检查当前采用 `git apply --reverse --check` 对当前工作区做 dry-run，证明捕获的 diff
  与当前工作区一致；尚不等于在干净基准版本中正向应用补丁并通过独立测试。
- 没有测试命令、空补丁、补丁检查失败、测试非零退出或超时均不能算工作区验证通过。
- 评测同时核对任务状态、配置命令、补丁记录及 verification 字段；旧版只有 `success=true`
  的记录不能直接计入新版通过率。模型提供的 summary 也不能覆盖失败原因。
- 报告明确包含 `verification_scope=workspace_tests` 和 `independent_acceptance=false`。
  以上是 A2/A3 阶段口径；A6/A7 已增加独立验收，新 benchmark 使用 `clean_checkout_tests` 和 `independent_acceptance=true`。
- 普通任务没有受信任测试配置时可继续产出补丁草稿；运行以未验证结果结束，页面显示待验证。
  为兼容既有状态机，数据库仍用 `failed` 搭配 `test_not_configured`，不引入新终态。
- 页面只对具备完整新版证据的结果显示“工作区测试通过”；历史成功记录显示“结果待验证”。

已有数据库使用新版 API/worker 前须运行 `python -m alembic upgrade head`，新增迁移为
`20261028_0010`，只增加可空 `test_command` 字段，不回填或改写历史成功记录。
本次迁移在临时 SQLite 数据库验证了升级、旧记录保留、回滚和再次升级；未对线上数据库执行。

后续迁移 `20261028_0011` 增加可空 `execution_spec`；实际 HEAD、运行环境与依赖身份通过后才会调用模型。
固定版本任务从指定提交建立任务隔离索引，运行结束再次核对 HEAD。评测清单、模型配置及执行身份随报告留存。

## 2026-10-29：A6/A7

独立验收先确认固定版本上的缺陷断言失败和基线回归通过，再开始模型调用。最终 diff 在另一份预先准备的
干净检出中正向应用，使用原始测试包执行缺陷与回归检查；受保护测试或配置改动直接拒绝验收。
失败、超时、错误标记、未知证据和不完整的 passed 标记均不算通过。
完整配置、记录字段、本地开发模式限制与模板见[干净检出验收](clean-acceptance.md)。

## 2026-10-29：A8 运行证据与费用

新增尝试级供应商账本，覆盖 Issue 增强、修复与可选 embedding；失败或缺少用量/单价时保留未知状态，
已知调用费用仅作为小计。旧配置中的零占位默认未知，真实零单价需要显式确认。
存在未知实例时整体平均费用为 `null`，并另报已知/未知实例数量，不能把缺失费用混成零。
详细配置、日志/补丁留存、数据库迁移和回滚限制见[运行证据说明](run-evidence.md)。
