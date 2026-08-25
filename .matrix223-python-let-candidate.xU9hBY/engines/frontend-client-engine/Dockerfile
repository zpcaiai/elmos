FROM node:24.4.1-alpine3.22 AS build
WORKDIR /app
RUN corepack enable
COPY engines/frontend-client-engine/package.json engines/frontend-client-engine/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY engines/frontend-client-engine/tsconfig.json ./
COPY engines/frontend-client-engine/src ./src
COPY engines/frontend-client-engine/test ./test
RUN pnpm build

FROM node:24.4.1-alpine3.22
RUN addgroup -S -g 10001 elmos && adduser -S -D -u 10001 -G elmos elmos
WORKDIR /app
COPY engines/frontend-client-engine/package.json ./package.json
COPY --from=build /app/dist ./dist
USER 10001:10001
ENV ELMOS_FRONTEND_PORT=8088 ELMOS_FRONTEND_HOST=0.0.0.0 NODE_ENV=production
EXPOSE 8088
ENTRYPOINT ["node", "dist/src/server.js"]
