"""gRPC server that exposes the mock services."""
from __future__ import annotations

import logging
from concurrent import futures
from typing import Dict, Iterable, Optional

import grpc

from bosdyn.api import (auth_service_pb2_grpc, directory_pb2,
                        directory_registration_service_pb2_grpc, directory_service_pb2_grpc,
                        estop_service_pb2_grpc, lease_service_pb2_grpc, power_service_pb2_grpc,
                        time_sync_service_pb2_grpc)

from .state import MockRobotState
from .services import auth as auth_service
from .services import directory as directory_services
from .services import estop as estop_service
from .services import lease as lease_service
from .services import power as power_service
from .services import time_sync as time_sync_service


class MockRobotServer:
    """Creates and manages a gRPC server that mimics Spot's login flow."""

    def __init__(self,
                 host: str = "0.0.0.0",
                 port: int = 50051,
                 credentials: Optional[Dict[str, str]] = None,
                 resources: Optional[Iterable[str]] = None) -> None:
        self._host = host
        self._port = port
        self._credentials = credentials or {"admin": "password"}
        self._resources = list(resources or ["body"])
        self._state = MockRobotState(resources=self._resources, credentials=self._credentials)
        self._server: Optional[grpc.Server] = None

    @property
    def address(self) -> str:
        return f"{self._host}:{self._port}"

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Server already started")
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=32))
        directory_service_pb2_grpc.add_DirectoryServiceServicer_to_server(
            directory_services.DirectoryServiceServicer(self._state), self._server)
        directory_registration_service_pb2_grpc.add_DirectoryRegistrationServiceServicer_to_server(
            directory_services.DirectoryRegistrationServiceServicer(self._state), self._server)
        auth_service_pb2_grpc.add_AuthServiceServicer_to_server(
            auth_service.AuthServiceServicer(self._state), self._server)
        time_sync_service_pb2_grpc.add_TimeSyncServiceServicer_to_server(
            time_sync_service.TimeSyncServiceServicer(self._state), self._server)
        lease_service_pb2_grpc.add_LeaseServiceServicer_to_server(
            lease_service.LeaseServiceServicer(self._state), self._server)
        estop_service_pb2_grpc.add_EstopServiceServicer_to_server(
            estop_service.EstopServiceServicer(self._state), self._server)
        power_service_pb2_grpc.add_PowerServiceServicer_to_server(
            power_service.PowerServiceServicer(self._state), self._server)
        self._register_services()
        self._server.add_insecure_port(self.address)
        self._server.start()
        logging.info("Mock robot listening on %s", self.address)

    def block_until_shutdown(self) -> None:
        if self._server is None:
            raise RuntimeError("Server has not been started")
        self._server.wait_for_termination()

    def stop(self) -> None:
        if self._server:
            self._server.stop(grace=None)
            self._server = None

    def _register_services(self) -> None:
        endpoint = directory_pb2.Endpoint(host_ip=self._host, port=self._port)
        registrations = [
            ("directory", "bosdyn.api.DirectoryService", False),
            ("directory-registration", "bosdyn.api.DirectoryRegistrationService", False),
            ("auth", "bosdyn.api.AuthService", False),
            ("time-sync", "bosdyn.api.TimeSyncService", False),
            ("lease", "bosdyn.api.LeaseService", True),
            ("estop", "bosdyn.api.EstopService", True),
            ("power", "bosdyn.api.PowerService", True),
        ]
        for name, service_type, requires_token in registrations:
            entry = directory_pb2.ServiceEntry(name=name, type=service_type,
                                               authority=self.address,
                                               user_token_required=requires_token,
                                               liveness_timeout_secs=30.0)
            self._state.directory.upsert(entry, endpoint)
