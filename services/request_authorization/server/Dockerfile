FROM golang:1.22-alpine AS builder

RUN apk add --no-cache protobuf protobuf-dev

WORKDIR /build

# Install protoc plugins
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.34.2 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.4.0

# Copy module files first for cache
COPY server/app/go.mod server/app/go.sum ./
RUN go mod download

# Copy source
COPY server/app/ ./
COPY proto/ /proto/

# Generate proto stubs
RUN mkdir -p proto && \
    protoc \
    --go_out=proto --go_opt=paths=source_relative \
    --go-grpc_out=proto --go-grpc_opt=paths=source_relative \
    -I /proto \
    /proto/permit.proto

# Build
RUN CGO_ENABLED=0 go build -o /server .
FROM alpine:3.19
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /server ./server

EXPOSE 9000 9003
CMD ["./server"]
