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
  const claim = context.summary.claims[0];
  const claimSources = context.sources.filter((source) =>
    claim?.sourceIds.includes(source.id),
  );

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

      {claim ? (
        <section className="consensus-block">
          <p className="section-label">中文共识</p>
          <p className="consensus-copy">{claim.text}</p>
          <p className="claim-sources">
            基于 {claimSources.map((source) => source.publication).join("、")}
          </p>
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
