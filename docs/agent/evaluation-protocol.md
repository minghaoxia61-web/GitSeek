# GitSeek Agent 评测协议(v0.1)

延续 GitSeek 检索评测的可复现口径:固定数据集、公开指标定义、失败分类必须带真实案例。

## 数据集

| 数据集 | 内容 | 用途 |
|---|---|---|
| B:自建 good-first-issue | 20 个已关闭的 Python 项目 issue,要求:描述完整、有修复 commit 作为 ground truth | 主评测集,直接对应"新手贡献"定位 |
| A:SWE-bench Lite 子集 | 30–50 个分层抽样实例 | 后续里程碑;必须使用官方 Docker 镜像与官方 fail-to-pass 判定,不自造环境 |

清单格式(`--manifest`,JSON 数组):

```json
[
  {
    "instance_id": "owner__repo-123",
    "repo": "owner/repo",
    "issue_number": 123,
    "gold_files": ["src/owner/repo/module.py"],
    "test_command": "python -m pytest tests/test_module.py -x"
  }
]
```

## 指标定义

| 指标 | 定义 | 计算 |
|---|---|---|
| 定位命中率 Top-1/5/10 | locator 候选文件列表(去重保序)前 K 个中命中 gold patch 文件的比例 | `packages.agent_core.bench.topk_hit` |
| 补丁产出率 | 最终 `git diff` 非空且能解析出改动文件的比例 | `diff_files(diff)` |
| 端到端成功率 | FINISH 且测试命令退出码为 0(配置了 test_command 时) | `FixerResult.success` |
| 成本/时效 | $ per instance、平均轮数 | `fixer_runs.cost_usd / rounds` |

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
