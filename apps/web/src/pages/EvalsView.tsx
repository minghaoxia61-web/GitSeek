import { useEffect, useState } from "react";

import { apiFetch } from "../api";
import type { EvaluationSummary } from "../types";
import { Signal } from "../components/ui";

export function EvalsView() {
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [running, setRunning] = useState(false);

  async function load(method: "GET" | "POST" = "GET") {
    if (method === "POST") setRunning(true);
    try {
      setSummary(await apiFetch<EvaluationSummary>(method === "GET" ? "/api/v1/evals/summary" : "/api/v1/evals/run", { method }));
      setStatus("ready");
    } catch {
      setStatus("unavailable");
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <div className="page evals-page">
      <section className="page-heading page-heading--row"><div><div className="kicker">质量记录</div><h1>固定用例的真实结果</h1><p>只展示实际执行过的确定性检查；失败项会直接列出，不用漂亮数字遮住。</p></div><button className="primary-button" onClick={() => load("POST")} disabled={running}>{running ? <><i className="spinner" /> 正在运行</> : "重新运行评测"}</button></section>
      {status === "loading" && <div className="eval-state"><i className="spinner" /> 正在读取评测结果…</div>}
      {status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>评测接口暂不可用。启动后端后即可运行固定用例。</span></div>}
      {summary && <>
        <section className="metric-grid">
          {summary.metrics.map((metric) => <article className="metric-card" key={metric.key}><small>{metric.label}</small><strong>{metric.value}{metric.unit}</strong><span className={metric.passed ? "passed" : "failed"}>{metric.passed ? "达到目标" : "未达到目标"}</span><p>目标 ≥ {metric.target}{metric.unit}</p></article>)}
          <article className="metric-card"><small>固定测试样本</small><strong>{summary.sample_count}</strong><span className="passed">{summary.dataset_version}</span><p>版本 {summary.version}</p></article>
        </section>
        {(summary.categories ?? []).length > 0 && <article className="panel eval-categories"><div className="panel-title"><span>覆盖范围</span><small>按约束类型拆分</small></div><div className="category-grid">{summary.categories?.map((category) => <div key={category.key}><span>{category.label}</span><strong>{category.accuracy}%</strong><small>{category.passed_fields} / {category.total_fields} 个字段正确</small><i><b style={{ width: `${category.accuracy}%` }} /></i></div>)}</div></article>}
        <article className="panel eval-failures"><div className="panel-title"><span>失败样本</span><small>{summary.failures.length ? `${summary.failures.length} 项需要处理` : "全部通过"}</small></div>{summary.failures.length ? summary.failures.map((failure) => <div className="failure-row" key={`${failure.case}-${failure.expected}`}><b>{failure.case}</b><span>期望：{failure.expected}</span><span>实际：{failure.actual}</span></div>) : <p className="eval-success">当前固定用例全部通过。新增解析规则时仍需扩充困难样本。</p>}</article>
      </>}
    </div>
  );
}
