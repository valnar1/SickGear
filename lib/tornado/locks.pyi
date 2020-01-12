# Stubs for tornado_py3.locks (Python 3)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

import datetime
import types
from typing import Any, Awaitable, Optional, Type, Union

class _TimeoutGarbageCollector:
    def __init__(self) -> None: ...

class Condition(_TimeoutGarbageCollector):
    io_loop: Any = ...
    def __init__(self) -> None: ...
    def wait(self, timeout: Optional[Union[float, datetime.timedelta]]=...) -> Awaitable[bool]: ...
    def notify(self, n: int=...) -> None: ...
    def notify_all(self) -> None: ...

class Event:
    def __init__(self) -> None: ...
    def is_set(self) -> bool: ...
    def set(self) -> None: ...
    def clear(self) -> None: ...
    def wait(self, timeout: Optional[Union[float, datetime.timedelta]]=...) -> Awaitable[None]: ...

class _ReleasingContextManager:
    def __init__(self, obj: Any) -> None: ...
    def __enter__(self) -> None: ...
    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[types.TracebackType]) -> None: ...

class Semaphore(_TimeoutGarbageCollector):
    def __init__(self, value: int=...) -> None: ...
    def release(self) -> None: ...
    def acquire(self, timeout: Optional[Union[float, datetime.timedelta]]=...) -> Awaitable[_ReleasingContextManager]: ...
    def __enter__(self) -> None: ...
    def __exit__(self, typ: Optional[Type[BaseException]], value: Optional[BaseException], traceback: Optional[types.TracebackType]) -> None: ...
    async def __aenter__(self) -> None: ...
    async def __aexit__(self, typ: Optional[Type[BaseException]], value: Optional[BaseException], tb: Optional[types.TracebackType]) -> None: ...

class BoundedSemaphore(Semaphore):
    def __init__(self, value: int=...) -> None: ...
    def release(self) -> None: ...

class Lock:
    def __init__(self) -> None: ...
    def acquire(self, timeout: Optional[Union[float, datetime.timedelta]]=...) -> Awaitable[_ReleasingContextManager]: ...
    def release(self) -> None: ...
    def __enter__(self) -> None: ...
    def __exit__(self, typ: Optional[Type[BaseException]], value: Optional[BaseException], tb: Optional[types.TracebackType]) -> None: ...
    async def __aenter__(self) -> None: ...
    async def __aexit__(self, typ: Optional[Type[BaseException]], value: Optional[BaseException], tb: Optional[types.TracebackType]) -> None: ...