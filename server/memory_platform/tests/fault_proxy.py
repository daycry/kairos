"""A TCP proxy in front of the ephemeral PostgreSQL that a test can cut, restore or silence on command (I3 / CA-34).

It is the oracle of the failure tests of the worker and of the connection pool: the code under test connects to `proxy.dsn(...)`
instead of the database, and the test decides when the database "goes away" without stopping a real server and without waiting
for anything. The three orders take effect before they return:

* `cut()`: every open connection is closed and every new one is accepted and closed at once (the client sees
  `psycopg.OperationalError`);
* `mute()`: a new connection is accepted and then ignored, forever (a server that does not answer); the open ones are closed;
* `freeze()`: the connections that are ALREADY open stay open and stop carrying data in both directions (what a partition or a frozen host looks like to a client: the socket is alive and
  nothing ever comes back); a new connection is accepted and ignored. `thaw()` lets what was held through, in order, and closes the ones that were accepted and ignored. This is the half-open
  case, which `mute()` does not reproduce (it closes the open connections), and the oracle of the client-side plazo of the pool;
* `restore()`: the proxy forwards again; connections that were held mute are closed (the client reconnects).

It listens on 127.0.0.1 only, on a port the system chooses, and it only ever connects to the upstream it was given. It belongs to
the process that started it: `stop()` (or `with FaultProxy(...)`) closes every socket and joins every thread.
"""
from __future__ import annotations

import os
import socket
import threading

FORWARD, CUT, MUTE, FREEZE = 'forward', 'cut', 'mute', 'freeze'


def database_address() -> tuple[str, int]:
    """Host and port of the isolated test PostgreSQL (`MEMORY_TEST_DSN`, set by run_postgres.py)."""
    from psycopg.conninfo import conninfo_to_dict
    info = conninfo_to_dict(os.environ['MEMORY_TEST_DSN'])
    return info.get('host') or '127.0.0.1', int(info.get('port') or 5432)


