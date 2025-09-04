"""Centralized event name constants.

This module defines all Redis event identifiers used across the
application. Using constants avoids typos when publishing or
subscribing to events.
"""

# PPE related events
PPE_VIOLATION = "ppe_violation"

# Authentication events
FAILED_LOGIN = "failed_login"

# Face recognition events
FACE_UNRECOGNIZED = "face_unrecognized"
FACE_BLURRY = "face_blurry"

# Gate pass events
GATEPASS_APPROVED = "gatepass_approved"
GATEPASS_REJECTED = "gatepass_rejected"
GATEPASS_OVERDUE = "gatepass_overdue"

# Visitor management events
VISITOR_REGISTERED = "visitor_registered"

# Camera/streaming events
CAMERA_OFFLINE = "camera_offline"

# System monitoring events
NETWORK_USAGE_HIGH = "network_usage_high"
NETWORK_USAGE_LOW = "network_usage_low"
DISK_SPACE_LOW = "disk_space_low"
SYSTEM_CPU_HIGH = "system_cpu_high"

# All events set for easy validation
ALL_EVENTS = {
    PPE_VIOLATION,
    FAILED_LOGIN,
    FACE_UNRECOGNIZED,
    FACE_BLURRY,
    GATEPASS_APPROVED,
    GATEPASS_REJECTED,
    GATEPASS_OVERDUE,
    VISITOR_REGISTERED,
    CAMERA_OFFLINE,
    NETWORK_USAGE_HIGH,
    NETWORK_USAGE_LOW,
    DISK_SPACE_LOW,
    SYSTEM_CPU_HIGH,
}

__all__ = [
    "PPE_VIOLATION",
    "FAILED_LOGIN",
    "FACE_UNRECOGNIZED",
    "FACE_BLURRY",
    "GATEPASS_APPROVED",
    "GATEPASS_REJECTED",
    "GATEPASS_OVERDUE",
    "VISITOR_REGISTERED",
    "CAMERA_OFFLINE",
    "NETWORK_USAGE_HIGH",
    "NETWORK_USAGE_LOW",
    "DISK_SPACE_LOW",
    "SYSTEM_CPU_HIGH",
    "ALL_EVENTS",
]
