"""Unit suite for the egress guard in ``backend/tests/conftest.py``.

Subject
-------
The deny-by-default network guard the suite's own conftest installs at module
scope, and specifically its ownership registry: ``_OWNED_ENDPOINTS``,
``_record_bound_endpoint``, ``_release_socket_endpoint``, ``_endpoint_of`` and
``_is_local_address``.

The guard admits one thing - an endpoint a **live socket in this process** bound -
and refuses everything else. Every other suite in this repository depends on that
being true, and depends on it in the negative direction: an unmocked call must
fail loudly rather than reach a real service. A guard that over-admits does not
fail any test, so the over-admissions are what this module asserts.

What is asserted
----------------
Positive, so the guard is not merely "deny all":

* a loopback listener this process bound is connectable, through
  ``socket.connect`` and through ``socket.create_connection``;
* ``socket.socketpair()`` still works, which asyncio's proactor self-pipe and
  starlette's ``TestClient`` portal both need;
* a loopback bind - by address or by name - is admitted and recorded, and an
  ``AF_UNIX`` path is bindable.

Negative, one per over-admission the registry must not make:

* **publication** - a bind to ``0.0.0.0``, to ``::``, to the empty host or to a
  routable address is **refused outright**, so the suite cannot publish a listener
  on an interface this machine shares. The registry consequently holds no
  unspecified endpoint, and the admission path carries no widening to describe
  one;

* **transport** - a UDP bind does not authorize a TCP connect on the same port,
  and the reverse;
* **address** - a bind to ``127.0.0.1`` does not authorize ``127.0.0.2``, and a
  bind to a routable address authorizes nothing at all;
* **family** - an ``AF_INET`` bind does not authorize an ``AF_INET6`` target on
  the same port, including the IPv4-mapped spelling;
* **lifetime** - closing or detaching the socket withdraws the authorization, so a
  port another process rebinds is not reachable;
* **AF_UNIX** - a path this process did not bind is refused, and a path it did
  bind is admitted only for itself;
* **re-entrancy** - the registry lock is an ``RLock``, so the weak-reference
  finalizer that releases an endpoint during garbage collection cannot deadlock a
  thread that is already inside the registry. Both cases are bounded by a timeout,
  so a regression to a plain ``Lock`` fails a test rather than hanging the run.

Isolation
---------
Every socket this module opens is bound to an ephemeral loopback port, so nothing
here collides with a concurrently running checkout, and no test connects to an
endpoint it did not bind itself. :func:`registry_is_restored` fails any test that
leaves an entry behind, because a leaked entry is a standing authorization for
every test that follows.

``AF_UNIX`` is absent from Windows builds of CPython 3.9. The ``AF_UNIX`` cases
therefore drive the classifier directly with
``AF_UNIX_FAMILY`` substituted and a stand-in socket object, which is what makes
the branch assertable on either platform.

.. seealso:: ``docs/testing/DECISION-LOG.md`` for the ownership model and the
   alternatives weighed, and ``docs/testing/TRACEABILITY-MATRIX.md`` row H4.
"""

import socket
import sys
import threading

import pytest

import tests.conftest as suite_conftest

pytestmark = pytest.mark.unit

#: Loopback address every internet socket in this module binds.
LOOPBACK_V4 = "127.0.0.1"

#: A second loopback address on the same interface, used for the address cases.
OTHER_LOOPBACK_V4 = "127.0.0.2"

#: IPv6 loopback, and the IPv4-mapped spelling of :data:`LOOPBACK_V4`.
LOOPBACK_V6 = "::1"
MAPPED_LOOPBACK_V4 = "::ffff:127.0.0.1"

#: A routable address the guard must always refuse.
ROUTABLE_HOST = "203.0.113.10"

#: Stand-in family number for the ``AF_UNIX`` cases on a platform that has none.
SUBSTITUTE_UNIX_FAMILY = -1

UNIX_PATH = "/tmp/blitzy-owned.sock"
FOREIGN_UNIX_PATH = "/tmp/blitzy-foreign.sock"

#: Seconds the two re-entrancy cases wait before declaring a deadlock. Every
#: operation they time is a dictionary update under a lock, so a second is orders
#: of magnitude more than the work needs and short enough to fail promptly.
REENTRY_TIMEOUT = 1.0


