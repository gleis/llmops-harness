# syntax=docker/dockerfile:1.7
FROM golang:1.27.3-bookworm AS build
WORKDIR /src
ADD --checksum=sha256:4e5d862c6364a901ecbd8d6632ccc9bd7d2defd48f4a6affa094dbaab5d6dd8f https://github.com/jaegertracing/jaeger/archive/d723f91447f29a345c288f37eb8d1ce7807bc0be.tar.gz /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /src
COPY jaeger.go.mod go.mod
COPY jaeger.go.sum go.sum
ADD --checksum=sha256:67ba4100efe0c24f59a776e2e843eae39a4a5b1b8ee6f141e9a6801c8e51141c https://github.com/jaegertracing/jaeger-ui/releases/download/v2.23.0/assets.tar.gz /tmp/ui.tar.gz
RUN mkdir -p cmd/jaeger/internal/extension/jaegerquery/internal/ui/actual && \
    tar -xzf /tmp/ui.tar.gz --strip-components=3 -C cmd/jaeger/internal/extension/jaegerquery/internal/ui/actual && \
    find cmd/jaeger/internal/extension/jaegerquery/internal/ui/actual -type f -exec gzip --no-name {} \;
RUN CGO_ENABLED=0 go build -p 2 -mod=readonly -trimpath -o /out/jaeger ./cmd/jaeger
FROM scratch
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
COPY --from=build /out/jaeger /jaeger
COPY jaeger.yaml /etc/jaeger.yaml
USER 10001:10001
EXPOSE 16686 4318 13133
ENTRYPOINT ["/jaeger"]
CMD ["--config", "/etc/jaeger.yaml"]
LABEL org.opencontainers.image.version="2.23.0-security.1" org.opencontainers.image.revision="d723f91447f29a345c288f37eb8d1ce7807bc0be"
