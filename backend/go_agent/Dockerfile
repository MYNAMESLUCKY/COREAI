# syntax=docker/dockerfile:1

FROM golang:1.22 AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . ./
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/agent ./cmd/agent

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=build /out/agent /app/agent
ENV AGENT_HOST=0.0.0.0
ENV AGENT_PORT=8080
EXPOSE 8080
ENTRYPOINT ["/app/agent","--mode","api","--host","0.0.0.0","--port","8080"]