class _StandInSocket:
    """Minimal object with the two attributes the classifier reads.

    Supports weak references, which is what :func:`_acquire_endpoint` needs, so an
    ownership entry can be registered against it without opening a real socket of
    a family this platform may not provide.
    """

    def __init__(self, family, socket_type=None):
        self.family = family
        self.type = socket_type


@pytest.fixture(autouse=True)
def registry_is_restored():
    """Fail the test if it leaves an ownership entry behind.

    A leaked entry authorizes that endpoint for the rest of the session, so the
    check runs for every test here rather than only the ones that register
    directly.
    """
    before = dict(suite_conftest._OWNED_ENDPOINTS)
    yield
    after = dict(suite_conftest._OWNED_ENDPOINTS)

    assert after == before, (
        "this test left the endpoint ownership registry changed, which "
        "authorizes those endpoints for every test that follows: "
        "{0}".format(sorted(set(after) ^ set(before)))
    )


@pytest.fixture
def bound_listener():
    """Yield a bound, listening TCP socket on an ephemeral loopback port."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((LOOPBACK_V4, 0))
    listener.listen(1)
    try:
        yield listener
    finally:
        listener.close()


@pytest.fixture
def bound_datagram_socket():
    """Yield a bound UDP socket on an ephemeral loopback port."""
    datagram = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    datagram.bind((LOOPBACK_V4, 0))
    try:
        yield datagram
    finally:
        datagram.close()


def _port_of(sock):
    """Return the port ``sock`` is bound to."""
    return sock.getsockname()[1]


def _released_loopback_port():
    """Return an ephemeral loopback port this process bound and then released.

    The port is unowned by construction, so a connect to it is refused before any
    syscall is attempted - which is what makes it safe to name in a test.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind((LOOPBACK_V4, 0))
    port = _port_of(probe)
    probe.close()
    return port


# --------------------------------------------------------------------------- #
# The guard is installed, and it is the module under test.
# --------------------------------------------------------------------------- #


def test_the_guard_module_is_the_one_pytest_loaded():
    """The conftest imported here is the same module object the guard lives in."""
    assert sys.modules["tests.conftest"] is suite_conftest


def test_binding_registers_an_endpoint(bound_listener):
    """A loopback bind is recorded, which is what a later connect is matched on."""
    endpoint = suite_conftest._endpoint_of(
        socket.AF_INET, socket.SOCK_STREAM, (LOOPBACK_V4, _port_of(bound_listener))
    )

    assert endpoint in suite_conftest._OWNED_ENDPOINTS


# --------------------------------------------------------------------------- #
# Positive: what the suite genuinely needs stays reachable.
# --------------------------------------------------------------------------- #


def test_a_listener_this_process_bound_is_connectable(bound_listener):
    """The admission the suite depends on: an endpoint this process owns."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect((LOOPBACK_V4, _port_of(bound_listener)))
        assert client.getpeername()[1] == _port_of(bound_listener)
    finally:
        client.close()


def test_create_connection_reaches_an_owned_listener(bound_listener):
    """``create_connection`` builds its own socket and is matched on TCP only."""
    connection = socket.create_connection((LOOPBACK_V4, _port_of(bound_listener)))
    try:
        assert connection.getpeername()[1] == _port_of(bound_listener)
    finally:
        connection.close()


def test_socketpair_still_works():
    """asyncio's self-pipe and starlette's portal both open one of these."""
    left, right = socket.socketpair()
    try:
        left.send(b"x")
        assert right.recv(1) == b"x"
    finally:
        left.close()
        right.close()


@pytest.mark.parametrize("host", ["0.0.0.0", ""])
def test_a_wildcard_bind_is_refused(host):
    """A bind to every local interface never happens, so it authorizes nothing.

    ``0.0.0.0`` and the empty host make the same request: accept connections on
    every interface this machine has. This host runs many clones of this
    repository at once, so a listener there is reachable by all of them and by
    anything else that can route to the machine, which is neither offline nor
    isolated.

    The guard refuses the ``bind`` itself rather than declining to record it, so
    the socket is never published and no widening is needed in the admission path
    to describe what such a socket would have answered on.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError) as excinfo:
            listener.bind((host, 0))

        reported = str(excinfo.value)

        assert "socket.bind" in reported
        assert repr((host, 0)) in reported
    finally:
        listener.close()


