import os
from typing import Callable, Any
import contextlib
import socketio
from contextlib import contextmanager

import types
@types.coroutine
def callcc(func):
    """The almighty call-with-current-continuation, now in coroutine form.

    This function returns an awaitable object, so it must be called
    like this:
       retval = await callcc(some_func)

    Then if some_func looks like this:
       def some_func(return_cb, throw_cb):
           ...
           return_cb(42)
           ...

    Then your execution will resume with retval == 42.

    Alternatively, if some_func looks like this:
       def some_func(return_cb, throw_cb):
           ...
           throw_cb(Exception("disaster!"))
           ...

    Then your execution will resume with that exception.

    Note that this only works when called from coroutines launched
    with `start`, which is also in this module.

    Warning: The coroutines provided by this function are SINGLE-USE!
    You must not call them twice!

    """
    return (yield func)

class CallOnlyOnce:
    """Wraps functions and ensures only one is called.

    A simple stateful class that can wrap any number of functions, and ensures
    that only one of them is ever called, and only once.

    """
    def __init__(self, msg):
        self.been_called = False
        self.msg = msg

    def wrap(self, f):
        def wrapped(*args, **kwargs):
            if self.been_called:
                raise Exception(self.msg)
            self.been_called = True
            return f(*args, **kwargs)
        return wrapped

def start(coroutine):
    """Starts a coroutine running.

    If the coroutine makes a blocking call before yielding for the
    first time, start() will block. However, if the coroutine is
    written to not use blocking operations, or at least doesn't call
    them before its first yield, start() will return immediately
    (after reaching the first yield).

    In either case, this function will return None.

    """
    def run(continuation, value):
        try:
            # Pass the value in to the coroutine, and the coroutine will run until
            # either the coroutine yields us a function to call...
            func = continuation(value)
        except StopIteration:
            # ...or the coroutine returns a value through throwing StopIteration...
            return
        except:
            # ...or the coroutine throws an exception, bringing its story to an end.
            raise
        else:
            trampoline(func)
    def trampoline(func):
        # The coroutine has sent us function "func"; we will pass the coroutine's
        # continuations to func, so that it may call them and restart the coroutine.
        once = CallOnlyOnce("Only one of the continuations produced by callcc can be called, and only once.")
        send  = once.wrap(lambda val: run(coroutine.send,  val))
        throw = once.wrap(lambda exn: run(coroutine.throw, exn))
        try:
            # Now, actually call the function that the coroutine yielded us.
            # We pass it wrapped callbacks for coroutine.send and coroutine.throw, so
            # the function may send a value or throw an exception into the coroutine
            # as it wishes.
            func(send, throw)
            # func shouldn't block for overly long, so trampoline(func) will return quickly.
            # If func does block, so too will trampoline(func), and anything above it on the call stack.
        except:
            raise RuntimeError("Functions called with callcc are not allowed to throw exceptions")
    run(coroutine.send, None)

class LinearVariable:
    def __init__(self):
        """A class which linearly holds a single value.

        The value inside this class can be set exactly once, and gotten exactly once.

        The goal of this class is to allow function A (which can't use
        callcc) to call function B (which returns its value via
        invoking a callback).

        That scenario happens whenever normal code wants to call
        coroutine code. Coroutines return values by invoking a
        continuation callback.

        If we pass LinearVariable.set as the return value callback for
        a coroutine (specifically, as the return_value_cb argument to
        the start function) then we can get the return value of the
        coroutine from normal code.

        This is also useful as a way to return a value from an
        asynchronous generator.

        """

        self.value = None
        self.been_set = False
        self.been_got = False

    def set(self, value):
        if self.been_set:
            raise Exception("can't set LinearVariable twice")
        self.value = value
        self.been_set = True

    def get(self):
        if not self.been_set:
            raise Exception("can't get value of unset LinearVariable")
        if self.been_got:
            raise Exception("can't get value of LinearVariable twice")
        val = self.value
        self.been_got = True
        self.value = None
        return val

# wait a second.
# I guess we'll have it be some kind of,
# object-cap design
# we'll have this single function which will let us block
# it's a WaitForMultipleObjects
# and we'll await on it being passed in to us.
# and we'll call it to get events.

# does that make sense?

# okay so I should model an epoll edge-triggered interface.
# essentially, they ask for an event on a file descriptor
# and we have an event cache for that file descriptor
# and they should only ask again for the event when they have already tried to operate, and gotten EAGAIN on that file descriptor.

# so!

# we'll have this MonitoredFileDescriptor class,
# and we'll have async methods on it that can be called to block,
# and that's the entire interface.

