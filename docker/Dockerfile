# Two stages, one image: Node builds the PWA, Python serves it alongside the
# JSON API. Single container by design -- SQLite is one file to back up, and
# splitting the client behind a second image would buy CORS and a compose
# network for no benefit at one user.

FROM node:20-alpine AS client
WORKDIR /build
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build


FROM python:3.12-slim AS runtime

# uvloop and httptools come from uvicorn[standard]; argon2-cffi needs no
# compiler on a wheel-provided platform, so no build toolchain is installed.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PF_DATA_DIR=/data \
    PF_STATIC_DIR=/app/client/dist

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
        "fastapi>=0.110" "uvicorn[standard]>=0.27" \
        "argon2-cffi>=23" "python-multipart>=0.0.9"

COPY server/ ./server/
COPY db/ ./db/
COPY --from=client /build/dist ./client/dist

# The database and the credentials file live on the volume, so both survive
# an image rebuild -- and a database restored from backup does not bring an
# old passcode with it, because they are separate files.
VOLUME ["/data"]
EXPOSE 8000

# 0.0.0.0 on purpose: no code distinguishes LAN from tailnet traffic, so
# moving to Tailscale is purely a deployment change. TLS is terminated
# outside the container (`tailscale serve`), which is also what supplies the
# certificate the PWA needs to register a service worker.
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
