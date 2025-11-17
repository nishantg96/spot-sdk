"""TimeSync service."""
from __future__ import annotations

from google.protobuf import duration_pb2

from bosdyn.api import time_sync_pb2, time_sync_service_pb2_grpc

from ..state import MockRobotState
from .common import build_response_header, now_timestamp


class TimeSyncServiceServicer(time_sync_service_pb2_grpc.TimeSyncServiceServicer):
    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def TimeSyncUpdate(self, request, context):  # pylint: disable=unused-argument
        response = time_sync_pb2.TimeSyncUpdateResponse()
        response.header.CopyFrom(build_response_header(request))
        clock_identifier, status, samples = self._state.time_sync.update(request.clock_identifier)
        response.clock_identifier = clock_identifier
        response.state.status = status
        response.state.measurement_time.CopyFrom(now_timestamp())
        response.state.best_estimate.round_trip_time.CopyFrom(_zero_duration())
        response.state.best_estimate.clock_skew.CopyFrom(_zero_duration())
        if samples > 1:
            response.previous_estimate.round_trip_time.CopyFrom(_zero_duration())
            response.previous_estimate.clock_skew.CopyFrom(_zero_duration())
        return response


def _zero_duration() -> duration_pb2.Duration:
    duration = duration_pb2.Duration()
    duration.FromSeconds(0)
    return duration
