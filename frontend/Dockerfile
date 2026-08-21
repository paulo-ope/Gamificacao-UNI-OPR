FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app

ARG INTERNAL_API_URL=http://backend:8000
ARG NEXT_PUBLIC_API_URL=
ENV INTERNAL_API_URL=$INTERNAL_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV INTERNAL_API_URL=http://backend:8000
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# `output: "standalone"` (next.config.mjs) faz o build já rastrear e copiar só as dependências de
# node_modules realmente usadas em runtime (tracing de import), num server.js autocontido - corta
# a imagem final de ~1,2GB (node_modules inteiro) pra uma fração disso. .next/standalone já inclui
# uma cópia própria de next.config.mjs/package.json - não precisa copiar de novo.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]
