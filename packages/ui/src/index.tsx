import type { MusicContext } from "@linerfy/domain";
import type { ReactNode } from "react";

export function LinerfyMark() {
  return (
    <span className="linerfy-mark" aria-label="Linerfy">
      <span aria-hidden="true">L</span>
    </span>
  );
}

export function SourceLink({
  children,
  href,
}: {
  children: ReactNode;
  href: string;
}) {
  return (
    <a className="source-link" href={href} rel="noreferrer" target="_blank">
      {children}
      <span aria-hidden="true">↗</span>
    </a>
  );
}

export function MusicContextCard({ context }: { context: MusicContext }) {
  return (
    <article className="context-card">
      <header className="release-header">
        {context.release.artworkUrl ? (
          // Remote fixture art intentionally uses a plain img so the shared package has no Next.js dependency.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            alt={`${context.release.title} album artwork`}
            className="release-artwork"
            height="168"
            src={context.release.artworkUrl}
            width="168"
          />
        ) : null}
        <div>
          <p className="eyebrow">NOW IN CONTEXT</p>
          <h2>{context.release.title}</h2>
          <p className="artist-name">
            {context.artist.name} · {context.release.year}
          </p>
          <ul className="genre-list" aria-label="Genres">
            {context.genres.map((genre) => (
              <li key={genre.name}>{genre.name}</li>
            ))}
          </ul>
        </div>
      </header>

      {context.consensusBlocks.map((block) => (
        <section className="consensus-block" key={block.licensePool}>
          <p className="section-label">中文共识</p>
          {block.skippedReason ? (
            <p className="claim-text muted">
              该许可证池的来源不足两个，未生成综合观点。
            </p>
          ) : block.claims.length ? (
            <ul className="claim-list">
              {block.claims.map((claim) => {
                const claimSources = context.sources.filter((source) =>
                  claim.sourceIds.includes(source.id),
                );
                return (
                  <li className="claim-item" key={claim.id}>
                    <p className="claim-text">{claim.text}</p>
                    <p className="claim-sources">
                      基于{" "}
                      {claimSources
                        .map((source) => source.publication)
                        .join("、")}
                    </p>
                  </li>
                );
              })}
            </ul>
          ) : null}
          <p className="attribution">
            {block.attribution} ·{" "}
            <SourceLink href={block.license.url}>{block.license.id}</SourceLink>
          </p>
        </section>
      ))}

      {context.sourceSummaries.length ? (
        <section className="source-summaries">
          <p className="section-label">单来源归纳</p>
          <div className="source-summary-grid">
            {context.sourceSummaries.map((summary) => (
              <article className="source-summary" key={summary.source.id}>
                <strong>{summary.source.publication}</strong>
                <ul className="claim-list">
                  {summary.claims.map((claim) => (
                    <li className="claim-item" key={claim.id}>
                      <p className="claim-text">{claim.text}</p>
                    </li>
                  ))}
                </ul>
                <p className="attribution">
                  {summary.attribution} ·{" "}
                  <SourceLink href={summary.license.url}>
                    {summary.license.id}
                  </SourceLink>
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <div className="section-heading">
          <p className="section-label">来源摘录</p>
          <span>{context.sources.length} 篇</span>
        </div>
        <div className="source-grid">
          {context.sources.map((source) => {
            const excerpt = context.excerpts.find(
              (item) => item.sourceId === source.id,
            );
            return (
              <article className="source-card" key={source.id}>
                <div className="source-meta">
                  <strong>{source.publication}</strong>
                  {source.score ? (
                    <span>
                      {source.score.value}/{source.score.scale}
                    </span>
                  ) : null}
                </div>
                <h3>{source.title}</h3>
                {excerpt ? <p>{excerpt.text}</p> : null}
                <SourceLink href={source.url}>查看原文</SourceLink>
              </article>
            );
          })}
        </div>
      </section>
    </article>
  );
}
