"""Tests for the isolated memory service."""

# The service derives passwords at the cost measured in T-01 (n=2^17, ~128 MB and ~0.6 s each); the suite creates hundreds of users and logins, so it runs at the cost of the earlier
# release (n=2^14). `tests/test_passwords.py` runs the real cost (`passwords.DEFAULT_PARAMS`) and says so; nothing in `passwords.py` reads this file.
from memory_platform import passwords

passwords.TARGET = (2 ** 14, 8, 1)
