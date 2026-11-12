import { useEffect, useRef, useState } from "react";

import { ApiError, createFixerRun, getFixerTimeline } from "../api";
import type { FixerRun, FixerStep } from "../types";
import { Signal } from "../components/ui";

const toolLabels: Record<string, string> = {
  run_bash: "执行命令",
  view_file: "查看文件",
  apply_patch: "应用补丁",
  verify_patch: "检查补丁",
  run_tests: "运行测试",
  finish: "结束",
  tool_error: "工具执行错误",
  usage_unknown: "模型用量未确认",
};

const failureLabels: Record<string, string> = {
  localization_error: "定位错误",
  issue_comprehension_error: "issue 理解错误",
  patch_logic_error: "补丁逻辑错误",
  test_environment_error: "测试环境错误",
  token_budget_exhausted: "token 超预算",
  round_limit_exhausted: "重试轮数耗尽",
  test_not_configured: "未配置验证测试，补丁仍需验证",
  no_patch: "模型已结束，但未生成补丁",
  patch_validation_error: "补丁校验失败",
  baseline_not_reproduced: "修复前未复现指定缺陷，不能进行有效验收",
  acceptance_environment_error: "验收环境或基线回归测试失败",
  acceptance_setup_error: "验收目录或测试准备失败",
  acceptance_patch_error: "补丁无法应用到干净检出",
  acceptance_test_failed: "独立检出的缺陷测试或回归测试失败",
  protected_test_modified: "补丁或执行过程改动了受保护测试，验收未通过",
  execution_identity_error: "代码版本或执行环境与评测配置不一致",
  model_error: "模型调用失败或用量无法确认，已停止后续调用",
  tool_error: "工具执行失败，已保留当前补丁和执行记录",
  evidence_error: "运行记录保存失败，已停止后续调用",
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

function costAmount(value: number): string {
  return value > 0 && value < 0.0001 ? value.toPrecision(2) : value.toFixed(4);
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

  const verification = run?.verification;
  const verified = run?.status === "succeeded" && run.success === true
    && verification?.version === "fixer-verification-v1"
    && verification.scope === "workspace_tests" && verification.model_finished
    && verification.patch_present && verification.apply_ok === true
    && verification.test_executed && verification.test_ok === true
    && verification.test_exit_code === 0 && !verification.test_timed_out;
  const unverified = run?.status === "succeeded" && !verified
    || run?.failure_category === "test_not_configured";
  const statusTone = verified ? "green" : unverified ? "amber" : run?.status === "failed" ? "red" : "amber";
  const acceptance = run?.acceptance;
  const cleanVerified = verified && acceptance?.version === "clean-acceptance-v1"
    && acceptance.scope === "clean_checkout_tests" && acceptance.passed
    && acceptance.baseline_reproduced && acceptance.patch_applied
    && acceptance.protected_files_unchanged && acceptance.environment_verified
    && [[acceptance.baseline_target, 1], [acceptance.baseline_regression, 0],
      [acceptance.final_target, 0], [acceptance.final_regression, 0]].every(([record, code]) => {
        const evidence = record as { exit_code: number; timed_out: boolean; marker_found: boolean } | undefined;
        return evidence !== undefined && evidence.exit_code === code && !evidence.timed_out && evidence.marker_found;
      });
  const statusLabel = cleanVerified ? "干净检出验收通过" : verified ? "工作区测试通过" : unverified ? "结果待验证" : run?.status === "failed" ? "验证未通过" : run?.status === "running" ? "运行中" : "排队中";
  const billing = run?.billing;
  const costKnown = billing?.version === "provider-billing-v1" && billing.state === "known"
    && billing.estimated_cost_usd !== null;
  const costLabel = costKnown ? `调用估算 $${costAmount(billing.estimated_cost_usd!)}` : "费用未知";

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
          <article className="metric-card"><small>状态</small><strong className="fixer-status"><Signal tone={statusTone} /> {statusLabel}</strong><span className={verified ? "passed" : run.status === "failed" && !unverified ? "failed" : ""}>{run.model ?? "默认模型"}</span><p>{run.status === "queued" ? "已排队，等待 worker 认领（可在 GitHub Actions 手动触发 Agent runner 立即处理）" : failureLabels[run.failure_category ?? ""] ?? run.error ?? (unverified ? "缺少完整验证证据，不能确认修复有效。" : run.summary) ?? "等待 worker 认领"}</p></article>
          <article className="metric-card"><small>轮数 / 上限</small><strong>{run.rounds}/{run.max_rounds}</strong><span>token 预算 {run.token_budget.toLocaleString()}</span><p>输入 {run.token_in} · 输出 {run.token_out}{(run.billing?.unknown_usage_calls ?? 0) > 0 ? "（已知部分，用量不完整）" : ""}</p></article>
          <article className="metric-card"><small>工具调用</small><strong>{run.step_count ?? steps.length}</strong><span>{costLabel}</span><p>{costKnown ? "按配置单价估算模型与向量调用，不是最终账单。" : "用量或单价尚未确认，不能按零费用计算。"}</p>{!costKnown && (billing?.known_cost_subtotal_usd ?? 0) > 0 && <p>已知部分 ${costAmount(billing!.known_cost_subtotal_usd)}</p>}<p>issue #{run.issue_number ?? "-"}</p></article>
        </section>
      )}

      {verification && (
        <article className="panel">
          <div className="panel-title"><span>验证证据</span><small>当前工作区检查</small></div>
          <p>补丁：{verification.patch_present ? "已生成" : "未生成"} · 补丁检查：{verification.apply_ok === true ? "通过" : verification.apply_ok === false ? "失败" : "未检查"}</p>
          <p>测试：{verification.test_executed ? verification.test_timed_out ? "超时" : verification.test_ok ? "通过" : "失败" : "未执行"}{verification.test_exit_code !== null ? `（退出码 ${verification.test_exit_code}）` : ""}</p>
          {!acceptance && <p>独立干净环境验收尚未执行，补丁仍需审查。</p>}
        </article>
      )}

      {acceptance && (
        <article className="panel">
          <div className="panel-title"><span>独立验收证据</span><small>{cleanVerified ? "通过" : "未通过或尚未完成"}</small></div>
          <p>修复前复现：{acceptance.baseline_reproduced ? "已确认" : "未确认"} · 干净检出应用补丁：{acceptance.patch_applied ? "已应用" : "未确认"}</p>
          <p>受保护测试：{acceptance.protected_files_unchanged ? "完整性检查通过" : "尚未通过检查"}</p>
          <p>{acceptance.isolated ? "本次使用固定容器运行验收测试。" : "本次为本地开发验证，没有容器隔离。"}补丁仍需审查。</p>
        </article>
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
