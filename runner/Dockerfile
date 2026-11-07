FROM node:24-bookworm-slim AS node
FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*
RUN groupadd --gid 10000 hapic-runner && useradd --uid 10000 --gid 10000 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin hapic-runner
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ENV HOME=/tmp NPM_CONFIG_CACHE=/workspace/.npm-cache PIP_CACHE_DIR=/workspace/.pip-cache
WORKDIR /workspace
USER 10000:10000
CMD ["python", "--version"]
