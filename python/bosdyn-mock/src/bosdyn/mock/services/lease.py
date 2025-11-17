"""Lease service implementation."""
from __future__ import annotations

from bosdyn.api import lease_pb2, lease_service_pb2_grpc

from ..state import MockRobotState
from .common import build_response_header


class LeaseServiceServicer(lease_service_pb2_grpc.LeaseServiceServicer):
    def __init__(self, state: MockRobotState) -> None:
        self._state = state

    def AcquireLease(self, request, context):  # pylint: disable=unused-argument
        response = lease_pb2.AcquireLeaseResponse()
        response.header.CopyFrom(build_response_header(request))
        client_name = request.header.client_name if request.header else "anonymous"
        status, lease, owner = self._state.leases.acquire(request.resource, client_name,
                                                          client_name)
        response.status = status
        if lease:
            response.lease.CopyFrom(lease)
        if owner:
            response.lease_owner.CopyFrom(owner)
        return response

    def TakeLease(self, request, context):  # pylint: disable=unused-argument
        response = lease_pb2.TakeLeaseResponse()
        response.header.CopyFrom(build_response_header(request))
        client_name = request.header.client_name if request.header else "anonymous"
        status, lease, owner = self._state.leases.take(request.resource, client_name,
                                                       client_name)
        response.status = status
        if lease:
            response.lease.CopyFrom(lease)
        if owner:
            response.lease_owner.CopyFrom(owner)
        return response

    def ReturnLease(self, request, context):  # pylint: disable=unused-argument
        response = lease_pb2.ReturnLeaseResponse()
        response.header.CopyFrom(build_response_header(request))
        response.status = self._state.leases.return_lease(request.lease)
        return response

    def ListLeases(self, request, context):  # pylint: disable=unused-argument
        response = lease_pb2.ListLeasesResponse()
        response.header.CopyFrom(build_response_header(request))
        resources, tree = self._state.leases.list_resources()
        response.resources.extend(resources)
        response.resource_tree.CopyFrom(tree)
        return response

    def RetainLease(self, request, context):  # pylint: disable=unused-argument
        response = lease_pb2.RetainLeaseResponse()
        response.header.CopyFrom(build_response_header(request))
        response.lease_use_result.CopyFrom(self._state.leases.retain(request.lease))
        return response
