FROM node:24-bookworm-slim
WORKDIR /game
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY server.js ./
COPY src/ src/
COPY public/ public/
ENV HOST=0.0.0.0 PORT=3000
USER node
EXPOSE 3000
CMD ["node", "server.js"]
