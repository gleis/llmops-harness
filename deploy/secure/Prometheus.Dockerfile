# syntax=docker/dockerfile:1.7
FROM golang:1.27.3-bookworm AS build
WORKDIR /src
ADD --checksum=sha256:5691de55569c79ac40b5ddef0336cfd13f8b50ae85e541f401af16be45b9a270 https://github.com/prometheus/prometheus/archive/e2e28adeee2c5883d000fc82aca6008cfbf7e96d.tar.gz /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
COPY prometheus.go.mod go.mod
COPY prometheus.go.sum go.sum
ADD --checksum=sha256:000a45231f6dd22a5703218aad3ee11da125c8a44d1824a27670416c07531001 https://github.com/prometheus/prometheus/releases/download/v3.16.0/prometheus-web-ui-3.16.0.tar.gz /tmp/ui.tar.gz
RUN tar -xzf /tmp/ui.tar.gz -C web/ui && SKIP_UI_BUILD=1 make assets-compress
RUN CGO_ENABLED=0 go build -p 2 -mod=readonly -trimpath -tags netgo,builtinassets -o /out/prometheus ./cmd/prometheus && \
    CGO_ENABLED=0 go build -p 2 -mod=readonly -trimpath -tags netgo,builtinassets -o /out/promtool ./cmd/promtool
FROM prom/prometheus@sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06
COPY --from=build /out/prometheus /bin/prometheus
COPY --from=build /out/promtool /bin/promtool
LABEL org.opencontainers.image.version="3.16.0-security.1" org.opencontainers.image.revision="e2e28adeee2c5883d000fc82aca6008cfbf7e96d"
