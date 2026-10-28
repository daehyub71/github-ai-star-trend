// 히어로 이미지 자리 — web/public/art/hero-home.webp 가 있으면 그것, 없으면 SVG 별자리(시안 v1.3 대체 그림)
// 장식이라 보조기기에는 숨긴다(alt="" 와 같은 뜻)
export function HeroArt({ src }: { src: string | null }) {
  if (src) return <div className="art-frame" aria-hidden="true" style={{ backgroundImage: `url(${src})` }} />;
  const pts = "40,270 120,232 200,246 280,178 360,160 440,98 530,58";
  return (
    <div className="art-frame fallback" aria-hidden="true">
      <svg viewBox="0 0 600 375" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="hl" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stopColor="#60A5FA" /><stop offset=".6" stopColor="#A78BFA" /><stop offset="1" stopColor="#FDBA74" />
          </linearGradient>
          <radialGradient id="hs">
            <stop offset="0" stopColor="#fff" /><stop offset=".4" stopColor="#C7D2FE" /><stop offset="1" stopColor="#C7D2FE" stopOpacity="0" />
          </radialGradient>
        </defs>
        <polyline points={pts} fill="none" stroke="url(#hl)" strokeWidth="3" strokeLinecap="round" />
        <polyline points={pts} fill="none" stroke="url(#hl)" strokeWidth="14" strokeLinecap="round" opacity=".18" />
        {pts.split(" ").map((p, i) => {
          const [x, y] = p.split(",");
          return <circle key={p} cx={x} cy={y} r={13 + i * 2.5} fill="url(#hs)" />;
        })}
      </svg>
    </div>
  );
}
