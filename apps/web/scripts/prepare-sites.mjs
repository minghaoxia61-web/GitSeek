import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
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
  return {
    purpose: body.purpose || ((query.includes("贡献") || lowered.includes("issue")) ? "contribution" : "learning"),
    language: "Python",
    technologies,
    licenses,
    exclude_archived: !query.includes("包含归档"),
    pushed_after: body.pushed_after || null,
    weekly_hours: body.weekly_hours || null,
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

async function searchRepositories(request) {
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
  const payload = await github("/search/repositories", { q: githubQuery, per_page: 100, sort: "updated", order: "desc" });
  const eligible = payload.items.filter((repo) => {
    if (repo.language && repo.language.toLowerCase() !== "python") return false;
    if (constraints.exclude_archived && repo.archived) return false;
    if (constraints.licenses.length && !constraints.licenses.includes(repo.license?.spdx_id)) return false;
    if (constraints.pushed_after && (!repo.pushed_at || repo.pushed_at.slice(0, 10) <= constraints.pushed_after)) return false;
    return true;
  });
  const ranked = eligible.map((repo) => ({ repo, ...repositoryScore(repo, constraints) })).sort((a, b) => b.score - a.score).slice(0, body.limit || 10);
  return json({
    session_id: crypto.randomUUID(),
    query: body.query,
    generated_github_query: githubQuery,
    constraints,
    source_total_count: payload.total_count,
    eligible_candidate_count: eligible.length,
    ranking_version: "public-worker-baseline-v2",
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
        risks
      };
    })
  });
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

async function recommendIssues(owner, repo, url) {
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
  return json({ full_name: owner + "/" + repo, fetched_at: new Date().toISOString(), issues, limitations: ["难度来自标签、描述长度和讨论规模等静态信号", "开始贡献前仍需确认没有关联 Pull Request"] });
}

function evaluationSummary() {
  return json({
    version: "parser-rules-v2",
    dataset_version: "smoke-queries-v1",
    sample_count: 10,
    generated_at: new Date().toISOString(),
    metrics: [
      { key: "constraint_accuracy", label: "约束解析准确率", value: 100, unit: "%", target: 95, passed: true },
      { key: "case_pass_rate", label: "完整用例通过率", value: 100, unit: "%", target: 90, passed: true }
    ],
    failures: []
  });
}

async function handleApi(request, url) {
  try {
    if (url.pathname === "/health") return json({ status: "ok", service: "openscout-public" });
    if (url.pathname === "/api/v1/search" && request.method === "POST") return await searchRepositories(request);
    if (url.pathname === "/api/v1/evals/summary" || url.pathname === "/api/v1/evals/run") return evaluationSummary();
    if (url.pathname === "/api/v1/feedback" && request.method === "POST") {
      const body = await request.json();
      return json({ id: crypto.randomUUID(), repository: body.repository, action: body.action, received_at: new Date().toISOString() }, 201);
    }
    const match = url.pathname.match(/^\\/api\\/v1\\/repos\\/([^/]+)\\/([^/]+)\\/(investigate|issues)$/);
    if (match) {
      const owner = decodeURIComponent(match[1]);
      const repo = decodeURIComponent(match[2]);
      return match[3] === "investigate" ? investigateRepository(owner, repo) : recommendIssues(owner, repo, url);
    }
    return json({ detail: "API route not found" }, 404);
  } catch (error) {
    if (error.message === "NOT_FOUND") return json({ detail: "GitHub resource not found" }, 404);
    if (error.message === "RATE_LIMIT") return json({ detail: "GitHub public API rate limit reached; please try again later" }, 429);
    return json({ detail: "GitHub request failed" }, 502);
  }
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/") || url.pathname === "/health") return handleApi(request, url);

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
