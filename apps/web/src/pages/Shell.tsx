import type { ConnectionStatus, View } from "../lib/types";
import { navItems } from "../lib/utils";
import { Signal } from "../components/ui";

export function Shell({
  view,
  setView,
  compareCount,
  savedCount,
  hasResults,
  detailParent,
  connection,
  children,
}: {
  view: View;
  setView: (view: View) => void;
  compareCount: number;
  savedCount: number;
  hasResults: boolean;
  detailParent: "discover" | "results" | "saved";
  connection: ConnectionStatus;
  children: React.ReactNode;
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("discover")} aria-label="回到 GitSeek 首页">
          <span className="brand-mark">G</span>
          <span><b>GitSeek</b><small>repository finder</small></span>
        </button>

        <nav className="side-nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={view === item.id || (view === "detail" && item.id === detailParent) ? "active" : ""}
              onClick={() => setView(item.id)}
              aria-label={item.label}
              title={item.label}
            >
              <span className={`nav-glyph nav-glyph--${item.id}`} />
              <span>{item.label}</span>
              {item.id === "saved" && savedCount > 0 && <em className="nav-count">{savedCount}</em>}
            </button>
          ))}
          {hasResults && <button className={view === "results" || (view === "detail" && detailParent === "results") ? "active" : ""} onClick={() => setView("results")} aria-label="结果" title="结果"><span className="nav-glyph nav-glyph--results" /><span>结果</span></button>}
        </nav>

        <div className="sidebar-footer">
          <button onClick={() => setView("evals")} className={view === "evals" ? "active" : ""}><span className="nav-glyph nav-glyph--evals" />质量记录</button>
          <button onClick={() => setView("settings")} className={view === "settings" ? "active" : ""}><span className="nav-glyph nav-glyph--settings" />设置</button>
          <a href="https://github.com/minghaoxia61-web/GitSeek" target="_blank" rel="noreferrer">GitHub ↗</a>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar glass">
          <div className="breadcrumb"><b>{view === "discover" ? "搜索项目" : view === "saved" ? "我的收藏" : view === "evals" ? "质量记录" : view === "compare" ? "项目对比" : view === "settings" ? "设置" : view === "detail" ? "项目档案" : "搜索结果"}</b></div>
          <div className="top-actions">
            <button className="compare-shortcut" onClick={() => setView("compare")}>对比 {compareCount > 0 && <em>{compareCount}</em>}</button>
            <button className={`system-chip system-chip--${connection.state}`} onClick={() => setView("settings")} title={connection.detail}><Signal tone={connection.state === "online" ? "green" : connection.state === "offline" ? "red" : "amber"} /> {connection.state === "online" ? "在线" : connection.state === "offline" ? "离线" : "连接中"}</button>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
