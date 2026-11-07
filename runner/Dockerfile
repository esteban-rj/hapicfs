FROM node:24-bookworm-slim AS node
FROM python:3.14-slim
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ENV HOME=/tmp NPM_CONFIG_CACHE=/workspace/.npm-cache PIP_CACHE_DIR=/workspace/.pip-cache
WORKDIR /workspace
USER 10000:10000
CMD ["python", "--version"]
