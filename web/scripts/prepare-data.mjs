// Vercel 빌드 준비 (SPEC 결정 55 · R12) — 공개 데이터와 비공개 사이트 사본을 web/.data/ 아래로 모은다.
//
//   web/.data/site          ← ../data/site 가 보이면 복사, 안 보이면(R12) 공개 저장소에서 그 커밋의 data/site 만 받는다
//   web/.data/site-private  ← 비공개 저장소의 site-private/ 만 받는다(읽기 전용 토큰)
//
// 토큰은 명령줄에 넣지 않고 git 환경변수 설정(GIT_CONFIG_*)으로만 넘긴다 — 실패해도 빌드 로그에 남지 않게.
// 프로덕션 빌드는 비공개 사본 없이 진행하지 않는다(카드 없는 사이트가 조용히 배포되지 않게).
// 사용: node scripts/prepare-data.mjs   (web/vercel.json 의 buildCommand)
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const OUT = ".data";

/** 무엇을 할지 — 환경변수와 파일 존재만 보고 정한다(부작용 없음) */
export function planPrepare(env, exists) {
  let site;
  if (exists("../data/site/index.json")) {
    site = { action: "copy", from: "../data/site" };
  } else if (env.VERCEL_GIT_REPO_OWNER && env.VERCEL_GIT_REPO_SLUG && env.VERCEL_GIT_COMMIT_SHA) {
    site = { action: "fetch", repo: `${env.VERCEL_GIT_REPO_OWNER}/${env.VERCEL_GIT_REPO_SLUG}`,
             ref: env.VERCEL_GIT_COMMIT_SHA, folder: "data/site" };
  } else {
    site = { action: "fail", reason: "../data/site 가 없고 Vercel 저장소 정보도 없다" };
  }
  let priv;
  if (env.STARTREND_PRIVATE_REPO && env.STARTREND_PRIVATE_REPO_TOKEN) {
    priv = { action: "fetch", repo: env.STARTREND_PRIVATE_REPO, ref: "HEAD", folder: "site-private" };
  } else if (env.VERCEL_ENV === "production") {
    priv = { action: "fail", reason: "프로덕션 빌드에 비공개 사본(STARTREND_PRIVATE_REPO·_TOKEN)이 없다" };
  } else {
    priv = { action: "skip", reason: "비공개 저장소 설정이 없다 — 카드·브리핑 없이 빌드한다" };
  }
  return { site, priv };
}

/** 토큰을 git 환경변수 설정으로 — 명령줄·오류 메시지에 나오지 않는다 */
export function gitAuthEnv(token, base = process.env) {
  const basic = Buffer.from(`x-access-token:${token}`).toString("base64");
  return {
    ...base,
    GIT_TERMINAL_PROMPT: "0",
    GIT_CONFIG_COUNT: "1",
    GIT_CONFIG_KEY_0: "http.https://github.com/.extraheader",
    GIT_CONFIG_VALUE_0: `AUTHORIZATION: basic ${basic}`,
  };
}

/** 한 폴더만 얕게 받는 git 명령들(인자 배열) */
export function fetchCommands(repo, ref, folder, dir) {
  return [
    ["clone", "--quiet", "--filter=blob:none", "--no-checkout", "--depth", "1", `https://github.com/${repo}.git`, dir],
    ["-C", dir, "sparse-checkout", "set", folder],
    ["-C", dir, "fetch", "--quiet", "--depth", "1", "--filter=blob:none", "origin", ref],
    ["-C", dir, "checkout", "--quiet", "FETCH_HEAD"],
  ];
}

function fetchFolder({ repo, ref, folder }, dest, env) {
  const tmp = fs.mkdtempSync(path.join(OUT, ".fetch-"));
  const dir = path.join(tmp, "repo");
  try {
    for (const args of fetchCommands(repo, ref, folder, dir)) {
      try {
        execFileSync("git", args, { env, stdio: ["ignore", "ignore", "pipe"] });
      } catch {
        // 인자에는 토큰이 없지만, 혹시 모를 출력은 그대로 옮기지 않는다
        throw new Error(`git ${args[0] === "-C" ? args[2] : args[0]} 실패 — ${repo} 의 ${folder}`);
      }
    }
    const src = path.join(dir, folder);
    if (!fs.existsSync(src)) throw new Error(`${repo} 에 ${folder} 가 없다`);
    fs.cpSync(src, dest, { recursive: true });
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function count(dir) {
  return fs.existsSync(dir) ? fs.readdirSync(dir, { recursive: true }).length : 0;
}

export function main(env = process.env) {
  const plan = planPrepare(env, (p) => fs.existsSync(p));
  fs.rmSync(OUT, { recursive: true, force: true });
  fs.mkdirSync(OUT, { recursive: true });
  const site = path.join(OUT, "site");
  const priv = path.join(OUT, "site-private");

  if (plan.site.action === "fail") throw new Error(plan.site.reason);
  if (plan.site.action === "copy") fs.cpSync(plan.site.from, site, { recursive: true });
  else fetchFolder(plan.site, site, { ...env, GIT_TERMINAL_PROMPT: "0" });
  console.log(`[prepare-data] 공개 데이터: ${plan.site.action} → ${site} (${count(site)}개)`);

  if (plan.priv.action === "fail") throw new Error(plan.priv.reason);
  if (plan.priv.action === "fetch") {
    fetchFolder(plan.priv, priv, gitAuthEnv(env.STARTREND_PRIVATE_REPO_TOKEN, env));
    console.log(`[prepare-data] 비공개 사본: ${plan.priv.repo} → ${priv} (${count(priv)}개)`);
  } else {
    console.log(`[prepare-data] 비공개 사본: 건너뜀 — ${plan.priv.reason}`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    main();
  } catch (e) {
    console.error(`[prepare-data] ${e instanceof Error ? e.message : String(e)}`);
    process.exit(1);
  }
}
