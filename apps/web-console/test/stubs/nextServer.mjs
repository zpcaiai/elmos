// Minimal runtime stub of next/server for node-unit-testing route handlers.
// Handlers only construct responses via NextResponse.json and type their
// request parameter as NextRequest; a Request subclass covers both.
export class NextRequest extends Request {
  get nextUrl() {
    return new URL(this.url);
  }
}

function withHeaders(init, extra) {
  const headers = new Headers(init?.headers);
  for (const [key, value] of Object.entries(extra ?? {})) {
    if (value !== undefined) headers.set(key, value);
  }
  return headers;
}

export const NextResponse = {
  json(body, init) {
    return new Response(JSON.stringify(body), {
      ...init,
      headers: withHeaders(init, { "content-type": "application/json" }),
    });
  },
  redirect(url, status = 307) {
    return new Response(null, { status, headers: { location: String(url) } });
  },
};
