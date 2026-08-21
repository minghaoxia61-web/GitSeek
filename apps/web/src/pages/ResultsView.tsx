import { useMemo, useState } from "react";

import type { AgentRunResponse, AgentStep, Recommendation, SearchResponse } from "../types";
import type { SearchProblem } from "../lib/types";
import { formatNumber } from "../lib/utils";
import { ResultCard } from "../components/ResultCard";
import { DataFreshness, Signal } from "../components/ui";

export function ResultsView({
  data,
  agentRun,
  agentProgress,
  compare,
  saved,
  toggleCompare,
  onSave,
  onDetail,
  onNewSearch,
  problem,
  notice,
  onCancelAgent,
}: {
  data: SearchResponse;
  agentRun: AgentRunResponse | null;
  agentProgress: AgentStep[];
  compare: string[];
  saved: string[];
  toggleCompare: (name: string) => void;
  onSave: (repo: Recommendation) => void;
  onDetail: (repo: Recommendation) => void;
  onNewSearch: () => void;
  problem: SearchProblem | null;
  notice: string | null;
  onCancelAgent: () => void;
}) {
  const [sortBy, setSortBy] = useState<"match" | "activity" | "approachable">("match");
  const sortedResults = useMemo(() => [...data.results].sort((left, right) => {
    if (sortBy === "activity") return (right.score_breakdown.activity ?? 0) - (left.score_breakdown.activity ?? 0);
    if (sortBy === "approachable") return left.stars - right.stars;
    return right.score - left.score;
  }), [data.results, sortBy]);

  return (
    <div className="page page--results">
      <section className="results-header">
        <div>
          <div className="kicker">{formatNumber(data.source_total_count)} repositories checked</div>
          <h1>{data.eligible_candidate_count} 个项目值得继续看</h1>
          <p>结果按需求匹配排序，不按热度排序。</p>
        </div>
        <button className="secondary-button" onClick={onNewSearch}>修改搜索</button>
      </section>

      {problem && <section className={`result-state result-state--${problem.kind}`}><Signal tone={problem.kind === "rate_limit" ? "amber" : "red"} /><div><small>{problem.kind === "rate_limit" ? "REQUEST LIMITED" : "SERVICE UNAVAILABLE"}</small><h2>{problem.title}</h2><p>{problem.message}</p><button className="primary-button" onClick={onNewSearch}>返回修改查询</button></div></section>}
      {notice && !problem && <div className="notice"><Signal tone="amber" /><span>{notice}</span></div>}
      {!problem && !agentRun && agentProgress.length > 0 && <div className="notice"><Signal /><span>{agentProgress.at(-1)?.summary}</span><button className="text-button" onClick={onCancelAgent}>停止后台优化</button></div>}
      {!problem && data.retrieval?.github_status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>GitHub 当前限流或暂不可用，本次结果来自已同步索引，页面已保留数据时间。</span></div>}
      {!problem && data.retrieval?.embedding_status === "unavailable" && <div className="notice"><Signal tone="amber" /><span>外部语义模型暂不可用，本次已自动改用本地向量排序。</span></div>}

      {!problem && <section className="query-record">
        <div><small>你的需求</small><p>{data.query}</p></div>
        <div className="constraint-record">
          <span>{data.constraints.purpose === "contribution" ? "首次贡献" : "学习项目"}</span>
          {data.constraints.language !== "Any" && data.constraints.language !== "未确定" && <span>{data.constraints.language}</span>}
          {data.constraints.technologies.map((item) => <span key={item}>{item}</span>)}
          {data.constraints.licenses.map((item) => <span key={item}>{item}</span>)}
          {data.constraints.pushed_after && <span>{data.constraints.pushed_after} 后更新</span>}
          {data.constraints.platform && <span>{data.constraints.platform}</span>}
        </div>
        {agentRun && <details className="search-trace"><summary>查看搜索过程</summary><p>{agentRun.interpretation.summary}</p><p>语义排序：{data.retrieval?.embedding_status === "external" ? data.retrieval.embedding_model || "外部向量模型" : "本地向量模型"}</p>{agentRun.steps.map((step) => <span key={step.node}><Signal tone={step.status === "completed" ? "green" : "amber"} />{step.summary}<small>{step.duration_ms}ms</small></span>)}</details>}
        {data.retrieval?.fusion_strategy && <details className="search-trace"><summary>查看检索诊断</summary><p>排序版本：{data.ranking_version} · {data.retrieval.fusion_strategy.toUpperCase()} 融合 · k={data.retrieval.fusion_rank_constant}</p>{Object.entries(data.retrieval.channel_candidate_counts ?? {}).map(([channel, count]) => <span key={channel}><Signal /><span>{channel}</span><small>{count} 个候选 · {data.retrieval?.channel_latency_ms?.[channel.replace(/_\d+$/, "")] ?? "—"}ms</small></span>)}<p>端到端检索耗时：{data.retrieval.total_latency_ms ?? "—"}ms</p></details>}
      </section>}

      {!problem && data.results.length === 0 && <section className="result-state result-state--empty"><span className="empty-mark">0</span><div><small>NO MATCHES</small><h2>这次没有项目通过全部条件</h2><p>GitHub 已完成检索，但语言、许可证、更新时间或规模条件组合后没有留下候选。可以先去掉一到两个硬条件再试。</p><button className="primary-button" onClick={onNewSearch}>放宽搜索条件</button></div></section>}

      {!problem && data.results.length > 0 && <div className="results-layout">
        <section className="results-list">
          <div className="list-toolbar"><span>{data.results.length} 个结果</span><div><button className={sortBy === "match" ? "active" : ""} onClick={() => setSortBy("match")}>最佳匹配</button><button className={sortBy === "activity" ? "active" : ""} onClick={() => setSortBy("activity")}>最近活跃</button><button className={sortBy === "approachable" ? "active" : ""} onClick={() => setSortBy("approachable")}>较小项目</button></div></div>
          {sortedResults.map((repo) => (
            <ResultCard key={repo.full_name} repo={repo} saved={saved.includes(repo.full_name)} selected={compare.includes(repo.full_name)} onSave={() => onSave(repo)} onSelect={() => toggleCompare(repo.full_name)} onDetail={() => onDetail(repo)} />
          ))}
        </section>

      </div>}
    </div>
  );
}
