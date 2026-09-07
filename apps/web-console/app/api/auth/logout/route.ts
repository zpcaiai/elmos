export { POST } from "./_route";

// Next.js statically analyzes route segment config and does not accept these
// fields through a re-export, even when the handler module declares them.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
