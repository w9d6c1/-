# React 管理后台 Dockerfile (app/)
FROM node:22-alpine AS base
WORKDIR /app

ARG APP_VERSION=dev
LABEL version=$APP_VERSION
COPY package.json package-lock.json ./

# Dev Stage
FROM base AS dev
RUN npm install
COPY . .
EXPOSE 5175

# Build Stage
FROM base AS prod
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

# Production Stage
FROM nginx:1.27-alpine AS production
COPY --from=prod /app/dist /usr/share/nginx/html/app
COPY docker/nginx-app.conf /etc/nginx/conf.d/default.conf
EXPOSE 5175
