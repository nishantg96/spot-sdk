"""Directory service implementations."""
from __future__ import annotations

from bosdyn.api import (directory_pb2, directory_registration_pb2,
                        directory_registration_service_pb2_grpc, directory_service_pb2_grpc)

from ..state import MockRobotState
from .common import build_response_header


class DirectoryServiceServicer(directory_service_pb2_grpc.DirectoryServiceServicer):
    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def ListServiceEntries(self, request, context):  # pylint: disable=unused-argument
        response = directory_pb2.ListServiceEntriesResponse()
        response.header.CopyFrom(build_response_header(request))
        response.service_entries.extend(self._state.directory.list_entries())
        return response

    def GetServiceEntry(self, request, context):  # pylint: disable=unused-argument
        response = directory_pb2.GetServiceEntryResponse()
        response.header.CopyFrom(build_response_header(request))
        registration = self._state.directory.get(request.service_name)
        if registration is None:
            response.status = directory_pb2.GetServiceEntryResponse.STATUS_NONEXISTENT_SERVICE
            return response
        response.status = directory_pb2.GetServiceEntryResponse.STATUS_OK
        response.service_entry.CopyFrom(registration.entry)
        return response


class DirectoryRegistrationServiceServicer(
        directory_registration_service_pb2_grpc.DirectoryRegistrationServiceServicer):

    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def RegisterService(self, request, context):  # pylint: disable=unused-argument
        response = directory_registration_pb2.RegisterServiceResponse()
        response.header.CopyFrom(build_response_header(request))
        status = self._state.directory.register(request.service_entry, request.endpoint)
        response.status = status
        return response

    def UnregisterService(self, request, context):  # pylint: disable=unused-argument
        response = directory_registration_pb2.UnregisterServiceResponse()
        response.header.CopyFrom(build_response_header(request))
        response.status = self._state.directory.unregister(request.service_name)
        return response

    def UpdateService(self, request, context):  # pylint: disable=unused-argument
        response = directory_registration_pb2.UpdateServiceResponse()
        response.header.CopyFrom(build_response_header(request))
        if not self._state.directory.exists(request.service_entry.name):
            response.status = directory_registration_pb2.UpdateServiceResponse.STATUS_NONEXISTENT_SERVICE
            return response
        self._state.directory.upsert(request.service_entry, request.endpoint)
        response.status = directory_registration_pb2.UpdateServiceResponse.STATUS_OK
        return response
