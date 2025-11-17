"""In-memory state shared across the mock services."""
from __future__ import annotations

import random
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from bosdyn.api import (auth_pb2, directory_pb2, directory_registration_pb2, estop_pb2,
                        lease_pb2, power_pb2, time_sync_pb2)

from .services import common


@dataclass
class ServiceRegistration:
    entry: directory_pb2.ServiceEntry
    endpoint: directory_pb2.Endpoint
    last_heartbeat: datetime


class DirectoryStore:
    """Stores service entries and their heartbeats."""

    def __init__(self) -> None:
        self._services: Dict[str, ServiceRegistration] = {}
        self._lock = threading.Lock()

    def register(self, entry: directory_pb2.ServiceEntry,
                 endpoint: directory_pb2.Endpoint) -> directory_registration_pb2.RegisterServiceResponse.Status:
        record = directory_pb2.ServiceEntry()
        record.CopyFrom(entry)
        record.last_update.CopyFrom(common.now_timestamp())
        stored_endpoint = directory_pb2.Endpoint()
        stored_endpoint.CopyFrom(endpoint)
        with self._lock:
            if record.name in self._services:
                return directory_registration_pb2.RegisterServiceResponse.STATUS_ALREADY_EXISTS
            self._services[record.name] = ServiceRegistration(record, stored_endpoint,
                                                              datetime.now(timezone.utc))
        return directory_registration_pb2.RegisterServiceResponse.STATUS_OK

    def upsert(self, entry: directory_pb2.ServiceEntry,
               endpoint: directory_pb2.Endpoint) -> None:
        record = directory_pb2.ServiceEntry()
        record.CopyFrom(entry)
        record.last_update.CopyFrom(common.now_timestamp())
        stored_endpoint = directory_pb2.Endpoint()
        stored_endpoint.CopyFrom(endpoint)
        with self._lock:
            self._services[record.name] = ServiceRegistration(record, stored_endpoint,
                                                              datetime.now(timezone.utc))

    def unregister(self, name: str) -> directory_registration_pb2.UnregisterServiceResponse.Status:
        with self._lock:
            if name not in self._services:
                return directory_registration_pb2.UnregisterServiceResponse.STATUS_NONEXISTENT_SERVICE
            del self._services[name]
        return directory_registration_pb2.UnregisterServiceResponse.STATUS_OK

    def get(self, name: str) -> Optional[ServiceRegistration]:
        with self._lock:
            return self._services.get(name)

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._services

    def list_entries(self) -> List[directory_pb2.ServiceEntry]:
        with self._lock:
            entries = []
            for registration in self._services.values():
                entry = directory_pb2.ServiceEntry()
                entry.CopyFrom(registration.entry)
                entries.append(entry)
            return entries


class AuthStore:
    """Stores usernames/passwords and active auth tokens."""

    def __init__(self, credentials: Dict[str, str], ttl_seconds: int = 3600) -> None:
        self._credentials = credentials
        self._ttl = ttl_seconds
        self._tokens: Dict[str, Tuple[str, datetime]] = {}
        self._lock = threading.Lock()

    def mint_token(self, username: str, password: str) -> Tuple[auth_pb2.GetAuthTokenResponse.Status, str]:
        with self._lock:
            if not username or not password:
                return auth_pb2.GetAuthTokenResponse.STATUS_INVALID_LOGIN, ""
            if self._credentials.get(username) != password:
                return auth_pb2.GetAuthTokenResponse.STATUS_INVALID_LOGIN, ""
            token = uuid.uuid4().hex
            expiry = datetime.now(timezone.utc) + timedelta(seconds=self._ttl)
            self._tokens[token] = (username, expiry)
            return auth_pb2.GetAuthTokenResponse.STATUS_OK, token

    def validate_token(self, token: str) -> bool:
        with self._lock:
            data = self._tokens.get(token)
            if not data:
                return False
            _, expiry = data
            if expiry < datetime.now(timezone.utc):
                del self._tokens[token]
                return False
            return True

    def refresh_token(self, token: str) -> bool:
        with self._lock:
            data = self._tokens.get(token)
            if not data:
                return False
            username, _ = data
            self._tokens[token] = (username, datetime.now(timezone.utc) + timedelta(seconds=self._ttl))
            return True


