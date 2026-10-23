# Local trace storage

Compose runs Jaeger all-in-one 1.76 with OTLP gRPC on the internal network at
`jaeger:4317`, and the UI on [localhost:16686](http://localhost:16686).
Badger storage persists to `jaeger-data`; `make clean` removes it alongside demo data.
This single-node storage is for local investigation, not production availability.
The API and worker use the same collector, with trace context carried through the database.

Image and storage flags follow [Jaeger deployment documentation](https://www.jaegertracing.io/docs/1.76/deployment/).
Jaeger v1 is retained here for its small local all-in-one deployment; evaluate a supported
Jaeger v2 deployment and storage backend before public operation.
