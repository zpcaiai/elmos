FROM node:24.14.0-alpine3.22@sha256:76db75ca7e7da9148ae42c92d9be12d12a8d7b03e171f18339355d8078d644a0 AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && corepack prepare pnpm@10.12.4 --activate
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM node:24.14.0-alpine3.22@sha256:76db75ca7e7da9148ae42c92d9be12d12a8d7b03e171f18339355d8078d644a0 AS runtime
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
RUN addgroup -S -g 10001 elmos \
    && adduser -S -D -H -u 10001 -G elmos elmos
COPY --from=build --chown=10001:10001 /app/package.json ./package.json
COPY --from=build --chown=10001:10001 /app/node_modules ./node_modules
COPY --from=build --chown=10001:10001 /app/.next ./.next
COPY --from=build --chown=10001:10001 /app/public ./public
USER 10001:10001
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=4 \
  CMD wget -q -O /dev/null "http://127.0.0.1:3000/api/health?probe=readiness" || exit 1
CMD ["./node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
