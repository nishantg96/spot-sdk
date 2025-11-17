# bosdyn-mock

`bosdyn-mock` provides a small gRPC server that mimics the minimal boot/login flow of a Spot
robot.  The mock robot exposes a DirectoryService so that existing `bosdyn.client`
applications can discover endpoints, requires clients to authenticate with `AuthService`, and
performs the TimeSync negotiation used by the official SDK.  The mock server also implements
the Lease, E-Stop, and Power services so that downstream RPCs are properly gated.

The implementation re-uses the official protobuf definitions from this repository.  The
packaged modules depend on the `bosdyn-api` wheel that ships with the SDK, which already
contains the generated message and service classes from `protos/bosdyn/api/*.proto`.

## Running the server

```
pip install --no-deps prebuilt/bosdyn_api-5.0.1.2-py3-none-any.whl
pip install -e python/bosdyn-mock
bosdyn-mock --host 0.0.0.0 --port 50051 --username admin --password insecure
```

The command starts all mock services on a single port.  Each service registers with the
DirectoryService so that `bosdyn.client` can connect without any special configuration.
