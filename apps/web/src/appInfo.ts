export const APP_VERSION = "1.0.0";
export const RELEASES_URL = "https://github.com/minghaoxia61-web/GitSeek/releases";

export type ReleaseCheck = {
  state: "current" | "available" | "none";
  latestVersion: string | null;
  url: string;
};

function versionParts(value: string): number[] {
  return value.replace(/^v/, "").split(".").map((part) => Number.parseInt(part, 10) || 0);
}

function isNewerVersion(candidate: string, current: string): boolean {
  const left = versionParts(candidate);
  const right = versionParts(current);
  for (let index = 0; index < Math.max(left.length, right.length); index += 1) {
    if ((left[index] ?? 0) > (right[index] ?? 0)) return true;
    if ((left[index] ?? 0) < (right[index] ?? 0)) return false;
  }
  return false;
}

export async function checkForUpdates(): Promise<ReleaseCheck> {
  // The releases list includes preview releases, unlike /releases/latest.
  const response = await fetch("https://api.github.com/repos/minghaoxia61-web/GitSeek/releases?per_page=1", {
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!response.ok) throw new Error(`GitHub 更新检查失败（HTTP ${response.status}）`);

  const releases = await response.json() as Array<{ tag_name: string; html_url: string }>;
  const release = releases[0];
  if (!release) return { state: "none", latestVersion: null, url: RELEASES_URL };

  return {
    state: isNewerVersion(release.tag_name, APP_VERSION) ? "available" : "current",
    latestVersion: release.tag_name.replace(/^v/, ""),
    url: release.html_url,
  };
}
