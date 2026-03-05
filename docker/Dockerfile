FROM nginx:1.25-alpine

RUN apk add --no-cache curl

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf      /etc/nginx/nginx.conf
COPY conf.d/         /etc/nginx/conf.d/

# Self-signed cert placeholder (replace with real cert in production)
RUN mkdir -p /etc/nginx/ssl && \
    apk add --no-cache openssl && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout /etc/nginx/ssl/selfsigned.key \
      -out    /etc/nginx/ssl/selfsigned.crt \
      -subj "/C=US/ST=State/L=City/O=DataVault/CN=localhost"

EXPOSE 80 443

HEALTHCHECK --interval=20s --timeout=5s --retries=3 \
  CMD curl -fsS http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
