// 카드·브리핑 마크다운의 유일한 렌더러 — raw HTML 은 끈다(NFR-7, 결정 43).
// raw HTML 을 살리는 rehype 플러그인은 쓰지 않는다(test/markdown.test.tsx 가 소스 전체를 검사한다).
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ href, children: text }) => {
            const external = typeof href === "string" && /^https?:\/\//.test(href);
            return external ? (
              <a href={href} target="_blank" rel="noopener noreferrer nofollow">{text}</a>
            ) : (
              <a href={href}>{text}</a>
            );
          },
          table: ({ children: rows }) => (
            <div className="table-wrap"><table>{rows}</table></div>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