@dataclass
class TimeSyncSession:
    clock_identifier: str
    samples: int = 0


class TimeSyncStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, TimeSyncSession] = {}
        self._lock = threading.Lock()

    def update(self, clock_identifier: Optional[str]) -> Tuple[str, time_sync_pb2.TimeSyncState.Status, int]:
        with self._lock:
            if not clock_identifier:
                clock_identifier = uuid.uuid4().hex
            session = self._sessions.get(clock_identifier)
            if session is None:
                session = TimeSyncSession(clock_identifier=clock_identifier)
                self._sessions[clock_identifier] = session
            session.samples += 1
            status = (time_sync_pb2.TimeSyncState.STATUS_OK
                      if session.samples > 1 else time_sync_pb2.TimeSyncState.STATUS_MORE_SAMPLES_NEEDED)
            return session.clock_identifier, status, session.samples


@dataclass
class LeaseInfo:
    lease: lease_pb2.Lease
    owner: lease_pb2.LeaseOwner
    last_check_in: datetime


class LeaseStore:
    def __init__(self, resources: Iterable[str]) -> None:
        self._epoch = uuid.uuid4().hex
        self._resource_tree = lease_pb2.ResourceTree()
        self._resource_tree.resource = "root"
        for resource in resources:
            self._resource_tree.sub_resources.add(resource=resource)
        self._leases: Dict[str, LeaseInfo] = {}
        self._sequence: Dict[str, int] = {resource: 0 for resource in resources}
        self._lock = threading.Lock()

    def acquire(self, resource: str, client_name: str,
                user_name: Optional[str]) -> Tuple[int, Optional[lease_pb2.Lease], Optional[lease_pb2.LeaseOwner]]:
        with self._lock:
            if resource not in self._sequence:
                return (lease_pb2.AcquireLeaseResponse.STATUS_INVALID_RESOURCE, None, None)
            info = self._leases.get(resource)
            if info:
                return (lease_pb2.AcquireLeaseResponse.STATUS_RESOURCE_ALREADY_CLAIMED, None,
                        info.owner)
            lease, owner = self._generate_lease(resource, client_name, user_name)
            self._leases[resource] = LeaseInfo(lease=lease, owner=owner,
                                               last_check_in=datetime.now(timezone.utc))
            return lease_pb2.AcquireLeaseResponse.STATUS_OK, lease, owner

    def take(self, resource: str, client_name: str,
             user_name: Optional[str]) -> Tuple[int, Optional[lease_pb2.Lease], Optional[lease_pb2.LeaseOwner]]:
        with self._lock:
            if resource not in self._sequence:
                return (lease_pb2.TakeLeaseResponse.STATUS_INVALID_RESOURCE, None, None)
            lease, owner = self._generate_lease(resource, client_name, user_name)
            self._leases[resource] = LeaseInfo(lease=lease, owner=owner,
                                               last_check_in=datetime.now(timezone.utc))
            return lease_pb2.TakeLeaseResponse.STATUS_OK, lease, owner

    def return_lease(self, lease: lease_pb2.Lease) -> int:
        with self._lock:
            info = self._leases.get(lease.resource)
            if info is None:
                return lease_pb2.ReturnLeaseResponse.STATUS_INVALID_RESOURCE
            if not self._lease_matches(info.lease, lease):
                return lease_pb2.ReturnLeaseResponse.STATUS_NOT_ACTIVE_LEASE
            del self._leases[lease.resource]
            return lease_pb2.ReturnLeaseResponse.STATUS_OK

    def retain(self, lease: lease_pb2.Lease) -> lease_pb2.LeaseUseResult:
        result = lease_pb2.LeaseUseResult()
        result.attempted_lease.CopyFrom(lease)
        with self._lock:
            info = self._leases.get(lease.resource)
            if info is None:
                result.status = lease_pb2.LeaseUseResult.STATUS_INVALID_LEASE
                return result
            result.owner.CopyFrom(info.owner)
            result.latest_known_lease.CopyFrom(info.lease)
            if not self._lease_matches(info.lease, lease):
                result.status = lease_pb2.LeaseUseResult.STATUS_OLDER
                return result
            info.last_check_in = datetime.now(timezone.utc)
            result.status = lease_pb2.LeaseUseResult.STATUS_OK
            result.previous_lease.CopyFrom(info.lease)
            return result

    def list_resources(self) -> Tuple[List[lease_pb2.LeaseResource], lease_pb2.ResourceTree]:
        with self._lock:
            resources = []
            for resource_name in self._sequence.keys():
                resource = lease_pb2.LeaseResource(resource=resource_name)
                info = self._leases.get(resource_name)
                if info:
                    resource.lease.CopyFrom(info.lease)
                    resource.lease_owner.CopyFrom(info.owner)
                resources.append(resource)
            tree = lease_pb2.ResourceTree()
            tree.CopyFrom(self._resource_tree)
            return resources, tree

    def validate(self, lease: lease_pb2.Lease) -> lease_pb2.LeaseUseResult:
        result = lease_pb2.LeaseUseResult()
        result.attempted_lease.CopyFrom(lease)
        with self._lock:
            info = self._leases.get(lease.resource)
            if info is None:
                result.status = lease_pb2.LeaseUseResult.STATUS_INVALID_LEASE
                return result
            result.owner.CopyFrom(info.owner)
            result.latest_known_lease.CopyFrom(info.lease)
            if not self._lease_matches(info.lease, lease):
                result.status = lease_pb2.LeaseUseResult.STATUS_OLDER
                return result
            result.status = lease_pb2.LeaseUseResult.STATUS_OK
            result.previous_lease.CopyFrom(info.lease)
            return result

    def _generate_lease(self, resource: str, client_name: str,
                        user_name: Optional[str]) -> Tuple[lease_pb2.Lease, lease_pb2.LeaseOwner]:
        lease = lease_pb2.Lease()
        lease.resource = resource
        lease.epoch = self._epoch
        self._sequence.setdefault(resource, 0)
        self._sequence[resource] += 1
        lease.sequence.extend([self._sequence[resource]])
        lease.client_names.extend([client_name])
        owner = lease_pb2.LeaseOwner(client_name=client_name, user_name=user_name or client_name)
        return lease, owner

    @staticmethod
    def _lease_matches(active: lease_pb2.Lease, attempted: lease_pb2.Lease) -> bool:
        return (active.resource == attempted.resource and active.epoch == attempted.epoch
                and list(active.sequence) == list(attempted.sequence))


