// scripts/prepare-data.mjs 의 타입 — 테스트(test/prepare-data.test.ts)가 쓴다
type Env = Record<string, string | undefined>;
type Step =
  | { action: "copy"; from: string }
  | { action: "fetch"; repo: string; ref: string; folder: string }
  | { action: "skip" | "fail"; reason: string };

export function planPrepare(env: Env, exists: (p: string) => boolean): { site: Step; priv: Step };
export function gitAuthEnv(token: string, base?: Env): Env;
export function fetchCommands(repo: string, ref: string, folder: string, dir: string): string[][];
export function main(env?: Env): void;
