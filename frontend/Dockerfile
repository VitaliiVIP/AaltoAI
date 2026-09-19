# Static frontend: Vite build served by nginx. The API is a separate image
# (backend/Dockerfile); Caddy routes /api/* to it, stripping the prefix exactly
# like the dev-server proxy in vite.config.ts, so no base URL is baked in here.
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY tsconfig.json tsconfig.node.json vite.config.ts index.html ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM nginx:1.27-alpine
LABEL org.opencontainers.image.source=https://github.com/VitaliiVIP/AaltoAI
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
