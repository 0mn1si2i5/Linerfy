import { getFeaturedContext } from "../lib/catalog";

import { HomePage } from "./home-page";

// The page reads live catalog data from Supabase on every request, so it must
// not be statically prerendered at build time.
export const dynamic = "force-dynamic";

export default async function Page() {
  const result = await getFeaturedContext();
  return <HomePage result={result} />;
}
