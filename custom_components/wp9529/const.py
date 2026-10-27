"""Constants for the VSON WP9529 label printer integration."""

DOMAIN = "wp9529"
NAME_PREFIX = "9529"
MANUFACTURER = "VSON"
MODEL = "WP9529"

DEFAULT_LABEL_LENGTH = 30.0
DEFAULT_LABEL_GAP = 8.5
DEFAULT_DENSITY = "normal"

STATUS_IDLE = "idle"
STATUS_PRINTING = "printing"
STATUS_ERROR = "error"

SERVICE_PRINT_LABEL = "print_label"

ATTR_DEVICE_ID = "device_id"
ATTR_TITLE = "title"
ATTR_TEXT = "text"
ATTR_QR = "qr"
ATTR_ICON = "icon"
ATTR_COPIES = "copies"
ATTR_DENSITY = "density"
ATTR_LABEL_LENGTH = "label_length"
