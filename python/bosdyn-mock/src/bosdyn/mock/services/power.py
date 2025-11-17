"""Power service implementation."""
from __future__ import annotations

import grpc

from bosdyn.api import power_pb2, power_service_pb2_grpc

from ..state import MockRobotState
from .common import build_response_header


class PowerServiceServicer(power_service_pb2_grpc.PowerServiceServicer):
    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def PowerCommand(self, request, context):  # pylint: disable=unused-argument
        response = power_pb2.PowerCommandResponse()
        response.header.CopyFrom(build_response_header(request))
        lease_result, status, command_id = self._state.power.issue_command(request)
        response.lease_use_result.CopyFrom(lease_result)
        response.status = status
        response.power_command_id = command_id
        return response

    def PowerCommandFeedback(self, request, context):  # pylint: disable=unused-argument
        response = power_pb2.PowerCommandFeedbackResponse()
        response.header.CopyFrom(build_response_header(request))
        response.status = self._state.power.get_feedback(request.power_command_id)
        return response

    def FanPowerCommand(self, request, context):  # pylint: disable=unused-argument
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "Fan power is not implemented in the mock server")

    def FanPowerCommandFeedback(self, request, context):  # pylint: disable=unused-argument
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "Fan power is not implemented in the mock server")

    def ResetSafetyStop(self, request, context):  # pylint: disable=unused-argument
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "Safety stop reset is not implemented in the mock server")
