import { musicContextSchema, type MusicContext } from "./index";
import nfrContext from "./nfr.json";

// The display fixture is the shared contract fixture: Python's ingest pipeline
// produces `nfr.json`, and Zod re-validates it here so the two boundaries cannot
// silently drift. The web and desktop renderers import this value.
export const featuredContext: MusicContext =
  musicContextSchema.parse(nfrContext);