# this, I guess, is something like what an event loop should look like
# we'll require all IO goes through the framework.
# we'll need to have a wrapper for pathlib.Path
# then we'll explicitly pass it in, all the way.
# then things will automatically be able to switch between async and not-async
# not that that's useful...
# but, they'll be able to run multiple in the same process, which is nice.
# yeah this is the right way to make it clean and nice.
# COROUTINES!
async def event_loop():
    # this is some kind of global mutable variable that things re-enter
    waiters = []
    while True:
        happened_events = await callcc(selector.register_callback_for(waiter.event for waiter in waiters))
        # then at the top-level, we do selector.block_and_callback() to feed events back in.
        # in a loop, if we so choose.
        for event in happening_events:
            event.dispatch()
        # if there are no more waiters in this event loop, we're done, get out
        if len(waiters) == 0:
            break

class LinearChannel:
    def __init__(self):
        self._cb = None
        import collections
        self._pending = collections.deque()

    def send(self, value):
        if self._cb is not None:
            cb = self._cb
            self._cb = None
            cb(value)
        else:
            self._pending.append(value)

    async def recv(self):
        if self._cb is not None:
            raise Exception("shared access to LinearChannel")
        if len(self._pending) != 0:
            return self._pending.popleft()
        def register_cb(cb, _):
            self._cb = cb
        return (await callcc(register_cb))

    def pop_pending(self):
        while len(self._pending) != 0:
            yield self._pending.popleft()

class MonitorMultipleCoroutines:
    def __init__(self):
        self.chan = LinearChannel()

    async def gimme_some_event(self):
        return (await self.chan.recv())

    def gimme_pending_events(self):
        yield from self.chan.pop_pending()

    def add_and_start(self, coroutine_object, tag=None):
        async def work():
            try:
                ret = await coroutine_object
            except Exception as e:
                self.chan.send((tag, None, e))
            else:
                self.chan.send((tag, ret, None))
        start(work())

class ToplevelMonitor:
    def __init__(self):
        self.monitor = MonitorMultipleCoroutines()

    def check(self):
        for tag, ret, exc in self.monitor.gimme_pending_events():
            if exc:
                print("process", tag, "threw", exc)
                raise exc
            else:
                print("process", tag, "returned", ret)

    def add_and_start(self, coroutine_object, tag=None):
        self.monitor.add_and_start(coroutine_object, tag=tag)

async def reader(chan, return_on=None, tag="got val"):
    while True:
        val = await chan.recv()
        print(tag, val)
        if return_on is not None and val == return_on:
            print("returning", val)
            return val

class AsyncEpoll:
    "An epoll object whose poll function is async"
    def __init__(self, real_epoll, request_poll):
        self.real_epoll = real_epoll
        self.request_poll = request_poll
        self._result_cb = None
        self._except_cb = None

    def register(self, fd, eventmask=None):
        if eventmask is not None:
            return self.real_epoll.register(fd, eventmask)
        else:
            return self.real_epoll.register(fd)

    def modify(self, fd, eventmask):
        return self.real_epoll.modify(fd, eventmask)

    def unregister(self, fd):
        return self.real_epoll.unregister(fd)

    async def poll(self):
        if self._result_cb is not None or self._except_cb is not None:
            raise Exception("multiple callers are calling poll on AsyncEpoll?")
        def work(result_cb, except_cb):
            self._result_cb = result_cb
            self._except_cb = except_cb
            self.request_poll(self)
        return (await callcc(work))

    def _do_poll(self, timeout):
        "Called by the main loop when we request it."
        if self._result_cb is None or self._except_cb is None:
            raise Exception("calling _do_poll without setting the result callbacks is forboden")
        result_cb = self._result_cb
        self._result_cb = None
        except_cb = self._except_cb
        self._except_cb = None
        try:
            print("epolling with timeout", timeout)
            ret = self.real_epoll.poll(timeout)
            print("got from epoll", ret)
        except Exception as exn:
            except_cb(exn)
            return False
        else:
            result_cb(ret)
            return True

class Future:
    def __init__(self):
        self.value = None
        self.been_set = False
        self.cbs = []

    def set(self, value):
        self.value = value
        self.been_set = True
        for cb in self.cbs:
            cb(self.value)
        del self.cbs

    async def get(self):
        if self.been_set:
            return self.value
        def register_callback(cb, _):
            self.cbs.append(cb)
        return (await callcc(register_callback))

