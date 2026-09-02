FROM docker.m.daocloud.io/library/node:20-alpine AS build
WORKDIR /src
COPY package.json .
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

FROM docker.m.daocloud.io/library/nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
