/**
 * The minimal login state the renderer may observe. It deliberately carries no
 * token or raw identity — only whether a session is present — so the renderer
 * can never leak a credential.
 */
export type LoginState = { status: "signed-out" } | { status: "signed-in" };

/**
 * The outcome of a sign-in attempt. Success is reported as the resulting
 * `LoginState`; a failure carries a user-facing message. The token itself is
 * never part of this type, so it cannot cross the process boundary.
 */
export type SignInResult =
  | { status: "signed-in" }
  | { status: "signed-out" }
  | { status: "error"; message: string };
