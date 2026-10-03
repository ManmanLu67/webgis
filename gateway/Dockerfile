# 网关同时是默认入口和静态站点宿主：先构建前端，再把产物 COPY 进来。
# 这样默认路径只有 postgis + api + gateway 三个容器，不必为了发静态文件
# 再起一个 web 容器（宪章 C7）。

FROM node:22-bookworm-slim AS build
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml frontend/.npmrc ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM caddy:2.10-alpine
COPY gateway/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /build/dist /srv/web
EXPOSE 8080