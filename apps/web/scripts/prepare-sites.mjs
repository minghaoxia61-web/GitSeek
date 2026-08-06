import { copyFile, cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { extname, relative, resolve, sep } from "node:path";

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const outputDirectory = resolve("dist");
const entries = await readdir(outputDirectory, { recursive: true, withFileTypes: true });
const assets = {};

for (const entry of entries) {
  if (!entry.isFile()) continue;

  const absolutePath = resolve(entry.parentPath, entry.name);
  const assetPath = relative(outputDirectory, absolutePath).split(sep).join("/");
  if (assetPath.startsWith("server/") || assetPath.startsWith(".openai/")) continue;

  assets[`/${assetPath}`] = {
    body: (await readFile(absolutePath)).toString("base64"),
    type: contentTypes[extname(entry.name)] ?? "application/octet-stream",
  };
}

const worker = `const assets = ${JSON.stringify(assets)};

function decode(base64) {
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" }
  });
}

let databaseReady;

async function ensureDatabase(env) {
  if (!env.DB) throw new Error("DB_UNAVAILABLE");
  if (!databaseReady) {
    databaseReady = env.DB.batch([
      env.DB.prepare("CREATE TABLE IF NOT EXISTS search_sessions (id TEXT PRIMARY KEY, query TEXT NOT NULL, constraints_json TEXT NOT NULL, github_query TEXT NOT NULL, source_total_count INTEGER NOT NULL DEFAULT 0, eligible_candidate_count INTEGER NOT NULL DEFAULT 0, ranking_version TEXT NOT NULL, created_at TEXT NOT NULL)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS recommendations (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, repository TEXT NOT NULL, rank INTEGER NOT NULL, score REAL NOT NULL, payload_json TEXT NOT NULL, FOREIGN KEY (session_id) REFERENCES search_sessions(id) ON DELETE CASCADE, UNIQUE(session_id, rank))"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_recommendations_session_id ON recommendations(session_id)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS repository_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, repository TEXT NOT NULL, snapshot_json TEXT NOT NULL, fetched_at TEXT NOT NULL)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_repository_snapshots_repository ON repository_snapshots(repository, fetched_at)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, session_id TEXT, repository TEXT NOT NULL, action TEXT NOT NULL, reason TEXT, query TEXT, device_id TEXT, received_at TEXT NOT NULL)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_feedback_action ON feedback(action)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_feedback_device_id ON feedback(device_id)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS saved_repositories (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL, repository TEXT NOT NULL, saved_at TEXT NOT NULL, UNIQUE(device_id, repository))"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_saved_repositories_device ON saved_repositories(device_id, saved_at)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS contribution_issues (id INTEGER PRIMARY KEY AUTOINCREMENT, repository TEXT NOT NULL, issue_number INTEGER NOT NULL, payload_json TEXT NOT NULL, fetched_at TEXT NOT NULL, UNIQUE(repository, issue_number))"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_contribution_issues_repository ON contribution_issues(repository, fetched_at)"),
      env.DB.prepare("CREATE TABLE IF NOT EXISTS repository_index (repository TEXT PRIMARY KEY, language TEXT, license_spdx TEXT, archived INTEGER NOT NULL DEFAULT 0, pushed_at TEXT, search_text TEXT NOT NULL, payload_json TEXT NOT NULL, fetched_at TEXT NOT NULL)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_repository_index_filters ON repository_index(language, archived, license_spdx, pushed_at)"),
      env.DB.prepare("CREATE INDEX IF NOT EXISTS idx_repository_index_freshness ON repository_index(fetched_at)")
    ]);
  }
  await databaseReady;
}

async function persistSearch(env, payload, repositories) {
  const now = new Date().toISOString();
  const statements = [
    env.DB.prepare("INSERT INTO search_sessions (id, query, constraints_json, github_query, source_total_count, eligible_candidate_count, ranking_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
      .bind(payload.session_id, payload.query, JSON.stringify(payload.constraints), payload.generated_github_query, payload.source_total_count, payload.eligible_candidate_count, payload.ranking_version, now)
  ];
  for (const result of payload.results) {
    statements.push(env.DB.prepare("INSERT INTO recommendations (session_id, repository, rank, score, payload_json) VALUES (?, ?, ?, ?, ?)")
      .bind(payload.session_id, result.full_name, result.rank, result.score, JSON.stringify(result)));
  }
  for (const repository of repositories) {
    statements.push(env.DB.prepare("INSERT INTO repository_snapshots (repository, snapshot_json, fetched_at) VALUES (?, ?, ?)")
      .bind(repository.full_name, JSON.stringify(repository), now));
    const searchText = [repository.name, repository.full_name, repository.description || "", ...(repository.topics || [])].join(" ").toLowerCase();
    statements.push(env.DB.prepare("INSERT INTO repository_index (repository, language, license_spdx, archived, pushed_at, search_text, payload_json, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(repository) DO UPDATE SET language = excluded.language, license_spdx = excluded.license_spdx, archived = excluded.archived, pushed_at = excluded.pushed_at, search_text = excluded.search_text, payload_json = excluded.payload_json, fetched_at = excluded.fetched_at")
      .bind(repository.full_name, repository.language || null, repository.license?.spdx_id || null, repository.archived ? 1 : 0, repository.pushed_at || null, searchText, JSON.stringify(repository), now));
  }
  await env.DB.batch(statements);
}

async function searchIndex(env, query, constraints) {
  const result = await env.DB.prepare("SELECT payload_json, fetched_at FROM repository_index WHERE (language IS NULL OR lower(language) = 'python') AND (? = 0 OR archived = 0) AND (? = '' OR pushed_at > ?) ORDER BY pushed_at DESC LIMIT 300")
    .bind(constraints.exclude_archived ? 1 : 0, constraints.pushed_after || "", constraints.pushed_after || "").all();
  const terms = constraints.technologies.length
    ? constraints.technologies.map((item) => item.toLowerCase())
    : (query.match(/[A-Za-z][A-Za-z0-9.+#-]{2,}/g) || []).map((item) => item.toLowerCase()).filter((item) => !["github", "issue", "mit", "python", "windows"].includes(item)).slice(0, 4);
  return (result.results || []).map((item) => ({ repo: JSON.parse(item.payload_json), fetchedAt: item.fetched_at })).filter((item) => {
    if (constraints.licenses.length && !constraints.licenses.includes(item.repo.license?.spdx_id)) return false;
    if (constraints.project_size === "small" && (item.repo.stargazers_count || 0) >= 5000) return false;
    if (constraints.project_size === "medium" && ((item.repo.stargazers_count || 0) < 1000 || (item.repo.stargazers_count || 0) > 30000)) return false;
    if (constraints.project_size === "large" && (item.repo.stargazers_count || 0) <= 10000) return false;
    if (!terms.length) return true;
    const corpus = [item.repo.name, item.repo.full_name, item.repo.description || "", ...(item.repo.topics || [])].join(" ").toLowerCase();
    return terms.some((term) => corpus.includes(term));
  });
}

async function listSaved(env, deviceId) {
  const result = await env.DB.prepare("SELECT repository FROM saved_repositories WHERE device_id = ? ORDER BY saved_at DESC")
    .bind(deviceId).all();
  return (result.results || []).map((item) => item.repository);
}

async function github(path, params) {
  const url = new URL("https://api.github.com" + path);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== null && value !== undefined) url.searchParams.set(key, String(value));
  }
  const response = await fetch(url, {
    headers: {
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "OpenScout-Public-Demo"
    }
  });
  if (response.status === 404) throw new Error("NOT_FOUND");
  if (response.status === 403 || response.status === 429) throw new Error("RATE_LIMIT");
  if (!response.ok) throw new Error("GITHUB_ERROR");
  return response.json();
}

function parseConstraints(query, body = {}) {
  const lowered = query.toLowerCase();
  const aliases = { fastapi: "FastAPI", django: "Django", flask: "Flask", pytorch: "PyTorch", tensorflow: "TensorFlow", rag: "RAG", llm: "LLM", postgresql: "PostgreSQL", redis: "Redis", docker: "Docker" };
  const technologies = Object.entries(aliases).filter(([key]) => lowered.includes(key)).map(([, value]) => value);
  let licenses = Array.isArray(body.licenses) ? body.licenses : [];
  if (!licenses.length) {
    if (lowered.includes("mit")) licenses.push("MIT");
    if (lowered.includes("apache")) licenses.push("Apache-2.0");
    if (lowered.includes("gpl-3")) licenses.push("GPL-3.0");
  }
  const hoursMatch = query.match(/每周[^0-9]*([0-9]+)[^0-9]*小时/);
  return {
    purpose: body.purpose || ((query.includes("贡献") || lowered.includes("issue")) ? "contribution" : "learning"),
    language: "Python",
    technologies,
    licenses,
    exclude_archived: !query.includes("包含归档"),
    pushed_after: body.pushed_after || null,
    weekly_hours: body.weekly_hours || (hoursMatch ? Number(hoursMatch[1]) : null),
    platform: body.platform || (lowered.includes("windows") ? "Windows" : null),
    project_size: body.project_size || null
  };
}

function repositoryScore(repo, constraints) {
  const corpus = [repo.name, repo.description || "", ...(repo.topics || [])].join(" ").toLowerCase();
  const relevance = constraints.technologies.length
    ? 35 * constraints.technologies.filter((item) => corpus.includes(item.toLowerCase())).length / constraints.technologies.length
    : 20;
  const ageDays = repo.pushed_at ? Math.max((Date.now() - Date.parse(repo.pushed_at)) / 86400000, 0) : 9999;
  const activity = Math.max(30 * Math.exp(-ageDays / 180), 0);
  const popularity = Math.min(Math.log10((repo.stargazers_count || 0) + 1) / 5, 1) * 15;
  const metadata = [repo.description, repo.topics?.length, repo.language, repo.license].filter(Boolean).length / 4 * 10;
  const license = repo.license?.spdx_id ? 10 : 0;
  const breakdown = { relevance, activity, popularity, metadata, license };
  return { score: Object.values(breakdown).reduce((sum, value) => sum + value, 0), breakdown };
}

async function searchRepositories(request, env) {
  const body = await request.json();
  const constraints = parseConstraints(body.query, body);
  const terms = constraints.technologies.length ? constraints.technologies : ((body.query.match(/[A-Za-z][A-Za-z0-9.+#-]{2,}/g) || []).slice(0, 3));
  const queryParts = [...terms, "language:Python"];
  if (constraints.exclude_archived) queryParts.push("archived:false");
  if (constraints.pushed_after) queryParts.push("pushed:>" + constraints.pushed_after);
  if (constraints.project_size === "small") queryParts.push("stars:<5000");
  if (constraints.project_size === "medium") queryParts.push("stars:1000..30000");
  if (constraints.project_size === "large") queryParts.push("stars:>10000");
  const githubQuery = queryParts.join(" ");
  const indexed = await searchIndex(env, body.query, constraints);
  let githubItems = [];
  let githubTotal = 0;
  let githubStatus = "live";
  try {
    const payload = await github("/search/repositories", { q: githubQuery, per_page: 100, sort: "updated", order: "desc" });
    githubItems = payload.items;
    githubTotal = payload.total_count;
  } catch (error) {
    if (!indexed.length) throw error;
    githubStatus = "unavailable";
  }
  const candidates = new Map();
  const sourceMap = new Map();
  const fetchedAtMap = new Map();
  for (const item of indexed) {
    candidates.set(item.repo.full_name, item.repo);
    sourceMap.set(item.repo.full_name, new Set(["local_index"]));
    fetchedAtMap.set(item.repo.full_name, item.fetchedAt);
  }
  const liveFetchedAt = new Date().toISOString();
  for (const repo of githubItems) {
    candidates.set(repo.full_name, repo);
    if (!sourceMap.has(repo.full_name)) sourceMap.set(repo.full_name, new Set());
    sourceMap.get(repo.full_name).add("github_live");
    fetchedAtMap.set(repo.full_name, liveFetchedAt);
  }
  const eligible = [...candidates.values()].filter((repo) => {
    if (repo.language && repo.language.toLowerCase() !== "python") return false;
    if (constraints.exclude_archived && repo.archived) return false;
    if (constraints.licenses.length && !constraints.licenses.includes(repo.license?.spdx_id)) return false;
    if (constraints.pushed_after && (!repo.pushed_at || repo.pushed_at.slice(0, 10) <= constraints.pushed_after)) return false;
    return true;
  });
  const ranked = eligible.map((repo) => ({ repo, ...repositoryScore(repo, constraints) })).sort((a, b) => b.score - a.score).slice(0, body.limit || 10);
  const freshestIndexedAt = indexed.map((item) => item.fetchedAt).sort().at(-1) || null;
  const responsePayload = {
    session_id: crypto.randomUUID(),
    query: body.query,
    generated_github_query: githubQuery,
    constraints,
    source_total_count: githubTotal || indexed.length,
    eligible_candidate_count: eligible.length,
    ranking_version: "public-hybrid-index-v1",
    retrieval: {
      local_candidates: indexed.length,
      github_candidates: githubItems.length,
      github_status: githubStatus,
      index_freshest_at: freshestIndexedAt
    },
    results: ranked.map((item, index) => {
      const repo = item.repo;
      const matches = { language: "MATCH", archived: "MATCH" };
      if (constraints.licenses.length) matches.license = "MATCH";
      if (constraints.pushed_after) matches.activity = "MATCH";
      const reasons = ["主要语言为 Python"];
      if (constraints.technologies.length) reasons.push("匹配技术栈：" + constraints.technologies.join("、"));
      if (repo.pushed_at) reasons.push("最近推送时间：" + repo.pushed_at.slice(0, 10));
      if (repo.license?.spdx_id) reasons.push("许可证：" + repo.license.spdx_id);
      const risks = [];
      if (!repo.topics?.length) risks.push("仓库未配置 Topics，语义判断证据较少");
      if (!repo.open_issues_count) risks.push("当前没有开放 Issue，不一定适合首次贡献");
      risks.push("开始前请打开项目档案，核对 README、测试和贡献指南");
      return {
        rank: index + 1,
        full_name: repo.full_name,
        description: repo.description,
        html_url: repo.html_url,
        score: Math.round(item.score * 10) / 10,
        stars: repo.stargazers_count || 0,
        language: repo.language,
        license_spdx: repo.license?.spdx_id || null,
        pushed_at: repo.pushed_at,
        constraint_match: matches,
        score_breakdown: Object.fromEntries(Object.entries(item.breakdown).map(([key, value]) => [key, Math.round(value * 10) / 10])),
        reasons,
        risks,
        retrieval_sources: [...(sourceMap.get(repo.full_name) || [])].sort(),
        data_fetched_at: fetchedAtMap.get(repo.full_name) || null
      };
    })
  };
  await persistSearch(env, responsePayload, githubItems);
  return json(responsePayload);
}

function safeGithub(path, params, fallback) {
  return github(path, params).catch(() => fallback);
}

async function investigateRepository(owner, repo) {
  const metadata = await github("/repos/" + owner + "/" + repo);
  const [community, root, readme] = await Promise.all([
    safeGithub("/repos/" + owner + "/" + repo + "/community/profile", {}, null),
    safeGithub("/repos/" + owner + "/" + repo + "/contents", { ref: metadata.default_branch }, []),
    safeGithub("/repos/" + owner + "/" + repo + "/readme", {}, null)
  ]);
  const names = new Set(root.map((item) => item.name.toLowerCase()));
  const workflows = names.has(".github") ? await safeGithub("/repos/" + owner + "/" + repo + "/contents/.github/workflows", { ref: metadata.default_branch }, []) : [];
  let readmeText = "";
  try { readmeText = readme?.content ? atob(readme.content.replace(/\\n/g, "")).toLowerCase() : ""; } catch {}
  const files = community?.files || {};
  const signals = {
    has_readme: Boolean(files.readme || readme),
    has_contributing: Boolean(files.contributing),
    has_code_of_conduct: Boolean(files.code_of_conduct || files.code_of_conduct_file),
    has_issue_template: Boolean(files.issue_template),
    has_pull_request_template: Boolean(files.pull_request_template),
    has_security_policy: Boolean(files.security_policy || names.has("security.md")),
    has_license: Boolean(files.license || [...names].some((name) => name.startsWith("license"))),
    has_tests: names.has("test") || names.has("tests"),
    has_ci: workflows.some((item) => item.type === "file"),
    has_pyproject: names.has("pyproject.toml"),
    has_dependency_file: ["requirements.txt", "poetry.lock", "pdm.lock", "uv.lock", "pipfile"].some((name) => names.has(name)),
    has_docker: ["dockerfile", "docker-compose.yml", "compose.yml"].some((name) => names.has(name)),
    readme_has_quickstart: ["## installation", "## quickstart", "## quick start", "## getting started", "## usage"].some((marker) => readmeText.includes(marker))
  };
  const documentation = signals.has_readme * 30 + signals.has_contributing * 25 + signals.has_issue_template * 15 + signals.has_pull_request_template * 10 + signals.has_code_of_conduct * 10 + signals.has_security_policy * 10;
  const engineering = signals.has_tests * 30 + signals.has_ci * 25 + signals.has_pyproject * 20 + signals.has_dependency_file * 15 + signals.has_docker * 10;
  const learning = signals.has_contributing * 25 + signals.has_issue_template * 20 + signals.has_tests * 20 + signals.readme_has_quickstart * 20 + signals.has_code_of_conduct * 15;
  const fetchedAt = new Date().toISOString();
  const sourceRoot = metadata.html_url + "/tree/" + metadata.default_branch;
  const evidenceData = [
    ["community-health", "GitHub community profile completeness", community?.health_percentage || 0, "https://api.github.com/repos/" + owner + "/" + repo + "/community/profile"],
    ["contributing-guide", "Contribution guide detected", signals.has_contributing, files.contributing?.html_url || metadata.html_url],
    ["test-directory", "Root test directory detected", signals.has_tests, sourceRoot],
    ["ci-workflows", "GitHub Actions workflow detected", signals.has_ci, sourceRoot + "/.github/workflows"],
    ["python-project-config", "pyproject.toml detected", signals.has_pyproject, sourceRoot],
    ["readme-quickstart", "README quick-start section detected", signals.readme_has_quickstart, readme?.html_url || metadata.html_url]
  ];
  const risks = [];
  if (!signals.has_contributing) risks.push("未发现贡献指南，首次贡献准备路径可能不明确");
  if (!signals.has_tests) risks.push("根目录未发现 tests/test，仍需进一步检查嵌套测试结构");
  if (!signals.has_ci) risks.push("未发现 GitHub Actions 工作流，自动化质量信号不足");
  if (!signals.has_security_policy) risks.push("未发现安全策略文件");
  return json({
    full_name: metadata.full_name,
    description: metadata.description,
    html_url: metadata.html_url,
    default_branch: metadata.default_branch,
    fetched_at: fetchedAt,
    confidence: community && root.length && readme ? "high" : root.length ? "medium" : "low",
    signals,
    scores: { community_health: community?.health_percentage || 0, documentation, engineering, learning_friendliness: learning },
    evidence: evidenceData.map((item) => ({ id: item[0], fact: item[1], value: item[2], source_url: item[3], fetched_at: fetchedAt, confidence: "high" })),
    risks,
    limitations: ["仅进行静态公开信息调查，不克隆或执行仓库代码", "根目录信号不能完全替代代码级分析", "外部仓库内容始终作为不可信数据处理"]
  });
}

async function recommendIssues(owner, repo, url, env) {
  const payload = await github("/repos/" + owner + "/" + repo + "/issues", { state: "open", per_page: 100, sort: "updated" });
  const limit = Math.max(1, Math.min(Number(url.searchParams.get("limit") || 5), 10));
  const issues = payload.filter((item) => !item.pull_request && !item.assignees?.length && !item.locked).map((item) => {
    const labels = (item.labels || []).map((label) => label.name);
    const normalized = labels.map((label) => label.toLowerCase());
    const beginner = normalized.some((label) => ["good first issue", "good-first-issue", "beginner", "first-timers-only"].includes(label));
    const help = normalized.some((label) => ["help wanted", "help-wanted"].includes(label));
    const risky = normalized.some((label) => ["security", "breaking change", "architecture", "migration"].includes(label));
    const bodyLength = (item.body || "").trim().length;
    let score = 35 + (beginner ? 30 : help ? 18 : 0) + (bodyLength >= 300 ? 18 : bodyLength >= 100 ? 10 : 0) + (item.comments <= 5 ? 10 : item.comments >= 15 ? -12 : 0) + (risky ? -28 : 0);
    const reasons = ["Issue 仍处于开放状态且未被认领"];
    if (beginner) reasons.push("带有新人友好标签"); else if (help) reasons.push("维护者标记为需要帮助");
    if (bodyLength >= 300) reasons.push("任务描述较完整");
    const risks = [];
    if (bodyLength < 100) risks.push("任务描述较短，开始前需要确认范围");
    if (item.comments >= 15) risks.push("讨论较多，任务范围可能仍有争议");
    if (risky) risks.push("标签表明任务可能涉及较高风险");
    return { number: item.number, title: item.title, html_url: item.html_url, labels, comments: item.comments, updated_at: item.updated_at, difficulty: beginner && bodyLength >= 300 && item.comments <= 5 ? "easy" : risky || item.comments >= 15 ? "hard" : "medium", score: Math.max(0, Math.min(Math.round(score), 100)), reasons, risks };
  }).sort((a, b) => b.score - a.score).slice(0, limit);
  const responsePayload = { full_name: owner + "/" + repo, fetched_at: new Date().toISOString(), issues, limitations: ["难度来自标签、描述长度和讨论规模等静态信号", "开始贡献前仍需确认没有关联 Pull Request"] };
  if (issues.length) {
    await env.DB.batch(issues.map((issue) => env.DB.prepare("INSERT INTO contribution_issues (repository, issue_number, payload_json, fetched_at) VALUES (?, ?, ?, ?) ON CONFLICT(repository, issue_number) DO UPDATE SET payload_json = excluded.payload_json, fetched_at = excluded.fetched_at")
      .bind(responsePayload.full_name, issue.number, JSON.stringify(issue), responsePayload.fetched_at)));
  }
  return json(responsePayload);
}

function evaluationSummary() {
  const cases = [
    ["Python FastAPI，MIT，最近半年更新", { technology: "FastAPI", license: "MIT", purpose: "learning" }],
    ["每周 5 小时，第一次贡献 Django 项目", { technology: "Django", hours: 5, purpose: "contribution" }],
    ["Windows 可运行的中文 OCR Python 项目", { platform: "Windows", purpose: "learning" }],
    ["Apache 2.0 许可证的 RAG 工具，近一年活跃", { technology: "RAG", license: "Apache-2.0" }],
    ["找一个 GPL-3.0 的 Python 安全工具", { license: "GPL-3.0" }],
    ["我想学习 PyTorch 模型部署", { technology: "PyTorch", purpose: "learning" }],
    ["最近 30 天更新的 Flask 项目", { technology: "Flask" }],
    ["寻找 PostgreSQL 和 Redis 后端项目", { technology: "PostgreSQL" }],
    ["贡献一个 help wanted 的 LLM 项目", { technology: "LLM", purpose: "contribution" }],
    ["包含归档仓库的 FastAPI 搜索", { exclude_archived: false }]
  ];
  const failures = [];
  let passedFields = 0;
  let totalFields = 0;
  for (const [query, expected] of cases) {
    const constraints = parseConstraints(query);
    for (const [key, value] of Object.entries(expected)) {
      totalFields += 1;
      const actual = key === "technology" ? constraints.technologies.includes(value) : key === "license" ? constraints.licenses.includes(value) : key === "hours" ? constraints.weekly_hours : constraints[key];
      const expectedValue = key === "technology" || key === "license" ? true : value;
      if (actual === expectedValue) passedFields += 1;
      else failures.push({ case: query, expected: String(expectedValue), actual: String(actual) });
    }
  }
  const accuracy = Math.round(passedFields / totalFields * 1000) / 10;
  const failedCases = new Set(failures.map((item) => item.case)).size;
  const caseRate = Math.round((cases.length - failedCases) / cases.length * 1000) / 10;
  return json({
    version: "parser-rules-v2",
    dataset_version: "smoke-queries-v1",
    sample_count: cases.length,
    generated_at: new Date().toISOString(),
    metrics: [
      { key: "constraint_accuracy", label: "约束解析准确率", value: accuracy, unit: "%", target: 95, passed: accuracy >= 95 },
      { key: "case_pass_rate", label: "完整用例通过率", value: caseRate, unit: "%", target: 90, passed: caseRate >= 90 }
    ],
    failures
  });
}

async function handleApi(request, url, env) {
  try {
    await ensureDatabase(env);
    if (url.pathname === "/health") return json({ status: "ok", service: "openscout-public" });
    if (url.pathname === "/api/v1/index/status" && request.method === "GET") {
      const totals = await env.DB.prepare("SELECT COUNT(*) AS repository_count, MAX(fetched_at) AS freshest_at FROM repository_index").first();
      const snapshots = await env.DB.prepare("SELECT COUNT(*) AS snapshot_count FROM repository_snapshots").first();
      return json({
        repository_count: totals?.repository_count || 0,
        snapshot_count: snapshots?.snapshot_count || 0,
        freshest_at: totals?.freshest_at || null,
        ready: (totals?.repository_count || 0) > 0
      });
    }
    if (url.pathname === "/api/v1/search" && request.method === "POST") return await searchRepositories(request, env);
    if (url.pathname === "/api/v1/evals/summary" || url.pathname === "/api/v1/evals/run") return evaluationSummary();
    if (url.pathname === "/api/v1/feedback" && request.method === "POST") {
      const body = await request.json();
      const id = body.id || crypto.randomUUID();
      const receivedAt = new Date().toISOString();
      await env.DB.prepare("INSERT INTO feedback (id, session_id, repository, action, reason, query, device_id, received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
        .bind(id, body.session_id || null, body.repository, body.action, body.reason || null, body.query || null, body.device_id || null, receivedAt).run();
      return json({ id, repository: body.repository, action: body.action, received_at: receivedAt }, 201);
    }
    if (url.pathname === "/api/v1/feedback/summary" && request.method === "GET") {
      const result = await env.DB.prepare("SELECT action, COUNT(*) AS count FROM feedback GROUP BY action").all();
      const byAction = Object.fromEntries((result.results || []).map((item) => [item.action, item.count]));
      return json({ total: Object.values(byAction).reduce((sum, count) => sum + count, 0), by_action: byAction });
    }
    if (url.pathname === "/api/v1/saved" && request.method === "GET") {
      const deviceId = url.searchParams.get("device_id");
      if (!deviceId) return json({ detail: "device_id is required" }, 422);
      return json({ device_id: deviceId, repositories: await listSaved(env, deviceId) });
    }
    if (url.pathname === "/api/v1/saved" && request.method === "POST") {
      const body = await request.json();
      await env.DB.prepare("INSERT INTO saved_repositories (device_id, repository, saved_at) VALUES (?, ?, ?) ON CONFLICT(device_id, repository) DO NOTHING")
        .bind(body.device_id, body.repository, new Date().toISOString()).run();
      return json({ device_id: body.device_id, repositories: await listSaved(env, body.device_id) }, 201);
    }
    const savedMatch = url.pathname.match(/^\\/api\\/v1\\/saved\\/([^/]+)\\/([^/]+)$/);
    if (savedMatch && request.method === "DELETE") {
      const deviceId = url.searchParams.get("device_id");
      if (!deviceId) return json({ detail: "device_id is required" }, 422);
      const repository = decodeURIComponent(savedMatch[1]) + "/" + decodeURIComponent(savedMatch[2]);
      await env.DB.prepare("DELETE FROM saved_repositories WHERE device_id = ? AND repository = ?")
        .bind(deviceId, repository).run();
      return json({ device_id: deviceId, repositories: await listSaved(env, deviceId) });
    }
    const match = url.pathname.match(/^\\/api\\/v1\\/repos\\/([^/]+)\\/([^/]+)\\/(investigate|issues)$/);
    if (match) {
      const owner = decodeURIComponent(match[1]);
      const repo = decodeURIComponent(match[2]);
      return match[3] === "investigate" ? investigateRepository(owner, repo) : recommendIssues(owner, repo, url, env);
    }
    return json({ detail: "API route not found" }, 404);
  } catch (error) {
    if (error.message === "NOT_FOUND") return json({ detail: "GitHub resource not found" }, 404);
    if (error.message === "RATE_LIMIT") return json({ detail: "GitHub public API rate limit reached; please try again later" }, 429);
    if (error.message === "DB_UNAVAILABLE") return json({ detail: "Persistent storage is unavailable" }, 503);
    return json({ detail: "GitHub request failed" }, 502);
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/") || url.pathname === "/health") return handleApi(request, url, env);

    const requestedAsset = assets[url.pathname];
    const asset = requestedAsset ?? assets["/index.html"];
    if (!asset) return new Response("Not found", { status: 404 });

    return new Response(request.method === "HEAD" ? null : decode(asset.body), {
      headers: {
        "content-type": asset.type,
        "cache-control": requestedAsset && url.pathname !== "/index.html"
          ? "public, max-age=31536000, immutable"
          : "no-cache"
      }
    });
  }
};
`;

await mkdir("dist/server", { recursive: true });
await mkdir("dist/.openai", { recursive: true });
await writeFile("dist/server/index.js", worker, "utf8");
await copyFile(".openai/hosting.json", "dist/.openai/hosting.json");
await cp("drizzle", "dist/.openai/drizzle", { recursive: true });