@dataclass
class EstopEndpointState:
    endpoint: estop_pb2.EstopEndpoint
    stop_level: estop_pb2.EstopStopLevel = estop_pb2.ESTOP_LEVEL_NONE
    last_challenge: Optional[int] = None
    last_check_in: Optional[datetime] = None


class EstopStore:
    def __init__(self) -> None:
        self._config = estop_pb2.EstopConfig(unique_id=uuid.uuid4().hex)
        self._endpoints: Dict[str, EstopEndpointState] = {}
        self._lock = threading.Lock()

    @property
    def config(self) -> estop_pb2.EstopConfig:
        with self._lock:
            config = estop_pb2.EstopConfig()
            config.CopyFrom(self._config)
            for state in self._endpoints.values():
                config.endpoints.add().CopyFrom(state.endpoint)
            return config

    def register(self, request: estop_pb2.RegisterEstopEndpointRequest
                 ) -> Tuple[estop_pb2.RegisterEstopEndpointResponse.Status, Optional[estop_pb2.EstopEndpoint]]:
        with self._lock:
            if request.target_config_id and request.target_config_id != self._config.unique_id:
                return (estop_pb2.RegisterEstopEndpointResponse.STATUS_CONFIG_MISMATCH, None)
            endpoint = estop_pb2.EstopEndpoint()
            endpoint.CopyFrom(request.new_endpoint)
            endpoint.unique_id = uuid.uuid4().hex
            state = EstopEndpointState(endpoint=endpoint)
            self._endpoints[endpoint.unique_id] = state
            return estop_pb2.RegisterEstopEndpointResponse.STATUS_SUCCESS, endpoint

    def deregister(self, request: estop_pb2.DeregisterEstopEndpointRequest
                   ) -> estop_pb2.DeregisterEstopEndpointResponse.Status:
        with self._lock:
            uid = request.target_endpoint.unique_id
            if uid not in self._endpoints:
                return estop_pb2.DeregisterEstopEndpointResponse.STATUS_ENDPOINT_UNKNOWN
            del self._endpoints[uid]
            return estop_pb2.DeregisterEstopEndpointResponse.STATUS_SUCCESS

    def check_in(self, request: estop_pb2.EstopCheckInRequest
                 ) -> Tuple[estop_pb2.EstopCheckInResponse.Status, Optional[int]]:
        with self._lock:
            uid = request.endpoint.unique_id
            state = self._endpoints.get(uid)
            if state is None:
                return estop_pb2.EstopCheckInResponse.STATUS_ENDPOINT_UNKNOWN, None
            if state.last_challenge is not None and request.response != state.last_challenge:
                return (estop_pb2.EstopCheckInResponse.STATUS_INCORRECT_CHALLENGE_RESPONSE, None)
            state.stop_level = request.stop_level
            state.last_check_in = datetime.now(timezone.utc)
            challenge = random.getrandbits(31)
            state.last_challenge = challenge
            return estop_pb2.EstopCheckInResponse.STATUS_OK, challenge

    def system_status(self) -> estop_pb2.EstopSystemStatus:
        with self._lock:
            status = estop_pb2.EstopSystemStatus()
            stop_level = estop_pb2.ESTOP_LEVEL_NONE
            for state in self._endpoints.values():
                status_entry = status.endpoints.add()
                status_entry.endpoint.CopyFrom(state.endpoint)
                status_entry.stop_level = state.stop_level
                status_entry.time_since_valid_response.FromSeconds(0)
                stop_level = max(stop_level, state.stop_level)
            status.stop_level = stop_level
            status.stop_level_details = "Mock estop status"
            return status

    def set_config(self, request: estop_pb2.SetEstopConfigRequest
                   ) -> estop_pb2.SetEstopConfigResponse.Status:
        with self._lock:
            if request.target_config_id and request.target_config_id != self._config.unique_id:
                return estop_pb2.SetEstopConfigResponse.STATUS_CONFIG_MISMATCH
            self._config.CopyFrom(request.config)
            return estop_pb2.SetEstopConfigResponse.STATUS_SUCCESS