def test_an_ipv6_wildcard_bind_is_refused():
    """``::`` is the IPv6 spelling of the same request, and is refused too."""
    listener = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            listener.bind(("::", 0))
    finally:
        listener.close()


def test_a_bind_to_a_routable_address_is_refused():
    """A routable bind is refused one layer earlier than it used to be.

    The classifier used to record nothing for such a bind, which left the socket
    bound and reachable while merely unauthorized as a connect *target*. Refusing
    the call means the listener never exists at all.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            listener.bind((ROUTABLE_HOST, 0))
    finally:
        listener.close()


@pytest.mark.parametrize("host", [LOOPBACK_V4, OTHER_LOOPBACK_V4, "localhost"])
def test_a_loopback_bind_is_admitted(host):
    """The permitted side, so the refusal above is not a deny-all."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind((host, 0))

        assert suite_conftest._is_port_owned_by_this_process(_port_of(listener)) is True
    finally:
        listener.close()


def test_a_family_whose_address_cannot_be_read_is_not_bindable():
    """Classification fails closed: an unknown family is refused, not admitted."""
    assert (
        suite_conftest._is_bindable_address(
            _StandInSocket(SUBSTITUTE_UNIX_FAMILY - 1), (LOOPBACK_V4, 0)
        )
        is False
    )


def test_a_unix_path_is_bindable(unix_family):
    """An ``AF_UNIX`` path is filesystem-scoped, so it publishes nothing to a network."""
    assert (
        suite_conftest._is_bindable_address(_StandInSocket(unix_family), UNIX_PATH)
        is True
    )


# --------------------------------------------------------------------------- #
# Negative: transport cross-authorization.
# --------------------------------------------------------------------------- #


def test_a_udp_bind_does_not_authorize_tcp_on_the_same_port(bound_datagram_socket):
    """One port number carries two transports, each owned separately."""
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert (
            suite_conftest._is_local_address(
                tcp, (LOOPBACK_V4, _port_of(bound_datagram_socket))
            )
            is False
        )
    finally:
        tcp.close()


def test_a_tcp_connect_to_a_udp_owned_port_is_refused(bound_datagram_socket):
    """The classification above is what the connect guard acts on."""
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            tcp.connect((LOOPBACK_V4, _port_of(bound_datagram_socket)))
    finally:
        tcp.close()


def test_a_tcp_bind_does_not_authorize_a_datagram_send(bound_listener):
    """The reverse direction: a stream bind authorizes no datagram target."""
    datagram = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            datagram.sendto(b"x", (LOOPBACK_V4, _port_of(bound_listener)))
    finally:
        datagram.close()


# --------------------------------------------------------------------------- #
# Negative: address and family cross-authorization.
# --------------------------------------------------------------------------- #


def test_one_loopback_address_does_not_authorize_another(bound_listener):
    """``127.0.0.1`` and ``127.0.0.2`` are two addresses, not one interface."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        assert (
            suite_conftest._is_local_address(
                client, (OTHER_LOOPBACK_V4, _port_of(bound_listener))
            )
            is False
        )
    finally:
        client.close()


def test_a_connect_to_another_loopback_address_is_refused(bound_listener):
    """The same fact at the guard boundary rather than the classifier."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            client.connect((OTHER_LOOPBACK_V4, _port_of(bound_listener)))
    finally:
        client.close()


@pytest.mark.parametrize(
    "host", [LOOPBACK_V6, MAPPED_LOOPBACK_V4], ids=["ipv6-loopback", "ipv4-mapped"]
)
def test_an_ipv4_bind_does_not_authorize_an_ipv6_target(bound_listener, host):
    """A family is part of the endpoint, so the two do not share a port."""
    client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        assert (
            suite_conftest._is_local_address(client, (host, _port_of(bound_listener)))
            is False
        )
    finally:
        client.close()


