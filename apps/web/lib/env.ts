/** Read a required server-side environment variable, failing fast when it is
 *  missing. The error names the key but never its value, so no secret leaks
 *  into a log line or a rendered error. */
export function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`missing required environment variable: ${name}`);
  }
  return value;
}
