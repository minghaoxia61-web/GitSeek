# GitSeek Agent 架构:从发现贡献机会到自动完成第一个 PR

> 状态:垂直切片(v0.1)已落地;SWE-bench 官方 harness 接入与 GitHub App(M4)为后续里程碑。
> 详细方案见仓库根目录《GitSeek-Agent 详细方案》。

## 定位

GitSeek 的贡献筛查 agent 回答"哪个 issue 值得做";GitSeek Agent(M1 定位器 + M2 修复循环)回答"怎么把它修完"。设计遵循 mini-SWE-agent 的极简主义:scaffold 手写、工具空间只有 4 个、不引入 LangChain,保证每一步 token 消耗和失败原因都可归因。

## 模块

```
apps/api/routes/fixer.py        POST /api/v1/fixer/runs · GET run · GET diff · GET stream(SSE)
workers/agent_runner/runner.py  队列消费:FOR UPDATE SKIP LOCKED 认领 → clone → 定位 → 修复 → 记录
packages/agent_core/
    issue_parser.py             确定性 issue 解析(栈轨迹/文件提示/标识符),可选 LLM 增强
    chunking.py                 tree-sitter 按函数/类切块(带行号回退)
    ingestion.py                git clone(浅克隆)+ 切块入库(FTS + 可选向量)
    execution.py                固定 commit、依赖文件和运行环境的身份规范与检查
    acceptance.py               基线缺陷复现、干净检出应用补丁、受保护测试验收
    evidence.py                 尝试级事件日志、原子收据、候选补丁与源码身份
    locator.py                  关键词(FTS)与向量双通道 → 复用 packages.ranking RRF 融合
    tools.py                    模型输出解析:```bash / ```diff / VIEW 行 / FINISH:
    fixer.py                    极简修复循环:≤max_rounds、token 硬预算、失败分类
    llm.py                      OpenAI 兼容 /chat/completions 客户端(DeepSeek 可用)
    bench.py                    评测 harness:清单驱动,产出 Top-K/端到端/成本指标
packages/sandbox/               local(仅开发)与 docker(默认断网、限额、降权)两种后端
```

## 数据模型(迁移 20260830_0009)

`fixer_runs`(状态机 queued→running→succeeded|failed,含 token/成本/失败分类)、`fixer_steps`(每个工具调用一条,支撑 SSE 时间线)、`fixer_patches`(每轮补丁与最终 diff)、`agent_code_chunks`(代码块索引,PostgreSQL 上带 tsvector 生成列 + GIN)、`agent_bench_results`(指标逐条落库)。 screening agent 已占用 `agent_runs`/`agent_steps`,故新表使用 `fixer_` 前缀。

迁移 `20261028_0010` 增加受信任的 `fixer_runs.test_command`，由评测清单写入，公开 API 不接受。
worker 将它传入 Agent，并在 `result_json.verification` 中分别持久化补丁与测试证据；
`fixer_patches.apply_ok/test_ok` 来自实际检查，不再从 diff 是否存在或总体 success 推断。
未配置独立验收时，`succeeded` 仅表示非空补丁通过当前工作区检查及配置测试，不表示干净环境独立验收完成。
从 A6/A7 起，配置了 `execution.acceptance` 的任务还必须通过独立检出验收才能进入 `succeeded`；
普通任务没有此规范时仍只代表工作区验证。API 使用独立的 `verification`、`acceptance` 字段表示两类证据。
缺少测试时保留补丁，使用 `failed + test_not_configured`，页面显示待验证。
详见[评测口径](evaluation-protocol.md)。

迁移 `20261028_0011` 增加 `execution_spec`，将评测清单的 commit、环境、依赖身份与任务绑定。
worker 显式 fetch/检出并核对 HEAD，在身份门槛通过后才构造模型客户端；固定版本任务使用本次检出的隔离索引。
执行结束再核对 HEAD，保存开始/结束/索引版本、实际环境、清单哈希与模型配置。
详见[执行身份与清单格式](execution-spec.md)。

迁移 `20261029_0012` 允许费用为空；`provider-billing-v1` 账本覆盖增强、修复和可选 embedding 调用。
未确认用量/价格不再算零，API/页面只使用新版账本估算。工具与供应商调用保留中间证据，
异常时保存部分用量和补丁；本地尝试目录不随工作区清理删除。详见[运行证据和费用状态](run-evidence.md)。

## 关键决策

| 决策 | 理由 |
|---|---|
| 不用 LangChain | 需要精确控制 token、重试与工具语义;mini-SWE-agent 证明百行级 scaffold 可行且可归因 |
| chat/completions 而非 /responses | DeepSeek 等 coding 模型的兼容面;修复循环不需要 schema 约束输出 |
| SSE 由 DB 轮询驱动 | worker 是独立进程,进程内 queue 不可见;1s 轮询新 step 简单可靠 |
| PG SKIP LOCKED 队列 | 已有 PostgreSQL,不引入 Redis |
| 向量存 JSON 列、内存余弦 | 与 repository_embeddings 相同的既有模式;单仓库数千 chunk 规模足够 |
| 只做 Python 仓库 | 切块、测试执行、镜像全部大幅简化 |

## 安全边界

LLM 生成代码只在沙箱内执行:docker 后端默认 `--network none`、`--cap-drop ALL`、`no-new-privileges`、内存/CPU 限额;local 后端仅供开发调试,评测一律在 Linux CI/容器内进行。仓库内容按不可信数据处理,prompt 中明确注入不能改变指令。

## 使用

```bash
# 1. 建索引(clone + 切块 + 可选向量)
python -c "..."  # 或在 worker 内调用 ingest_repository;WebUI 后续提供入口
# 2. 创建修复任务
curl -X POST /api/v1/fixer/runs -d '{"repo_full_name":"owner/repo","issue_url":"https://github.com/owner/repo/issues/1"}'
# 3. 消费队列(本机调试用 local;评测用 docker)
python -m workers.agent_runner.runner --backend docker
#    无服务器方案:.github/workflows/agent-runner.yml 每 10 分钟在 GitHub Actions
#    上用 docker 沙箱消费一次(仓库 Secrets 需配置 DATABASE_URL / OPENAI_API_KEY)
# 4. 观察时间线:GET /api/v1/fixer/runs/{id}/stream(SSE)
# 5. 跑评测
python -m packages.agent_core.bench --manifest data/bench-manifest.json --backend docker
```
