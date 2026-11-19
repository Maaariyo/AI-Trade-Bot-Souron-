# syntax=docker/dockerfile:1
# Next.js image for the web service (development). Build context: apps/web.
FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

# Optional extra CA for TLS-intercepting proxies (see services/Dockerfile).
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then \
      cat /run/secrets/extra_ca >> /etc/ssl/certs/ca-certificates.crt; \
    fi

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]