class FaultProxy:
    def __init__(self, upstream: tuple[str, int] | None = None):
        self.upstream = upstream or database_address()
        self._lock = threading.Condition()  # a lock that can also announce an accepted connection
        self._mode = FORWARD
        self._held: set[socket.socket] = set()  # every socket this proxy owns and must close on cut/mute/stop
        self._ignored: set[socket.socket] = set()  # accepted while muted or frozen and never forwarded: what `thaw()` closes
        self._threads: list[threading.Thread] = []
        self._stopped = False
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(('127.0.0.1', 0))
        self._listener.listen(64)
        self.host, self.port = self._listener.getsockname()
        self.accepted = 0  # connections the proxy has accepted (any mode); read it after the client connected
        self._acceptor: threading.Thread | None = None

    # -- life cycle -----------------------------------------------------------------------------------------------------
    def start(self) -> 'FaultProxy':
        self._acceptor = threading.Thread(target=self._accept_loop, name='fault-proxy-accept', daemon=True)
        self._acceptor.start()
        return self

    def stop(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            self._close_held()
            self._lock.notify_all()
        try:
            self._listener.shutdown(socket.SHUT_RDWR)  # wakes accept() on Linux
        except OSError:
            pass
        self._listener.close()
        if self._acceptor:
            self._acceptor.join(timeout=10)
        for thread in list(self._threads):
            thread.join(timeout=10)

    def __enter__(self) -> 'FaultProxy':
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # -- the three orders -----------------------------------------------------------------------------------------------
    def cut(self) -> None:
        with self._lock:
            self._mode = CUT
            self._close_held()
            self._lock.notify_all()

    def mute(self) -> None:
        with self._lock:
            self._mode = MUTE
            self._close_held()
            self._lock.notify_all()

    def restore(self) -> None:
        with self._lock:
            self._mode = FORWARD
            self._close_held()
            self._lock.notify_all()

    def freeze(self) -> None:
        """Stop forwarding in both directions WITHOUT closing anything that is open; new connections are accepted and ignored."""
        with self._lock:
            self._mode = FREEZE
            self._lock.notify_all()

    def thaw(self) -> None:
        """Forward again: what was held in the pumps goes through in order; the connections accepted while frozen are closed (their clients reconnect)."""
        with self._lock:
            self._mode = FORWARD
            for sock in list(self._ignored):
                self._held.discard(sock)
                self._close(sock)
            self._ignored.clear()
            self._lock.notify_all()

    def wait_accepted(self, count: int, timeout: float = 30.0) -> bool:
        """Block until the proxy has accepted `count` connections in total (a condition, not a sleep)."""
        with self._lock:
            return self._lock.wait_for(lambda: self.accepted >= count, timeout)

    @property
    def mode(self) -> str:
        with self._lock:
            return self._mode

    def dsn(self, template: str | None = None) -> str:
        """The DSN of the test database with this proxy's address instead of the real one."""
        from psycopg.conninfo import conninfo_to_dict, make_conninfo
        info = conninfo_to_dict(template or os.environ['MEMORY_TEST_DSN'])
        info.pop('hostaddr', None)
        return make_conninfo(**{**info, 'host': self.host, 'port': self.port})

    # -- internals ------------------------------------------------------------------------------------------------------
    def _close_held(self) -> None:
        """Close every owned socket. Call with the lock held: it is what makes the orders take effect before they return."""
        for sock in list(self._held):
            self._close(sock)
        self._held.clear()
        self._ignored.clear()

    @staticmethod
    def _close(sock: socket.socket) -> None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass

    def _accept_loop(self) -> None:
        while True:
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            with self._lock:
                self.accepted += 1
                self._lock.notify_all()
                if self._stopped or self._mode == CUT:
                    self._close(client)
                    continue
                self._held.add(client)
                mode = self._mode
                if mode in (MUTE, FREEZE):
                    self._ignored.add(client)
            if mode in (MUTE, FREEZE):
                continue  # accepted and ignored; cut/mute/restore/stop close it (and thaw, for the frozen ones)
            thread = threading.Thread(target=self._session, args=(client,), name='fault-proxy-session', daemon=True)
            self._threads.append(thread)
            thread.start()

    def _session(self, client: socket.socket) -> None:
        try:
            upstream = socket.create_connection(self.upstream, timeout=10)
            upstream.settimeout(None)
        except OSError:
            with self._lock:
                self._held.discard(client)
            self._close(client)
            return
        with self._lock:
            if self._stopped or client not in self._held or self._mode not in (FORWARD, FREEZE):
                self._close(upstream)  # a cut/mute/restore closed the client while the upstream was being opened
                return
            self._held.add(upstream)
        pump = threading.Thread(target=self._pump, args=(upstream, client), name='fault-proxy-pump', daemon=True)
        self._threads.append(pump)
        pump.start()
        self._pump(client, upstream)
        pump.join(timeout=10)

    def _pump(self, source: socket.socket, target: socket.socket) -> None:
        try:
            while True:
                data = source.recv(65536)
                if not data:
                    break
                with self._lock:  # frozen: what arrives is held here (not lost) until thaw; a cut, a stop or a restore ends the wait
                    self._lock.wait_for(lambda: self._mode != FREEZE or self._stopped or source not in self._held)
                target.sendall(data)
        except OSError:
            pass
        finally:
            with self._lock:
                self._held.discard(source)
                self._held.discard(target)
            self._close(source)
            self._close(target)


def expire_lease(store, job_id: str) -> None:
    """Make the lease of a `running` job expire now, without waiting for it (I3 / CA-12, CA-34).

    Two columns move: `lease_until` (to the past) and `available_at` (to 1990, so the job is the first one a claim sees among whatever other tests
    left in the shared test database). `state`, `attempts`, `fence` and `worker_id` stay as the claim left them, so the next `claim_job` finds exactly
    what a worker that died mid-job leaves behind. Raises when the job is not `running` (a helper that silently did nothing would make a test pass for nothing).
    """
    with store.transaction() as c:
        row = c.execute("UPDATE memory.jobs SET lease_until=clock_timestamp()-interval '1 second', available_at=timestamptz '1990-01-01 00:00:00+00' "
                        "WHERE id=%s AND state='running' RETURNING id", (job_id,)).fetchone()
    if row is None:
        raise AssertionError(f'job {job_id} is not running: there is no lease to expire')
