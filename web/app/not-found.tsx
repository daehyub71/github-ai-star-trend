import Link from "next/link";

import { SiteHeader } from "@/components/SiteHeader";

export default function NotFound() {
  return (
    <>
      <SiteHeader current="week" />
      <main className="page">
        <section className="panel">
          <h1 style={{ margin: 0, fontSize: 22 }}>페이지가 없다</h1>
          <p className="muted">카드가 없는 저장소이거나 아직 만들지 않은 주일 수 있다. <Link href="/">이번 주로 돌아가기</Link></p>
        </section>
      </main>
    </>
  );
}
