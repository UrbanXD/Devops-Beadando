FROM node:22-alpine AS development

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install --global npm@12.2.2
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM node:22-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install --global npm@12.2.2 \
    && npm ci

COPY . .
RUN npm run build

FROM nginx:1.31.8-alpine3.24-slim

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html

USER nginx
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
