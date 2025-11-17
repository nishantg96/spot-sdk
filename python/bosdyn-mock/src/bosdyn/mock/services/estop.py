"""E-Stop service implementation."""
from __future__ import annotations

from bosdyn.api import estop_pb2, estop_service_pb2_grpc

from ..state import MockRobotState
from .common import build_response_header


class EstopServiceServicer(estop_service_pb2_grpc.EstopServiceServicer):
    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def RegisterEstopEndpoint(self, request, context):  # pylint: disable=unused-argument
        response = estop_pb2.RegisterEstopEndpointResponse()
        response.header.CopyFrom(build_response_header(request))
        status, endpoint = self._state.estop.register(request)
        response.status = status
        if endpoint:
            response.new_endpoint.CopyFrom(endpoint)
        response.request.CopyFrom(request)
        return response

    def DeregisterEstopEndpoint(self, request, context):  # pylint: disable=unused-argument
        response = estop_pb2.DeregisterEstopEndpointResponse()
        response.header.CopyFrom(build_response_header(request))
        response.status = self._state.estop.deregister(request)
        return response

    def EstopCheckIn(self, request, context):  # pylint: disable=unused-argument
        response = estop_pb2.EstopCheckInResponse()
        response.header.CopyFrom(build_response_header(request))
        status, challenge = self._state.estop.check_in(request)
        response.status = status
        response.request.CopyFrom(request)
        if challenge is not None:
            response.challenge = challenge
        return response

    def GetEstopConfig(self, request, context):  # pylint: disable=unused-argument
        response = estop_pb2.GetEstopConfigResponse()
        response.header.CopyFrom(build_response_header(request))
        response.config.CopyFrom(self._state.estop.config)
        return response

    def SetEstopConfig(self, request, context):  # pylint: disable=unused-argument
        response = estop_pb2.SetEstopConfigResponse()
        response.header.CopyFrom(build_response_header(request))
        response.status = self._state.estop.set_config(request)
        return response

    def GetEstopSystemStatus(self, request, context):  # pylint: disable=unused-argument
        response = estop_pb2.GetEstopSystemStatusResponse()
        response.header.CopyFrom(build_response_header(request))
        response.status.CopyFrom(self._state.estop.system_status())
        return response
