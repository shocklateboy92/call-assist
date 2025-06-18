"""Constants for Call Assist integration."""

DOMAIN = "call_assist"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"

# Default values
DEFAULT_HOST = "call-assist-addon"
DEFAULT_PORT = 50051

# Entity types
ENTITY_TYPE_CALL_STATION = "call_station"
ENTITY_TYPE_CONTACT = "contact"

# Call states
CALL_STATE_IDLE = "idle"
CALL_STATE_RINGING = "ringing"
CALL_STATE_IN_CALL = "in_call"
CALL_STATE_UNAVAILABLE = "unavailable"

# Contact availability states
CONTACT_AVAILABILITY_ONLINE = "online"
CONTACT_AVAILABILITY_OFFLINE = "offline"
CONTACT_AVAILABILITY_BUSY = "busy"
CONTACT_AVAILABILITY_UNKNOWN = "unknown"

# Service names
SERVICE_MAKE_CALL = "make_call"
SERVICE_END_CALL = "end_call"
SERVICE_ACCEPT_CALL = "accept_call"
SERVICE_ADD_CONTACT = "add_contact"
SERVICE_REMOVE_CONTACT = "remove_contact"

# Event names
EVENT_CALL_ASSIST_CALL_EVENT = "call_assist_call_event"
EVENT_CALL_ASSIST_CONTACT_EVENT = "call_assist_contact_event"