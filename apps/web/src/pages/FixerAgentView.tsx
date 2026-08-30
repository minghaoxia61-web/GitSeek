import { useEffect, useRef, useState } from "react";

import { ApiError, createFixerRun, getFixerTimeline } from "../api";
import type { FixerRun, FixerStep } from "../types";
import { Signal } from "../components/ui";

const toolLabels: Record<string, string> = {
  run_bash: "执行命令",
  view_file: "查看文件",
  apply_patch: "应用补丁",
  run_tests: "运行测试",
  finish: "结束",
};

const failureLabels: Record<string, string> = {
  localization_error: "定位错误",
  issue_comprehension_error: "issue 理解错误",
  patch_logic_error: "补丁逻辑错误",
  test_environment_error: "测试环境错误",
  token_budget_exhausted: "token 超预算",
  round_limit_exhausted: "重试轮数耗尽",
};

function stepInputSummary(step: FixerStep): string {
  const input = step.input ?? {};
  if (typeof input.command === "string") return input.command;
  if (typeof input.path === "string") {
    const span = input.start ? `:${input.start}-${input.end ?? input.start}` : "";
    return `${input.path}${span}`;
  }
  if (typeof input.summary === "string") return input.summary;
  return JSON.stringify(input);
}

export function FixerAgentView() {
  const [repo, setRepo] = useState("");
  const [issueUrl, setIssueUrl] = useState("");
  const [maxRounds, setMaxRounds] = useState("5");
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState<FixerStep[]>([]);
  const [run, setRun] = useState<FixerRun | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  const pollTimer = useRef<number | null>(null);

  useEffect(() => () => {
    if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
    controller.current?.abort();
  }, []);

  async function watchRun(runId: string, signal: AbortSignal) {
    let afterSeq = 0;
    const tick = async () => {
      if (signal.aborted) return;
      try {
        const snapshot = await getFixerTimeline(runId, afterSeq);
        setRun(snapshot.run);
        if (snapshot.steps.length) {
          setSteps((current) => {
            const known = new Set(current.map((step) => step.seq));
            return [...current, ...snapshot.steps.filter((step) => !known.has(step.seq))];
          });
          afterSeq = Math.max(afterSeq, ...snapshot.steps.map((step) => step.seq));
        }
        if (snapshot.run.status === "succeeded" || snapshot.run.status === "failed") {
          if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
          setRunning(false);
        }
      } catch (error) {
        if (pollTimer.current !== null) window.clearInterval(pollTimer.current);
        setRunning(false);
        setProblem(error instanceof ApiError ? error.message : "读取任务状态失败，请稍后刷新查看。");
      }
    };
    await tick();
    if (signal.aborted) return;
    pollTimer.current = window.setInterval(() => void tick(), 5000);
  }

  async function submit() {
    if (running) return;
    const repoName = repo.trim();
    if (!repoName.includes("/")) {
      setProblem("请输入 owner/repo 形式的仓库全名。");
      return;
    }
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setRunning(true);
    setProblem(null);
    setSteps([]);
    setRun(null);
    try {
      const created = await createFixerRun({
        repo_full_name: repoName,
        issue_url: issueUrl.trim() || null,
        max_rounds: Number(maxRounds) > 0 ? Number(maxRounds) : null,
      });
      setRun(created);
      await watchRun(created.run_id, abort.signal);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        setProblem("已停止跟踪该次修复运行。");
      } else if (error instanceof ApiError) {
        setProblem(error.message);
      } else {
        setProblem("修复 Agent 暂不可用，请确认后端已配置 OPENAI_API_KEY 且队列 worker 在运行。");
      }
    } finally {
      setRunning(false);
    }
  }

  const statusTone = run?.status === "succeeded" ? "green" : run?.status === "failed" ? "red" : "amber";
  const statusLabel = run?.status === "succeeded" ? "修复成功" : run?.status === "failed" ? "修复失败" : run?.status === "running" ? "运行中" : "排队中";

  return (
    <div className="page fixer-page">
      <section className="page-heading page-heading--row">
        <div>
          <div className="kicker">修复 Agent</div>
          <h1>从 Issue 到补丁草稿</h1>
          <p>输入一个真实 issue:代码定位 → 极简修复循环 → 沙箱内验证,每一步工具调用可见,结束时输出带证据的 diff。</p>
        </div>
      </section>

      <article className="panel fixer-form">
        <div className="fixer-form-row">
          <label className="fixer-field"><span>仓库 owner/repo</span><input className="fixer-input" value={repo} onChange={(event) => setRepo(event.target.value)} placeholder="例如 langchain-ai/langchain" /></label>
          <label className="fixer-field fixer-field--wide"><span>Issue 链接</span><input className="fixer-input" value={issueUrl} onChange={(event) => setIssueUrl(event.target.value)} placeholder="https://github.com/owner/repo/issues/123" /></label>
          <label className="fixer-field"><span>最大轮数</span><input className="fixer-input" type="number" min={1} max={10} value={maxRounds} onChange={(event) => setMaxRounds(event.target.value)} /></label>
          <button className="primary-button" onClick={() => void submit()} disabled={running}>{running ? <><i className="spinner" /> 运行中</> : "运行修复 Agent"}</button>
        </div>
        <p className="fixer-hint">需要后端已为该仓库建立代码索引(ingest),且队列 worker 在消费任务;模型走 OpenAI 兼容接口。</p>
      </article>

      {problem && <div className="notice"><Signal tone="red" /><span>{problem}</span></div>}

      {run && (
        <section className="metric-grid">
          <article className="metric-card"><small>状态</small><strong className="fixer-status"><Signal tone={statusTone} /> {statusLabel}</strong><span className={run.status === "succeeded" ? "passed" : run.status === "failed" ? "failed" : ""}>{run.model ?? "默认模型"}</span><p>{run.status === "queued" ? "已排队，等待 worker 认领（可在 GitHub Actions 手动触发 Agent runner 立即处理）" : run.summary ?? failureLabels[run.failure_category ?? ""] ?? run.error ?? "等待 worker 认领"}</p></article>
          <article className="metric-card"><small>轮数 / 上限</small><strong>{run.rounds}/{run.max_rounds}</strong><span>token 预算 {run.token_budget.toLocaleString()}</span><p>输入 {run.token_in} · 输出 {run.token_out}</p></article>
          <article className="metric-card"><small>工具调用</small><strong>{run.step_count ?? steps.length}</strong><span>成本 ${run.cost_usd.toFixed(4)}</span><p>issue #{run.issue_number ?? "-"}</p></article>
        </section>
      )}

      {steps.length > 0 && (
        <article className="panel">
          <div className="panel-title"><span>执行时间线</span><small>{steps.length} 次工具调用 · 每一步可见</small></div>
          <div className="fixer-steps">
            {steps.map((step) => (
              <div className="fixer-step" key={step.seq}>
                <div className="fixer-step-head">
                  <b>{toolLabels[step.tool] ?? step.tool}</b>
                  <small>round {step.round}</small>
                  <small>{step.latency_ms}ms</small>
                  <code>{stepInputSummary(step)}</code>
                </div>
                {step.output && <pre>{step.output}</pre>}
              </div>
            ))}
          </div>
        </article>
      )}

      {run?.diff && (
        <article className="panel">
          <div className="panel-title"><span>补丁草稿</span><small>git diff · 尚未推送</small></div>
          <pre className="fixer-diff">{run.diff}</pre>
        </article>
      )}
    </div>
  );
}
