import { FormEvent, useEffect, useRef, useState } from "react";
import type { ConnectionStatus, View } from "../lib/types";
import { navItems } from "../lib/utils";
import { Signal } from "../components/ui";

type IconName = "search" | "bookmark" | "list" | "chart" | "settings" | "compare" | "github" | "panel" | "user";

function ShellIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, React.ReactNode> = {
    search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></>,
    bookmark: <path d="M6.5 4.5A1.5 1.5 0 0 1 8 3h8a1.5 1.5 0 0 1 1.5 1.5V21L12 17.5 6.5 21Z" />,
    list: <><path d="M8 6h11M8 12h11M8 18h11" /><path d="M4 6h.01M4 12h.01M4 18h.01" /></>,
    chart: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1v.1h-4V21a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1-.4h-.1v-4H3a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1v-.1h4V3a1.7 1.7 0 0 0 1.1 1.6 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.17.38.38.72.6 1 .28.28.63.4 1 .4h.1v4H21a1.7 1.7 0 0 0-1.6.6Z" /></>,
    compare: <><path d="M8 3 4 7l4 4M4 7h16M16 21l4-4-4-4M20 17H4" /></>,
    github: <path d="M15 22v-3.9c.04-1-.36-1.8-1-2.3 3.3-.37 6.8-1.62 6.8-7.4 0-1.64-.58-2.98-1.55-4.03.16-.38.67-1.9-.15-3.97 0 0-1.27-.4-4.15 1.54A14.4 14.4 0 0 0 8 1.94C5.12 0 3.85.4 3.85.4c-.82 2.07-.31 3.59-.15 3.97A5.8 5.8 0 0 0 2.15 8.4c0 5.76 3.5 7.02 6.8 7.4-.42.37-.8 1.02-.94 1.98-.85.38-3 .99-4.32-1.24 0 0-.78-1.42-2.27-1.52 0 0-1.45-.02-.1.9 0 0 .97.45 1.64 2.14 0 0 .86 2.62 5 1.73V22" />,
    panel: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16M14 9l-2 3 2 3" /></>,
    user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 21a7 7 0 0 1 14 0" /></>,
  };
  return <svg className="shell-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function Shell({
  view,
  setView,
  compareCount,
  savedCount,
  hasResults,
  detailParent,
  connection,
  onGlobalSearch,
  children,
}: {
  view: View;
  setView: (view: View) => void;
  compareCount: number;
  savedCount: number;
  hasResults: boolean;
  detailParent: "discover" | "results" | "saved";
  connection: ConnectionStatus;
  onGlobalSearch: (query: string) => Promise<void>;
  children: React.ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const [globalQuery, setGlobalQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const currentLabel = view === "discover" ? "搜索项目" : view === "saved" ? "我的收藏" : view === "evals" ? "质量记录" : view === "compare" ? "项目对比" : view === "settings" ? "设置" : view === "detail" ? "项目档案" : "搜索结果";

  useEffect(() => {
    function handleKeydown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        searchInputRef.current?.focus();
        return;
      }
      if (event.key === "Escape" && document.activeElement === searchInputRef.current) {
        searchInputRef.current?.blur();
      }
    }
    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, []);

  async function submitGlobalSearch(event: FormEvent) {
    event.preventDefault();
    if (!globalQuery.trim() || searching) return;
    setSearching(true);
    await onGlobalSearch(globalQuery.trim());
    setSearching(false);
  }

  return (
    <div className={`app-shell ${collapsed ? "app-shell--collapsed" : ""}`}>
      <header className="global-topbar">
        <button className="brand" onClick={() => setView("discover")} aria-label="回到 GitSeek 首页">
          <span className="brand-mark"><span /></span>
          <span><b>GitSeek</b><small>OPEN SOURCE NAVIGATOR</small></span>
        </button>

        <form className="global-search" onSubmit={submitGlobalSearch} role="search">
          <ShellIcon name="search" />
          <input ref={searchInputRef} value={globalQuery} onChange={(event) => setGlobalQuery(event.target.value)} placeholder="搜索技术栈、用途或项目…" aria-label="全局搜索项目" />
          <kbd>⌘ K</kbd>
        </form>

        <div className="global-actions">
          <button className={`connection-button connection-button--${connection.state}`} onClick={() => setView("settings")} title={connection.detail}><Signal tone={connection.state === "online" ? "green" : connection.state === "offline" ? "red" : "amber"} /><span>{connection.state === "online" ? "服务在线" : connection.state === "offline" ? "服务离线" : "连接中"}</span></button>
          <span className="topbar-divider" />
          <button className="account-button" onClick={() => setView("settings")} aria-label="打开账户与设置"><span className="account-avatar">GS</span><span><b>本地访客</b><small>个人工作区</small></span><i>⌄</i></button>
        </div>
      </header>

      <aside className="sidebar">
        <div className="sidebar-heading"><span>工作区</span><button onClick={() => setCollapsed((value) => !value)} aria-label={collapsed ? "展开侧栏" : "折叠侧栏"} title={collapsed ? "展开侧栏" : "折叠侧栏"}><ShellIcon name="panel" /></button></div>

        <nav className="side-nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={view === item.id || (view === "detail" && item.id === detailParent) ? "active" : ""}
              onClick={() => setView(item.id)}
              aria-label={item.label}
              title={item.label}
            >
              <ShellIcon name={item.id === "discover" ? "search" : "bookmark"} />
              <span>{item.label}</span>
              {item.id === "saved" && savedCount > 0 && <em className="nav-count">{savedCount}</em>}
            </button>
          ))}
          {hasResults && <button className={view === "results" || (view === "detail" && detailParent === "results") ? "active" : ""} onClick={() => setView("results")} aria-label="结果" title="结果"><ShellIcon name="list" /><span>搜索结果</span></button>}
        </nav>

        <div className="sidebar-footer">
          <button onClick={() => setView("evals")} className={view === "evals" ? "active" : ""} title="质量记录"><ShellIcon name="chart" /><span>质量记录</span></button>
          <button onClick={() => setView("settings")} className={view === "settings" ? "active" : ""} title="设置"><ShellIcon name="settings" /><span>设置</span></button>
          <a href="https://github.com/minghaoxia61-web/GitSeek" target="_blank" rel="noreferrer" title="在 GitHub 查看"><ShellIcon name="github" /><span>查看源代码</span><i>↗</i></a>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb"><span>GitSeek</span><i>/</i><b>{currentLabel}</b></div>
          <div className="top-actions">
            <button className="compare-shortcut" onClick={() => setView("compare")}><ShellIcon name="compare" />项目对比 {compareCount > 0 && <em>{compareCount}</em>}</button>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
