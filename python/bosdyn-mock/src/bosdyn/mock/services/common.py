"""Shared helpers for the mock services."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from google.protobuf import timestamp_pb2

from bosdyn.api import header_pb2


def now_timestamp() -> timestamp_pb2.Timestamp:
    ts = timestamp_pb2.Timestamp()
    ts.FromDatetime(datetime.now(timezone.utc))
    return ts


def build_response_header(request: Optional[object]) -> header_pb2.ResponseHeader:
    """Create a minimal ResponseHeader that mirrors the incoming RequestHeader."""
    header = header_pb2.ResponseHeader()
    if request is not None and hasattr(request, "header") and request.header is not None:
        header.request_header.CopyFrom(request.header)
    now = now_timestamp()
    header.request_received_timestamp.CopyFrom(now)
    header.response_timestamp.CopyFrom(now)
    return header
