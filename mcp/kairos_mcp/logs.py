"""JSON log lines without content or credentials: an event name and a few known scalar fields."""
import json
import logging
import sys
import time

LOGGER = logging.getLogger('kairos_mcp')
FIELDS = frozenset({'method', 'status', 'reason', 'tool', 'attempt', 'duration_ms'})
_MARK = '_kairos_mcp_handler'


class JsonFormatter(logging.Formatter):
    def format(self, record):
        line = {'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(record.created)), 'level': record.levelname.lower(),
                'event': getattr(record, 'kairos_event', record.getMessage())}
        line.update(getattr(record, 'kairos_fields', {}))
        return json.dumps(line, ensure_ascii=False, sort_keys=True)


def configure_logging(stream=None, level=logging.INFO):
    """One JSON handler on the `kairos_mcp` logger; `httpx`, `httpcore` and `mcp` stay at WARNING so that no request line is written."""
    ours = [handler for handler in LOGGER.handlers if getattr(handler, _MARK, False)]
    if ours:
        if stream is not None:
            ours[0].setStream(stream)  # one handler, pointed at the stream of the latest call
    else:
        handler = logging.StreamHandler(stream or sys.stderr)
        handler.setFormatter(JsonFormatter())
        setattr(handler, _MARK, True)
        LOGGER.addHandler(handler)
    LOGGER.setLevel(level)
    LOGGER.propagate = False
    for name in ('httpx', 'httpcore', 'mcp'):
        logging.getLogger(name).setLevel(logging.WARNING)


def log_event(event, level='info', **fields):
    """Only the known fields are written: free text (a message, a path, a header) cannot reach a log line."""
    known = {key: value for key, value in fields.items() if key in FIELDS and isinstance(value, (str, int, float, bool))}
    LOGGER.log(getattr(logging, level.upper(), logging.INFO), event, extra={'kairos_event': event, 'kairos_fields': known})
