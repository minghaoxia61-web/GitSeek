import { useEffect, useState } from "react";

import { apiFetch } from "../api";
import type { EvaluationSummary, RuntimeMetricsSnapshot } from "../types";
import { Signal } from "../components/ui";

const diagnosticLabels: Record<string, string> = {
  reranker_recall_loss: "重排召回损失",
  reranker_order_regression: "重排顺序退化",
  fusion_recall_gap: "融合召回缺口",
  empty_retrieval_channel: "召回通道为空",
};

export function EvalsView() {
  const [summary, setSummary] = useState<EvaluationSummary | null>(null);
  const [runtime, setRuntime] = useState<RuntimeMetricsSnapshot | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "unavailable">("loading");
  const [running, setRunning] = useState(false);

  async function load(method: "GET" | "POST" = "GET") {
    if (method === "POST") setRunning(true);
    try {
      setSummary(await apiFetch<EvaluationSummary>(method === "GET" ? "/api/v1/evals/summary" : "/api/v1/evals/run", { method }));
      try {
        setRuntime(await apiFetch<RuntimeMetricsSnapshot>("/api/v1/metrics"));
      } catch {
        setRuntime(null);
      }
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
        {(summary.channel_experiments ?? []).length > 0 && <article className="panel eval-failures"><div className="panel-title"><span>召回通道与 RRF 对比</span><small>{summary.retrieval_snapshot_id} · 固定测试集</small></div>{summary.channel_experiments?.map((experiment) => <div className="failure-row" key={experiment.key}><b>{experiment.label}</b><span>Recall@10：{experiment.recall_at_10}% · 覆盖率：{experiment.coverage}%</span><span>nDCG@10：{experiment.ndcg_at_10}% · MRR@10：{experiment.mrr_at_10}%</span></div>)}</article>}
        {(summary.retrieval_diagnostics ?? []).length > 0 && <article className="panel diagnostic-panel"><div className="panel-title"><span>检索失败案例</span><small>{summary.retrieval_diagnostics?.length} 条 · 按严重程度排序</small></div>{summary.retrieval_diagnostics?.slice(0, 10).map((item) => <div className="retrieval-diagnostic" key={`${item.query_id}-${item.category}`}><div><span className={`severity severity--${item.severity}`}>{item.severity === "high" ? "高" : item.severity === "medium" ? "中" : "低"}</span><b>{diagnosticLabels[item.category] ?? item.category}</b><small>{item.query_id}</small></div><strong>{item.query}</strong><p>{item.summary}</p>{item.missing_repositories.length > 0 && <small>缺失：{item.missing_repositories.join("、")}</small>}<small>RRF Recall {item.evidence.rrf_recall_at_10}% → 最终 Recall {item.evidence.final_recall_at_10}%</small><em>{item.suggestion}</em></div>)}{(summary.retrieval_diagnostics?.length ?? 0) > 10 && <p className="diagnostic-more">优先展示前 10 条；完整清单保留在版本化评测 API 中。</p>}</article>}
        {runtime && <article className="panel runtime-panel"><div className="panel-title"><span>运行可观测性</span><small>当前实例 · 最近 {Math.round(runtime.uptime_seconds / 60)} 分钟</small></div>{runtime.search.searches > 0 ? <><div className="runtime-metrics"><div><small>搜索请求</small><strong>{runtime.search.searches}</strong></div><div><small>缓存命中率</small><strong>{(runtime.search.cache_hit_rate * 100).toFixed(1)}%</strong></div><div><small>GitHub 降级率</small><strong>{(runtime.search.github_degradation_rate * 100).toFixed(1)}%</strong></div><div><small>搜索 P50 / P95</small><strong>{runtime.search.p50_duration_ms} / {runtime.search.p95_duration_ms}ms</strong></div><div><small>搜索错误率</small><strong>{((runtime.paths["/api/v1/search"]?.error_rate ?? 0) * 100).toFixed(1)}%</strong></div></div>{Object.keys(runtime.search.channels).length > 0 && <div className="runtime-channels">{Object.entries(runtime.search.channels).map(([channel, values]) => <div key={channel}><b>{channel}</b><span>{values.calls} 次</span><small>P50 {values.p50_duration_ms}ms · P95 {values.p95_duration_ms}ms</small></div>)}</div>}{runtime.search.trend.length > 0 && <div className="runtime-trend"><small>最近分钟 P95 趋势</small>{runtime.search.trend.slice(-12).map((point) => { const max = Math.max(...runtime.search.trend.map((item) => item.p95_duration_ms), 1); return <div key={point.minute} title={`${point.minute} · ${point.searches} 次 · P95 ${point.p95_duration_ms}ms`}><i style={{ height: `${Math.max(8, point.p95_duration_ms / max * 100)}%` }} /><span>{new Date(point.minute).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span></div>; })}</div>}</> : <p className="runtime-empty">当前实例还没有搜索样本。运行几次搜索后，这里会显示缓存、降级和延迟趋势；实例重启后窗口会重新计数。</p>}</article>}
        {(summary.experiments ?? []).length > 0 && <article className="panel eval-failures"><div className="panel-title"><span>重排序消融实验</span><small>同一数据集与候选集</small></div>{summary.experiments?.map((experiment) => <div className="failure-row" key={experiment.key}><b>{experiment.label}</b><span>Recall@10：{experiment.recall_at_10}%</span><span>nDCG@10：{experiment.ndcg_at_10}% · MRR@10：{experiment.mrr_at_10}%</span></div>)}</article>}
        {(summary.categories ?? []).length > 0 && <article className="panel eval-categories"><div className="panel-title"><span>覆盖范围</span><small>按约束类型拆分</small></div><div className="category-grid">{summary.categories?.map((category) => <div key={category.key}><span>{category.label}</span><strong>{category.accuracy}%</strong><small>{category.passed_fields} / {category.total_fields} 个字段正确</small><i><b style={{ width: `${category.accuracy}%` }} /></i></div>)}</div></article>}
        <article className="panel eval-failures"><div className="panel-title"><span>失败样本</span><small>{summary.failures.length ? `${summary.failures.length} 项需要处理` : "全部通过"}</small></div>{summary.failures.length ? summary.failures.map((failure) => <div className="failure-row" key={`${failure.case}-${failure.expected}`}><b>{failure.case}</b><span>期望：{failure.expected}</span><span>实际：{failure.actual}</span></div>) : <p className="eval-success">当前固定用例全部通过。新增解析规则时仍需扩充困难样本。</p>}</article>
      </>}
    </div>
  );
}
