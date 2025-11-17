"""AuthService implementation."""
from __future__ import annotations

from bosdyn.api import auth_pb2, auth_service_pb2_grpc

from ..state import MockRobotState
from .common import build_response_header


class AuthServiceServicer(auth_service_pb2_grpc.AuthServiceServicer):
    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def GetAuthToken(self, request, context):  # pylint: disable=unused-argument
        response = auth_pb2.GetAuthTokenResponse()
        response.header.CopyFrom(build_response_header(request))
        if request.token:
            if self._state.auth.refresh_token(request.token):
                response.status = auth_pb2.GetAuthTokenResponse.STATUS_OK
                response.token = request.token
            else:
                response.status = auth_pb2.GetAuthTokenResponse.STATUS_INVALID_TOKEN
            return response
        status, token = self._state.auth.mint_token(request.username, request.password)
        response.status = status
        if token:
            response.token = token
        return response
