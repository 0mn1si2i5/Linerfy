import type { MusicContext } from "@linerfy/domain";
import { LinerfyMark, MusicContextCard } from "@linerfy/ui";

export function HomePage({ context }: { context: MusicContext | null }) {
  return (
    <main>
      <nav className="site-nav" aria-label="Main navigation">
        <a className="brand" href="#top">
          <LinerfyMark />
          <span>Linerfy</span>
        </a>
        <span className="preview-pill">EARLY LISTENING</span>
      </nav>

      <section className="hero" id="top">
        <p className="eyebrow">CRITICISM, IN CONTEXT</p>
        <h1>
          不替你播放，
          <br />
          只在你想知道时出现。
        </h1>
        <p className="hero-copy">
          Linerfy 把专家乐评、社区观点、Genre
          与可追溯的中文总结，放回正在发生的聆听里。
        </p>
        <form className="search-shell" action="#featured">
          <label className="sr-only" htmlFor="music-query">
            搜索歌曲或专辑
          </label>
          <input
            id="music-query"
            name="q"
            placeholder="搜索歌曲、专辑，或粘贴音乐链接"
          />
          <button type="submit">查看语境</button>
        </form>
      </section>

      <section className="featured" id="featured">
        <div className="featured-intro">
          <p className="eyebrow">A WORKING CONTEXT</p>
          <p>第一版先证明一件事：每一句总结，都能回到它来自的乐评。</p>
        </div>
        {context ? (
          <MusicContextCard context={context} />
        ) : (
          <p className="empty-state">这张专辑还没有被覆盖。</p>
        )}
      </section>

      <footer>
        <span>Linerfy</span>
        <span>Listen first. Context when wanted.</span>
      </footer>
    </main>
  );
}
