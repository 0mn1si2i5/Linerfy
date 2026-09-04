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

export function MusicContextCard({
  context,
  showReleaseHeader = true,
}: {
  context: MusicContext;
  showReleaseHeader?: boolean;
}) {
  return (
    <article className="context-card">
      {showReleaseHeader ? (
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
      ) : context.genres.length ? (
        <ul className="genre-list context-genres" aria-label="Genres">
          {context.genres.map((genre) => (
            <li key={genre.name}>{genre.name}</li>
          ))}
        </ul>
      ) : null}

      {context.consensusBlocks
        .filter((block) => block.claims.length > 0)
        .map((block) => (
          <section
            aria-label="综合归纳"
            className="consensus-block"
            key={block.licensePool}
          >
            <ul className="claim-list">
              {block.claims.map((claim) => {
                const claimSources = context.sources.filter((source) =>
                  claim.sourceIds.includes(source.id),
                );
                return (
                  <li className="claim-item" key={claim.id}>
                    <p className="claim-text">{claim.text}</p>
                    <p className="claim-sources">
                      来源：
                      {claimSources
                        .map((source) => source.publication)
                        .join("、")}
                    </p>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}

      {context.sourceSummaries.length ? (
        <section aria-label="各来源归纳" className="source-summaries">
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
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section aria-label="来源">
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
                <SourceLink href={source.url}>去原文</SourceLink>
              </article>
            );
          })}
        </div>
      </section>
    </article>
  );
}