class FDMonitor:
    def __init__(self, epoll: AsyncEpoll) -> None:
        self.epoll = epoll
        self.monitor_map: Any = {}
        self.poll_result_fut = None
        self.waiters_by_fd: Any = {}
        self.poll_running = False

    async def poll(self):
        # I should optimize this class by having callers just await on a specific
        # flag on a specific fd, then have the poll() coroutine do the dispatch to
        # callers.
        if self.poll_result_fut is None:
            print("poll: doing the poll")
            self.poll_result_fut = future = Future()
            start(self._do_poll())
        else:
            print("poll: waiting for future")
            future = self.poll_result_fut
        return (await future.get())

    async def _do_poll(self):
        future = self.poll_result_fut
        result = await self.epoll.poll()
        self.poll_result_fut = None
        future.set(result)

    # optimized???
    async def _poll(self):
        self.poll_running = True
        to_call = []
        for fd, event in await self.epoll.poll():
            waiters = self.waiters_by_fd[fd]
            del self.waiters_by_fd[fd]
            remaining = []
            for wanted_event, cb in waiters:
                if event & wanted_event:
                    to_call.append(cb)
                else:
                    remaining.append((wanted_event, cb))
            if remaining:
                self.waiters_by_fd[fd] = remaining
        for cb in to_call:
            cb(None)
        self.poll_running = False
        if len(self.waiters_by_fd) != 0:
            start(self._poll())

    def monitor(self, fd):
        if fd not in self.monitor_map:
            self.monitor_map[fd] = MonitoredFD(fd, self)
        return self.monitor_map[fd]

class MonitoredFD:
    def __init__(self, fd, monitor):
        self.fd = fd
        self.monitor = monitor
        self.current_eventmask = 0
        self.monitor.epoll.register(self.fd, self.current_eventmask)

    @contextlib.contextmanager
    def _mask_flag(self, flag):
        if (self.current_eventmask & flag) == 0:
            print("setting mask")
            self.current_eventmask |= flag
            self.monitor.epoll.modify(self.fd, self.current_eventmask)
            yield
            self.current_eventmask ^= flag
            self.monitor.epoll.modify(self.fd, self.current_eventmask)
        else:
            print("not setting mask")
            yield

    async def wait_for_event_flag(self, flag):
        with self._mask_flag(flag):
            while True:
                print("looping for readable", self.fd)
                poll_result = await self.monitor.poll()
                print("got poll_result", poll_result)
                for fd, event in poll_result:
                    if fd == self.fd and (event & flag) != 0:
                        return

    async def readable(self):
        await self.wait_for_event_flag(select.EPOLLIN)

    async def writable(self):
        pass

import os
import errno
class PipeChannel:
    "both ends in a single object because that's convenient"
    def __init__(self, fdmonitor: FDMonitor) -> None:
        self.rfd, self.wfd = os.pipe()
        try:
            self.read_monitor  = fdmonitor.monitor(self.rfd)
            self.write_monitor = fdmonitor.monitor(self.wfd)
            os.set_blocking(self.rfd, False)
        except:
            os.close(self.rfd)
            os.close(self.wfd)
            raise

    async def read(self):
        def data_no_eof():
            data = os.read(self.rfd, 4096)
            if len(data) == 0:
                raise Exception("eof on our own pipe?")
            return data
        try:
            print("performing first read")
            return data_no_eof()
        except OSError as e:
            if e.errno == errno.EAGAIN:
                print("waiting for readable")
                await self.read_monitor.readable()
                print("performing second read")
                return data_no_eof()
            else:
                raise

    def write(self, data):
        amount = os.write(self.wfd, data)
        if amount != len(data):
            raise Exception("partial write")

    def __del__(self):
        print("deleting PipeChannel")
        os.close(self.rfd)
        os.close(self.wfd)

import socket
def wrap_socket(fdmonitor, sock):
    fd = fdmonitor.monitor(sock.fileno())
    return Socket(sock, fd.readable, fd.writable)

def make_seqpacket(fdmonitor):
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET, 0)
    return wrap_socket(fdmonitor, a), wrap_socket(fdmonitor, b)

class Process:
    def __init__(self, sock: Socket, pid: int) -> None:
        self.sock = sock
        self.pid = pid

    async def event(self):
        fields = (await self.sock.recv(4096)).rstrip().split(b" ")
        if len(fields) == 1:
            return (fields[0], None)
        elif len(fields) == 2:
            return (fields[0], int(fields[1]))
        else:
            raise Exception("malformed message", fields)

