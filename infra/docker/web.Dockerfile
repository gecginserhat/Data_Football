# Kurgu web (Next.js). Geliştirmede repo volume ile bağlanır; node_modules konteyner içinde kurulur.
FROM node:22-bookworm-slim AS base
RUN corepack enable
WORKDIR /repo

FROM base AS dev
ENV NEXT_TELEMETRY_DISABLED=1
CMD ["sh", "-c", "pnpm install --frozen-lockfile && pnpm --filter @kurgu/web dev"]

FROM base AS build
COPY . .
RUN pnpm install --frozen-lockfile && pnpm --filter @kurgu/web build

FROM node:22-bookworm-slim AS prod
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/web/server.js"]
