import grpc
from grpc_health.v1 import health_pb2, health_pb2_grpc


class HealthService(health_pb2_grpc.HealthServicer):
    def __init__(self):
        self._status = health_pb2.HealthCheckResponse.SERVING

    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(status=self._status)

    def Watch(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "Watch is not implemented in MVP")