def test_a_bind_to_a_routable_address_records_nothing():
    """Only a loopback or unspecified bind is recorded, so no other authorizes."""
    stand_in = _StandInSocket(socket.AF_INET, socket.SOCK_STREAM)
    stand_in.getsockname = lambda: (ROUTABLE_HOST, 4187)

    suite_conftest._record_bound_endpoint(stand_in)

    assert (
        suite_conftest._endpoint_of(
            socket.AF_INET, socket.SOCK_STREAM, (ROUTABLE_HOST, 4187)
        )
        not in suite_conftest._OWNED_ENDPOINTS
    )


def test_a_routable_target_is_refused():
    """The headline guarantee, asserted at the boundary."""
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            client.connect((ROUTABLE_HOST, 443))
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# Negative: lifetime.  A released port is not an authorization.
# --------------------------------------------------------------------------- #


def test_closing_withdraws_the_authorization():
    """The endpoint leaves the registry when the socket holding it closes."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((LOOPBACK_V4, 0))
    port = _port_of(listener)
    endpoint = suite_conftest._endpoint_of(
        socket.AF_INET, socket.SOCK_STREAM, (LOOPBACK_V4, port)
    )
    assert endpoint in suite_conftest._OWNED_ENDPOINTS

    listener.close()

    assert endpoint not in suite_conftest._OWNED_ENDPOINTS


def test_a_released_port_cannot_be_connected_to():
    """Another process may hold that number now, so it must not be reachable."""
    port = _released_loopback_port()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
            client.connect((LOOPBACK_V4, port))
    finally:
        client.close()


def test_create_connection_to_a_released_port_is_refused():
    """The out-of-band connector is matched on the same registry."""
    port = _released_loopback_port()

    with pytest.raises(suite_conftest.UnmockedNetworkAccessError):
        socket.create_connection((LOOPBACK_V4, port))


def test_detaching_withdraws_the_authorization():
    """``detach`` gives up the descriptor without closing it, and releases too."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind((LOOPBACK_V4, 0))
    port = _port_of(listener)
    endpoint = suite_conftest._endpoint_of(
        socket.AF_INET, socket.SOCK_STREAM, (LOOPBACK_V4, port)
    )
    assert endpoint in suite_conftest._OWNED_ENDPOINTS

    descriptor = listener.detach()
    try:
        assert endpoint not in suite_conftest._OWNED_ENDPOINTS
    finally:
        socket.socket(fileno=descriptor).close()


def test_closing_one_of_two_holders_keeps_the_endpoint_owned():
    """Two sockets on one endpoint are counted, so neither release is premature."""
    first = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    first.bind((LOOPBACK_V4, 0))
    port = _port_of(first)
    endpoint = suite_conftest._endpoint_of(
        socket.AF_INET, socket.SOCK_STREAM, (LOOPBACK_V4, port)
    )
    second = _StandInSocket(socket.AF_INET, socket.SOCK_STREAM)
    suite_conftest._acquire_endpoint(second, endpoint)
    try:
        first.close()

        assert endpoint in suite_conftest._OWNED_ENDPOINTS
    finally:
        suite_conftest._release_socket_endpoint(second)


# --------------------------------------------------------------------------- #
# Negative: AF_UNIX.  Local by construction is not the same as owned.
# --------------------------------------------------------------------------- #


@pytest.fixture
def unix_family(monkeypatch):
    """Substitute ``AF_UNIX_FAMILY`` so the branch is reachable on any platform.

    Yields the family number the stand-in sockets report. The real constant is
    used where the platform provides it, so the assertions run against production
    values on a platform that has them.
    """
    family = getattr(socket, "AF_UNIX", SUBSTITUTE_UNIX_FAMILY)
    monkeypatch.setattr(suite_conftest, "AF_UNIX_FAMILY", family)
    return family


def test_an_unbound_unix_path_is_refused(unix_family):
    """Any process can publish a Unix socket; this suite must not talk to one."""
    stand_in = _StandInSocket(unix_family)

    assert suite_conftest._is_local_address(stand_in, FOREIGN_UNIX_PATH) is False


