import { redirect } from "next/navigation";

// The Web surface is auth-only now: the root points at the login page. The
// music product lives in the desktop companion, not here.
export default function Page() {
  redirect("/login");
}
