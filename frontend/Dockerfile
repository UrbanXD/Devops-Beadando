FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install --global npm@12.2.2
RUN npm ci

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
