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
    locator.py                  关键词(FTS)与向量双通道 → 复用 packages.ranking RRF 融合
    tools.py                    模型输出解析:```bash / ```diff / VIEW 行 / FINISH:
    fixer.py                    极简修复循环:≤max_rounds、token 硬预算、失败分类
    llm.py                      OpenAI 兼容 /chat/completions 客户端(DeepSeek 可用)
    bench.py                    评测 harness:清单驱动,产出 Top-K/端到端/成本指标
packages/sandbox/               local(仅开发)与 docker(默认断网、限额、降权)两种后端
```

## 数据模型(迁移 20260830_0009)

`fixer_runs`(状态机 queued→running→succeeded|failed,含 token/成本/失败分类)、`fixer_steps`(每个工具调用一条,支撑 SSE 时间线)、`fixer_patches`(每轮补丁与最终 diff)、`agent_code_chunks`(代码块索引,PostgreSQL 上带 tsvector 生成列 + GIN)、`agent_bench_results`(指标逐条落库)。 screening agent 已占用 `agent_runs`/`agent_steps`,故新表使用 `fixer_` 前缀。

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
