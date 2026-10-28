import { WeekView } from "@/components/WeekView";
import { loadIndex } from "@/lib/data";

// 첫 화면 = 가장 최근 주
export default function Home() {
  const latest = loadIndex().latest;
  if (!latest) return <main className="page"><p>아직 랭킹이 없다 — `python -m startrend export` 를 먼저 돌린다.</p></main>;
  return <WeekView week={latest} />;
}