class PowerStore:
    def __init__(self, lease_store: LeaseStore) -> None:
        self._lease_store = lease_store
        self._commands: Dict[int, power_pb2.PowerCommandStatus] = {}
        self._command_counter = 0
        self._lock = threading.Lock()

    def issue_command(self, request: power_pb2.PowerCommandRequest
                      ) -> Tuple[lease_pb2.LeaseUseResult, power_pb2.PowerCommandStatus, int]:
        lease_result = self._lease_store.validate(request.lease)
        if lease_result.status != lease_pb2.LeaseUseResult.STATUS_OK:
            return lease_result, power_pb2.STATUS_UNKNOWN, 0
        with self._lock:
            self._command_counter += 1
            command_id = self._command_counter
            status = power_pb2.STATUS_SUCCESS
            self._commands[command_id] = status
            return lease_result, status, command_id

    def get_feedback(self, command_id: int) -> power_pb2.PowerCommandStatus:
        with self._lock:
            return self._commands.get(command_id, power_pb2.STATUS_UNKNOWN)


class MockRobotState:
    """Container for all of the mock server's shared state."""

    def __init__(self, resources: Iterable[str], credentials: Dict[str, str]) -> None:
        self.directory = DirectoryStore()
        self.auth = AuthStore(credentials)
        self.time_sync = TimeSyncStore()
        self.leases = LeaseStore(resources=resources)
        self.estop = EstopStore()
        self.power = PowerStore(self.leases)

