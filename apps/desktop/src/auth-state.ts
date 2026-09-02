/**
 * The minimal login state the renderer may observe. It deliberately carries no
 * token or raw identity — only whether a session is present — so the renderer
 * can never leak a credential.
 */
export type LoginState = { status: "signed-out" } | { status: "signed-in" };
