import type { Recommendation } from "../types";
import { formatNumber } from "../lib/utils";
import { ScoreDial } from "../components/ui";

export function CompareView({ repos, onDiscover, onDetail, onRemove }: { repos: Recommendation[]; onDiscover: () => void; onDetail: (repo: Recommendation) => void; onRemove: (name: string) => void }) {
  if (!repos.length) {
    return (
      <div className="page compare-page">
        <section className="page-heading"><div className="kicker">项目对比</div><h1>把候选项目放在一起看</h1><p>从搜索结果中选择最多三个项目，这里不会自动塞入示例数据。</p></section>
        <section className="compare-empty-state"><span>还没有选择项目</span><p>返回候选项目，点击项目左侧的“＋”加入对比。</p><button className="primary-button" onClick={onDiscover}>去选择项目 →</button></section>
      </div>
    );
  }

  const items = repos;
  return (
    <div className="page compare-page">
      <section className="page-heading"><div className="kicker">项目对比</div><h1>并排看清差异</h1><p>综合分只是入口。这里重点比较相关度、维护情况、许可证和主要风险。</p></section>
      <div className="compare-grid">
        <div className="compare-labels"><div className="compare-empty"><span>比较项</span></div>{["综合匹配", "技术相关", "维护活跃", "项目规模", "许可证", "最近推送", "主要风险"].map((label) => <div key={label}>{label}</div>)}</div>
        {items.map((repo, index) => <article className="compare-column" key={repo.full_name}><header><div className="compare-column-head"><small>候选 {index + 1}</small><button onClick={() => onRemove(repo.full_name)} aria-label={`移除 ${repo.full_name}`}>移除</button></div><h3>{repo.full_name}</h3><p>{repo.description || "暂无仓库简介"}</p></header><div><ScoreDial value={repo.score} small /></div><div><strong>{repo.score_breakdown.relevance?.toFixed(0) ?? "—"}</strong><span>/ 35</span></div><div><strong>{repo.score_breakdown.activity?.toFixed(0) ?? "—"}</strong><span>/ 30</span></div><div><strong>{formatNumber(repo.stars)}</strong><span> Stars</span></div><div><span className="license-badge">{repo.license_spdx ?? "未声明"}</span></div><div><strong>{repo.pushed_at?.slice(0, 10) ?? "未知"}</strong></div><div className="compare-risk">{repo.risks[0] ?? "未发现明显风险"}</div><footer><button onClick={() => onDetail(repo)}>查看项目档案 →</button></footer></article>)}
        {items.length < 3 && <button className="add-column" onClick={onDiscover}>+<span>添加一个候选项目</span></button>}
      </div>
    </div>
  );
}
