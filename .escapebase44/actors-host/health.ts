// EscapeBase44: the deploy's health probe for the actors host — run inside
// the `actors` container (`deno run --allow-net --allow-env health.ts`),
// where the host answers on its own port. Prints the host's answer; exits
// non-zero when it is not serving.
const port = Deno.env.get("EB44_ACTORS_PORT") ?? "9100";
const res = await fetch(`http://127.0.0.1:${port}/_internal/health`);
console.log(await res.text());
Deno.exit(res.ok ? 0 : 1);