import supervise_api
import functools
class Host:
    def __init__(self, monitor: FDMonitor) -> None:
        self.monitor = monitor

    @functools.wraps(supervise_api.dfork)
    async def make_process(self, *args, **kwargs):
        sock = supervise_api.dfork(*args, **kwargs)
        sock = wrap_socket(self.monitor, sock)

        try:
            typ, pid = (await sock.recv(4096)).rstrip().split(b" ")
            if typ != b"pid":
                raise Exception("starting message has unknown type", typ)
            pid = int(pid)
        except:
            raise Exception("starting process failed, couldn't even get pid")
        
        return Process(sock, pid)

import time
async def call_it_and_print(func, tag):
    print("STARTING", tag)
    while True:
        time.sleep(.01)
        print("looping in", tag)
        print(tag, "got", await func())

def excitement():
    tl = TopLevelBusyLoop()
    epoll = tl.create_epoll()
    fdmonitor = FDMonitor(epoll)
    a, b = make_seqpacket(fdmonitor)
    start(call_it_and_print(lambda: a.recv(4096), tag="a"))
    print("writing")
    b._socket.send(b"msg1")
    print("pumped")
    tl.nonblocking_pump()
    host = Host(fdmonitor)
    async def thing():
        proc = await host.make_process(["sleep", "5"])
        start(call_it_and_print(proc.event, tag="got"))
    start(thing())
    while True:
        tl.blocking_pump()
    # return tl, pc

import select
class TopLevelBusyLoop:
    """Busy loops between multiple event loops/blocking calls

    As an optimization, if there's only one event loop/blocking call,
    it will just make a blocking call into the operating system.

    """
    def __init__(self):
        self.active_loops = []

    def _do_epoll_poll(self, epoll):
        self.active_loops.append(epoll)

    def blocking_pump(self):
        if len(self.active_loops) == 0:
            return
        if len(self.active_loops) > 1:
            raise Exception("can only handle one loop at a time at the moment")
        epoll = self.active_loops[0]
        del self.active_loops[0]
        epoll._do_poll(10)

    def nonblocking_pump(self):
        if len(self.active_loops) == 0:
            return
        if len(self.active_loops) > 1:
            raise Exception("can only handle one loop at a time at the moment")
        epoll = self.active_loops[0]
        del self.active_loops[0]
        epoll._do_poll(0)

    def create_epoll(self) -> AsyncEpoll:
        return AsyncEpoll(select.epoll(), self._do_epoll_poll)

def pump_until_complete(pump, coroutine_object):
    return_var = LinearVariable()
    exception_var = LinearVariable()
    async def work():
        try:
            val = await coroutine_object
        except Exception as e:
            exception_var.set(e)
        else:
            return_var.set(val)
    start(work())
    while not (return_var.been_set or exception_var.been_set):
        pump()
    if return_var.been_set:
        return return_var.get()
    elif exception_var.been_set:
        raise exception_var.get()

def test_stuff():
    monitor = MonitorMultipleCoroutines()
    chan1 = LinearChannel()
    chan2 = LinearChannel()
    chan1.send(10)
    chan2.send(11)
    monitor.add_and_start(reader(chan1, 1001), tag="tag1001")
    monitor.add_and_start(reader(chan2, 1002), tag="tag1002")
    chan1.send(20)
    chan2.send(21)
    start(reader(monitor.chan, return_on=2001, tag="someone returned"))
    # 
    chan1.send(30)
    chan2.send(31)
    # 
    chan1.send(1001)
    chan1.send(1002)
    # 
    chan1.send(40)
    chan2.send(41)
    # 
    chan2.send(1001)
    chan2.send(1002)
    # 
    chan1.send(50)
    chan2.send(51)

from socket import SOL_SOCKET, SO_ERROR

try:
    from ssl import SSLWantReadError, SSLWantWriteError
    WantRead = (BlockingIOError, InterruptedError, SSLWantReadError)
    WantWrite = (BlockingIOError, InterruptedError, SSLWantWriteError)
except ImportError:    # pragma: no cover
    WantRead = (BlockingIOError, InterruptedError)
    WantWrite = (BlockingIOError, InterruptedError)

