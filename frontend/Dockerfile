# syntax=docker/dockerfile:1

# ---- deps & build ------------------------------------------------------
FROM node:20-alpine AS build
WORKDIR /app

# Install deps first so this layer is cached unless package*.json changes.
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# VITE_* vars are baked into the bundle at build time. Override with
# --build-arg to point at a different backend per image.
ARG VITE_API_BASE_URL=http://localhost:8000/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build:all

# ---- runtime -------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

RUN touch /run/nginx.pid \
    && chown -R nginx:nginx \
       /run/nginx.pid \
       /var/cache/nginx \
       /etc/nginx/conf.d \
       /usr/share/nginx/html

USER nginx

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
