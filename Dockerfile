# Stage 1: Build
FROM golang:1.24-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o main main.go

# Stage 2: Runtime
FROM alpine:latest
WORKDIR /root/
COPY --from=builder /app/main .
COPY asatidz.json .
EXPOSE 8080
CMD ["./main"]
