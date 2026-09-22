FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY src ./src

EXPOSE 3010 9531-9538

CMD ["node", "src/server.mjs"]