def test_a_unix_path_this_process_bound_is_admitted(unix_family):
    """Ownership, not locality, is what admits it."""
    stand_in = _StandInSocket(unix_family)
    endpoint = suite_conftest._endpoint_of(unix_family, None, UNIX_PATH)
    suite_conftest._acquire_endpoint(stand_in, endpoint)
    try:
        assert suite_conftest._is_local_address(stand_in, UNIX_PATH) is True
    finally:
        suite_conftest._release_socket_endpoint(stand_in)


def test_owning_one_unix_path_does_not_authorize_another(unix_family):
    """Each path is its own endpoint."""
    stand_in = _StandInSocket(unix_family)
    endpoint = suite_conftest._endpoint_of(unix_family, None, UNIX_PATH)
    suite_conftest._acquire_endpoint(stand_in, endpoint)
    try:
        assert suite_conftest._is_local_address(stand_in, FOREIGN_UNIX_PATH) is False
    finally:
        suite_conftest._release_socket_endpoint(stand_in)


def test_an_unnamed_unix_socket_is_not_an_endpoint(unix_family):
    """An autobound socket reports ``''``, which identifies nothing."""
    assert suite_conftest._endpoint_of(unix_family, None, "") is None


def test_releasing_a_unix_path_withdraws_it(unix_family):
    """The lifetime rule applies to ``AF_UNIX`` as much as to a port."""
    stand_in = _StandInSocket(unix_family)
    endpoint = suite_conftest._endpoint_of(unix_family, None, UNIX_PATH)
    suite_conftest._acquire_endpoint(stand_in, endpoint)

    suite_conftest._release_socket_endpoint(stand_in)

    assert suite_conftest._is_local_address(stand_in, UNIX_PATH) is False


# --------------------------------------------------------------------------- #
# The registry lock is re-entrant, because a finalizer releases through it.
# --------------------------------------------------------------------------- #


def test_the_registry_lock_can_be_acquired_twice_by_one_thread():
    """The lock is re-entrant, which a plain ``Lock`` is not.

    ``_release_collected_endpoint`` is a weak-reference callback, so the garbage
    collector can run it on a thread that is already inside
    ``_acquire_endpoint``. With a non-reentrant lock that thread waits for itself
    and the run stops there, which is why ``DECISION-LOG.md`` row D224 records the
    lock as an ``RLock``.

    Bounded by ``timeout`` rather than left to block, so a regression fails this
    test instead of hanging the suite.
    """
    assert suite_conftest._OWNED_ENDPOINTS_LOCK.acquire(timeout=REENTRY_TIMEOUT) is True
    try:
        reacquired = suite_conftest._OWNED_ENDPOINTS_LOCK.acquire(
            timeout=REENTRY_TIMEOUT
        )
        assert reacquired is True, (
            "the endpoint registry lock is not re-entrant, so a weakref finalizer "
            "firing inside a held lock would deadlock the run"
        )
        suite_conftest._OWNED_ENDPOINTS_LOCK.release()
    finally:
        suite_conftest._OWNED_ENDPOINTS_LOCK.release()


def test_a_finalizer_can_release_an_endpoint_from_inside_the_held_lock(unix_family):
    """The functional half: the release path re-enters and completes.

    Run on a worker thread with a bounded join, so a non-reentrant lock shows up
    as a thread that never finishes rather than as a suite that never returns.
    """
    stand_in = _StandInSocket(unix_family)
    endpoint = suite_conftest._endpoint_of(unix_family, None, UNIX_PATH)
    suite_conftest._acquire_endpoint(stand_in, endpoint)
    completed = threading.Event()

    def release_while_holding():
        with suite_conftest._OWNED_ENDPOINTS_LOCK:
            # The same call the weakref callback makes, from a frame that already
            # holds the lock.
            suite_conftest._release_socket_endpoint(stand_in)
        completed.set()

    worker = threading.Thread(target=release_while_holding, daemon=True)
    worker.start()
    worker.join(REENTRY_TIMEOUT)

    assert completed.is_set(), (
        "releasing an endpoint from inside the held registry lock did not "
        "complete, which is the deadlock a non-reentrant lock produces"
    )
    assert suite_conftest._is_local_address(stand_in, UNIX_PATH) is False
