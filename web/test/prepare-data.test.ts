import { describe, expect, it } from "vitest";

import { fetchCommands, gitAuthEnv, planPrepare } from "../scripts/prepare-data.mjs";

const TOKEN = "github_pat_" + "x".repeat(70);       // 형식만 맞춘 가짜 값

describe("prepare-data — Vercel 빌드 준비 (결정 55, R12)", () => {
  it("copies the public data when the build can see ../data/site", () => {
    const plan = planPrepare({}, (p) => p === "../data/site/index.json");
    expect(plan.site).toEqual({ action: "copy", from: "../data/site" });
  });

  it("fetches data/site from the public repo when files outside the root are not there (R12)", () => {
    const env = { VERCEL_GIT_REPO_OWNER: "o", VERCEL_GIT_REPO_SLUG: "r", VERCEL_GIT_COMMIT_SHA: "abc123" };
    expect(planPrepare(env, () => false).site).toEqual({ action: "fetch", repo: "o/r", ref: "abc123", folder: "data/site" });
    expect(planPrepare({}, () => false).site.action).toBe("fail");
  });

  it("fetches the private site copy only with a repo and a token", () => {
    const env = { STARTREND_PRIVATE_REPO: "o/p", STARTREND_PRIVATE_REPO_TOKEN: TOKEN };
    expect(planPrepare(env, () => true).priv).toEqual({ action: "fetch", repo: "o/p", ref: "HEAD", folder: "site-private" });
    expect(planPrepare({}, () => true).priv.action).toBe("skip");
  });

  it("refuses a production build without the private copy", () => {
    // 카드 없는 사이트가 조용히 배포되지 않게
    expect(planPrepare({ VERCEL_ENV: "production" }, () => true).priv.action).toBe("fail");
  });

  it("passes the token through git's environment, never on the command line", () => {
    const env = gitAuthEnv(TOKEN, {});
    expect(env.GIT_CONFIG_KEY_0).toBe("http.https://github.com/.extraheader");
    expect(env.GIT_CONFIG_VALUE_0).toBe(`AUTHORIZATION: basic ${Buffer.from(`x-access-token:${TOKEN}`).toString("base64")}`);
    expect(env.GIT_TERMINAL_PROMPT).toBe("0");
    const cmds = fetchCommands("o/p", "HEAD", "site-private", ".tmp");
    expect(cmds.flat().join(" ")).not.toContain(TOKEN);
    expect(cmds.flat().join(" ")).not.toContain(env.GIT_CONFIG_VALUE_0);
    expect(cmds.map((c) => c[0])).toEqual(["clone", "-C", "-C", "-C"]);
    expect(cmds[0]).toContain("https://github.com/o/p.git");
  });
});
