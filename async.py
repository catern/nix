import os
from typing import Callable, Any

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
        except:
            # ...or the coroutine throws an exception, bringing its story to an end.
            pass
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

class Channel:
    def __init__(self):
        self.cbs = []

    def send(self, value):
        cbs = self.cbs
        self.cbs = []
        for cb in cbs:
            cb(value)

    def register_callback(self, cb, _):
        self.cbs.append(cb)

    async def recv(self):
        return (await callcc(self.register_callback))

def fd_reader(obj):
    async def read():
        buf = os.read(obj.fileno(), 4096)
        if len(buf) == 0:
            raise Exception(f"got eof on {obj.fileno()}")
        else:
            return buf
    return read

def fd_writer(obj):
    async def write(data):
        # print("about to write to", obj.fileno(), file=sys.stderr)
        sent = os.write(obj.fileno(), data)
        if sent != len(data):
            raise Exception(f"partial write to {obj.fileno()}")
    return write

import inspect
def store_generator_return_value(f):
    """Decorates a generator function to return an iterable object which stores the generator's return value

    Works on both regular and async generators!

    """
    if inspect.isasyncgenfunction(f):
        def wrapped(*args, **kwargs):
            return StoreAsyncGeneratorReturnValue(f(*args, **kwargs))
        return wrapped
    elif inspect.isgeneratorfunction(f):
        def wrapped(*args, **kwargs):
            return StoreGeneratorReturnValue(f(*args, **kwargs))
        return wrapped
    else:
        raise TypeError("passed function is not a generator or async generator:", f)

class StoreGeneratorReturnValue:
    def __init__(self, gen):
        self.var = LinearVariable()
        self.gen = gen

    def get(self):
        return self.var.get()

    def __iter__(self):
        return self

    def __next__(self):
        if self.var.been_set:
            raise StopIteration()
        try:
            return self.gen.__next__()
        except StopIteration as e:
            self.var.set(e.value)
            raise

class StoreAsyncGeneratorReturnValue:
    def __init__(self, gen):
        self.var = LinearVariable()
        self.gen = gen

    def get(self):
        return self.var.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.var.been_set:
            raise StopAsyncIteration()
        try:
            return (await self.gen.__anext__())
        except StopAsyncIterationWithValue as e:
            self.var.set(e.value)
            raise StopAsyncIteration
        except StopAsyncIteration:
            self.var.set(None)
            raise StopAsyncIteration

class StopAsyncIterationWithValue(Exception):
    def __init__(self, value):
        self.value = value

# What if I want a single generator to generate two streams?
# that's not the real issue.
# the real issue is, how do I iterate over two async streams?
# I want get whichever one returns a value first.
# and dispatch on that.

# dispatch is easy enough.
# but essentially I __anext__ them all, passing the appropriate dispatch continuations
# and then my function returns, having tail-called itself out of existence.

# I think I grasped something interesting

# Python generators use yield to make a "callback" into a for loop that is iterating over your generator.

# The old style of doing coroutines in Python "used up" the generator language feature, using "yield" instead as a callback into the event loop.

# But this was annoying, so they added a new coroutine interface, essentially the same as the generator interface,
# which offered a dedicated channel through which you can callback into the event loop.

# Then they added support for using the old generator interface at the same time as the new coroutine interface,
# so you could once again use yield to callback into for loops.

# The problem is that each of these kinds of special callbacks are language-level features in Python.
# what you really want is a generic way to make these callbacks.

# Essentially, what would it look like to generate multiple streams?

def example(f, g):
    f(1)
    g("foo")
    f(2)
    g("bar")
    f(3)
    f(4)

# And what behavior would you want?
# Basically, you'd want f to block until it requests another value from you.
# No, wait!
# If I want to be able to callcc...

# Essentially, I want functions I call to be able to send the value I pass in, to somewhere up stream,
# and then block or something?

# Ok, how would we implement generators using callcc?

# Essentially, it would look like this...

def example_generator(callback: Callable[[int, Any], None]):
    for value in range(5):
        callcc(lambda k: callback(value, k))

# Then, in callback...

def example_user():
    def process(value, cont):
        print(value)
        cont()
    example_generator(process)

# Basically, callcc mode is very strong.
# So...
# What am I using yield to implement, when I use it to implement callcc?
# I'm calling a callback, passing it some value and also my current continuation.
# When I use yield to implement callcc, the callback is simple:
# It just applies the value to my current continuation.

# can I turn example_user into a more for-loopy style?
# using some kind of adapter?

def example_for_user():
    class IterationWrapper:
        def __init__(self, gen_cont):
            self.gen_cont = gen_cont

        def __iter__(self):
            return self

        def __next__(self):
            var = LinearVariable()
            def bind(my_cont):
                def set(value, their_cont):
                    my_cont(value)
                    self.gen_cont = their_cont
                self.gen_cont(set)
            return callcc(bind)
    pass

# okay.
# so I think I clearly should be using callbacks in the stderr log thing.

# if those callbacks are async, they can be transformed into a for-loop straightforwardly using callcc magic.

# callbacks...

# the only remaining issue with that is exceptions.
# callbacks are painful with exceptions, because what if the code in the middle binds a handler?
# but I think it's unimportant
# also, in this concrete use case, it's unimportant.

# wait a second.
# if I do it with callbacks, I lose out theoretically.

# I want a type where...
# i can detect the end explicitly

# oh hmm but i don't have dispatching overhead with callbacks!

# so the choice is
# request -> (errlog -> ()) -> result
# or
# request -> Stream errlog result
# where Stream is:
# () -> ((errlog, Stream errlog result) | result)

# the latter seems more specific.

# let's rewrite the latter...

# request -> ((errlog, Stream errlog result) | result)

# request -> () -> errlog, (() -> errlog, (() -> errlog, (() -> Stream errlog result | result) | result) | result)

# compare:
# (elem -> ()) -> ()
# Stream elem = More (() -> elem) | End
# which desugars anyway to
# (elem, Stream elem)
# (elem, (elem, Stream elem))

# can I map the state machine around to that?

# this is really sweet and all, but...
# what if I want to actually have a generator?

# oh! at that time, I can use the coroutine thing :)


def agen_return(value=None):
    """Return a value while inside an asynchronous generator.

    It's not yet possible to return a value inside an asynchronous
    generator using a return statement, so this should be used
    instead.

    We can't just directly raise StopAsyncIteration inside the
    asynchronous generator, because that's prevented by the Python
    runtime. (and translated into a RuntimeError)

    """
    raise StopAsyncIterationWithValue(value)