class Socket(object):
    '''
    Non-blocking wrapper around a socket object.   The original socket is put
    into a non-blocking mode when it's wrapped.
    '''

    def __init__(self, sock, readable, writable):
        self._socket = sock
        self._socket.setblocking(False)
        self._readable = readable
        self._writable = writable

    def __repr__(self):
        return '<curio.Socket %r>' % (self._socket)

    def __getattr__(self, name):
        return getattr(self._socket, name)

    def fileno(self):
        return self._socket.fileno()

    def settimeout(self, seconds):
        raise RuntimeError('Use timeout_after() to set a timeout')

    def gettimeout(self):
        return None

    def dup(self):
        return type(self)(self._socket.dup())

    @contextmanager
    def blocking(self):
        '''
        Allow temporary access to the underlying socket in blocking mode
        '''
        try:
            self._socket.setblocking(True)
            yield self._socket
        finally:
            self._socket.setblocking(False)

    async def recv(self, maxsize, flags=0):
        while True:
            try:
                data = self._socket.recv(maxsize, flags)
                if len(data) == 0:
                    raise Exception("eof")
                return data
            except WantRead:
                await self._readable()
            except WantWrite:     # pragma: no cover
                await self._writable()

    async def recv_into(self, buffer, nbytes=0, flags=0):
        while True:
            try:
                return self._socket.recv_into(buffer, nbytes, flags)
            except WantRead:
                await self._readable()
            except WantWrite:     # pragma: no cover
                await self._writable()

    async def send(self, data, flags=0):
        while True:
            try:
                return self._socket.send(data, flags)
            except WantWrite:
                await self._writable()
            except WantRead:      # pragma: no cover
                await self._readable()

    async def sendall(self, data, flags=0):
        buffer = memoryview(data).cast('b')
        total_sent = 0
        try:
            while buffer:
                try:
                    nsent = self._socket.send(buffer, flags)
                    total_sent += nsent
                    buffer = buffer[nsent:]
                except WantWrite:
                    await self._writable()
                except WantRead:   # pragma: no cover
                    await self._readable()
        except errors.CancelledError as e:
            e.bytes_sent = total_sent
            raise

    async def accept(self):
        while True:
            try:
                client, addr = self._socket.accept()
                return type(self)(client), addr
            except WantRead:
                await self._readable()

    async def connect_ex(self, address):
        try:
            await self.connect(address)
            return 0
        except OSError as e:
            return e.errno

    async def connect(self, address):
        try:
            result = self._socket.connect(address)
            if getattr(self, 'do_handshake_on_connect', False):
                await self.do_handshake()
            return result
        except WantWrite:
            await self._writable()
        err = self._socket.getsockopt(SOL_SOCKET, SO_ERROR)
        if err != 0:
            raise OSError(err, 'Connect call failed %s' % (address,))
        if getattr(self, 'do_handshake_on_connect', False):
            await self.do_handshake()

    async def recvfrom(self, buffersize, flags=0):
        while True:
            try:
                return self._socket.recvfrom(buffersize, flags)
            except WantRead:
                await self._readable()
            except WantWrite:       # pragma: no cover
                await self._writable()

    async def recvfrom_into(self, buffer, bytes=0, flags=0):
        while True:
            try:
                return self._socket.recvfrom_into(buffer, bytes, flags)
            except WantRead:
                await self._readable()
            except WantWrite:       # pragma: no cover
                await self._writable()

    async def sendto(self, bytes, flags_or_address, address=None):
        if address:
            flags = flags_or_address
        else:
            address = flags_or_address
            flags = 0
        while True:
            try:
                return self._socket.sendto(bytes, flags, address)
            except WantWrite:
                await self._writable()
            except WantRead:      # pragma: no cover
                await self._readable()

    async def recvmsg(self, bufsize, ancbufsize=0, flags=0):
        while True:
            try:
                return self._socket.recvmsg(bufsize, ancbufsize, flags)
            except WantRead:
                await self._readable()

    async def recvmsg_into(self, buffers, ancbufsize=0, flags=0):
        while True:
            try:
                return self._socket.recvmsg_into(buffers, ancbufsize, flags)
            except WantRead:
                await self._readable()

    async def sendmsg(self, buffers, ancdata=(), flags=0, address=None):
        while True:
            try:
                return self._socket.sendmsg(buffers, ancdata, flags, address)
            except WantRead:
                await self._writable()

    # Special functions for SSL
    async def do_handshake(self):
        while True:
            try:
                return self._socket.do_handshake()
            except WantRead:
                await self._readable()
            except WantWrite:
                await self._writable()

    # Design discussion.  Why make close() async?   Partly it's to make the
    # programming interface highly uniform with the other methods (all of which
    # involve an await).  It's also to provide consistency with the Stream
    # API below which requires an asynchronous close to properly flush I/O
    # buffers.

    async def close(self):
        if self._socket:
            self._socket.close()
        self._socket = None
        self._fileno = -1

    # This is declared as async for the same reason as close()
    async def shutdown(self, how):
        if self._socket:
            self._socket.shutdown(how)

    async def __aenter__(self):
        self._socket.__enter__()
        return self

    async def __aexit__(self, *args):
        if self._socket:
            self._socket.__exit__(*args)
