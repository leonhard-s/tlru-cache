"""Time aware cache for arbitrary functions.

This module implements the ``tlru_cache` function, which is a decorator
very similar to :func:`functools.lru_cache()`. It extends the caching
strategy to also allow for a time constraint, which is used to ensure
cache items are always reasonably recent.

"""

import collections
import functools
import threading
import time
from typing import (Any, Callable, Dict, Generic, Hashable, Iterable,
                    NamedTuple, Optional, Set, Tuple, Type, TypeVar, Union,
                    overload)

__all__ = [
    'tlru_cache'
]

__version__ = '0.1.0a1'

_T = TypeVar('_T')
_FuncT = TypeVar('_FuncT', bound=Callable[..., Any])


class _TLRUCacheInfo(NamedTuple):
    """Container for TLRU cache statistics.

    Note that the ``misses`` and ``expired`` field are not exclusive; a
    call that was found in the cache but out of date will count towards
    both.

    :param hits: Number of times a cached value was returned.
    :type hits: int
    :param misses: Number of times no cached value could be found.
    :type misses: int
    :param maxsize: The size constraint of the cache.
    :type maxsize: Optional[int]
    :param currsize: Current number of items in the cache.
    :type int:
    :param lifetime: Timespan during which cache items are valid.
    :type Optional[float]
    :param expired: Number of elements that were missed due to age.
    :type int:

    """
    hits: int
    misses: int
    maxsize: Optional[int]
    currsize: int
    lifetime: Optional[float]
    expired: int


class _TLRUCacheWrapper(Generic[_T]):
    """Type-hinting version of the `_tlru_cache_wrapper` method.

    This is never instantiated and only serves to hint the attributes
    and parameters available.

    :param __wrapped__: The user-provided function that was wrapped.
    :type __wrapped__: Callable[..., _T]

    """

    __wrapped__: Callable[..., _T]

    def __call__(self, *args: Hashable, **kwargs: Hashable) -> _T:
        ...

    def cache_info(self) -> _TLRUCacheInfo:
        """Report cache statistics.

        :return: A named tuple containing cache statistics information.
        :rtype: _TLRUCacheInfo

        """
        ...

    def cache_clear(self) -> None:
        """Clear the cache and reset cache statistics."""
        ...


def _make_key(args: Iterable[Hashable], kwargs: Dict[str, Hashable],
              typed: bool, kwd_mark: Tuple[Hashable] = (object(),),
              fasttypes: Set[Type[Any]] = {int, str}) -> Hashable:
    """Helper function for converting function arguments into a key.

    Please note that keyword argument order affects the generated key,
    f(a=1, b=2) and f(b=2, a=1) will have different keys.

    :param args: A tuple of hasbable arguments to generate a key from.
    :type args: Iterable[Hashable]
    :param kwargs: A dict of hashable keyword arguments.
    :type kwargs: Dict[str, Hashable]
    :param typed: Whether to use include type information in the key.
    :type typed: bool
    :param kwd_mark: A tuple containing a unique marker object to
        separate positional and keyword arguments.
    :type kwd_mark: Tuple[Hashable]
    :param fasttypes: A series of types that cache their hash value.
        This allows speeding up certain single-key lookups.
    :type fasttypes: Set[Type[Any]]

    :return: A hashable value to use use as a key.
    :rtype: Hashable

    """
    # NOTE: I do not fully understand why the key is generated in this way in
    # the original lru_cache implementation, but the point was to emulate its
    # behaviour, so this has not been altered.
    #
    # The _HashedSeq object from the original implementation has been dropped
    # due to this implementation not requiring as many individual hashings.
    key = tuple(args)
    if kwargs:
        key += (kwd_mark, *kwargs.items())
    if typed:
        key += tuple(type(v) for v in args)
        if kwargs:
            key += tuple(type(v) for v in kwargs.values())
    elif len(key) == 1 and type(key[0]) in fasttypes:
        return key[0]
    return key


def _tlru_cache_wrapper(user_function: Callable[..., _T],
                        maxsize: Optional[int], lifetime: Optional[float],
                        typed: bool) -> Callable[..., _T]:
    """Internal cache wrapper.

    This function implements the TLRU cache in its scope and returns a
    function wrapping the original `user_function`.

    :param user_function: The function to cache.
    :type user_function: Callable[..., _T]
    :param maxsize: Maximum number of elements in the cache.
    :type maxsize: Optional[int]
    :param lifetime: Seconds after which elements will become invalid.
    :type lifetime: Optional[float]
    :param typed: Whether to use check argument type as well as value.
    :type typed: bool

    :return: A caching wrapper function for the given `user_function`.
    :rtype: Callable[..., _T]

    """
    cache: 'collections.OrderedDict[Hashable, Tuple[Hashable, float]]' = (
        collections.OrderedDict())

    # Sentinel value used for dict access fallback
    sentinel = object()
    default = sentinel, 0.0

    # Set up statistics
    hits = misses = expired = 0

    # Create local names for common cache methods
    cache_get = cache.get
    cache_len = cache.__len__
    cache_move = cache.move_to_end
    t_now = time.time

    lock = threading.Lock()

    if maxsize == 0:

        def wrapper(*args: Any, **kwargs: Any) -> _T:
            """No caching, only update access statistics."""
            nonlocal misses
            misses += 1
            return user_function(*args, **kwargs)

    # Infinite cache size
    elif maxsize is None:

        # TODO: Add time only constraint

        def wrapper(*args: Any, **kwargs: Any) -> _T:
            """Simple caching with no size or time constraint."""
            nonlocal hits, misses
            with lock:
                key = _make_key(args, kwargs, typed)
                result, _ = cache_get(key, default)
                if result is not sentinel:
                    hits += 1
                    return result  # type: ignore
                misses += 1
                result = user_function(*args, **kwargs)
                cache[key] = result, 0.0  # Time data not needed/used
            return result

    elif lifetime is None or lifetime < 0:

        def wrapper(*args: Any, **kwargs: Any) -> _T:
            """Basic LRU cache."""
            nonlocal hits, misses
            key = _make_key(args, kwargs, typed)
            with lock:
                result, _ = cache_get(key, default)
                if result is not sentinel:

                    hits += 1
                    cache_move(key, last=True)
                    return result  # type: ignore

                if maxsize is not None and cache_len() >= maxsize:
                    _ = cache.popitem(last=False)

                misses += 1

                result = user_function(*args, **kwargs)
                cache[key] = result, 0.0  # Time data not needed/used
            return result

    else:

        def wrapper(*args: Any, **kwargs: Any) -> _T:
            """Timed LRU cache.."""
            nonlocal hits, misses, expired
            key = _make_key(args, kwargs, typed)
            with lock:
                result, time_added = cache_get(key, default)
                now = t_now()
                if result is not sentinel:

                    if now - time_added <= lifetime:  # type: ignore
                        hits += 1
                        cache_move(key, last=True)
                        return result  # type: ignore

                    # Result is out of date - update
                    _ = cache.pop(key)
                    expired += 1
                elif maxsize is not None and cache_len() >= maxsize:
                    _ = cache.popitem(last=False)

                misses += 1

                result = user_function(*args, **kwargs)
                cache[key] = result, now  # Time data not needed/used
            return result

    def cache_info() -> _TLRUCacheInfo:
        """Report cache statistics.

        :return: A named tuple containing cache statistics information.
        :rtype: _TLRUCacheInfo

        """
        with lock:
            for key in list(cache):
                if lifetime is not None and t_now() - cache[key][1] > lifetime:
                    _ = cache.pop(key)
            return _TLRUCacheInfo(
                hits, misses, maxsize, cache_len(), lifetime, expired)

    def cache_clear() -> None:
        """Clear the cache and reset cache statistics."""
        nonlocal hits, misses, expired
        with lock:
            cache.clear()
            hits = misses = expired = 0

    wrapper.cache_info = cache_info  # type: ignore
    wrapper.cache_clear = cache_clear  # type: ignore
    return wrapper


@overload
def tlru_cache(user_function: Callable[..., _T]) -> _TLRUCacheWrapper[_T]:
    """Timed least-recently-used (TLRU) cache decorator.

    This function extends the :func:`functools.lru_cache()` decorator
    provided in the Python standard library by the `lifetime`
    parameter, which controls the maximum age of cache items.

    Arguments to the cached function must be hashabe.

    This function follows the implementation of
    :func:`functools.lru_cache` 

    :param user_function: The function to return a cache for
    :type user_function: Callable[..., Any]

    :return: A TLRU-cached wrapper for the decorated function.
    :rtype: _TLRUCacheWrapper

    """
    ...


@overload
def tlru_cache(maxsize: Optional[int] = 128,
               lifetime: Optional[float] = 60.0, typed: bool = False
               ) -> Callable[[Callable[..., _T]], _TLRUCacheWrapper[_T]]:
    """Timed least-recently-used (TLRU) cache decorator.

    This function extends the :func:`functools.lru_cache()` decorator
    provided in the Python standard library by the `lifetime`
    parameter, which controls the maximum age of cache items.

    If `maxsize` is set to None, the LRU features are disabled and only
    the `lifetime` argument will be used for cache invalidation.

    If `lifetime` is set to None, the timed features are disabled,
    resulting in behaviour identical to the original
    :func:`functools.lru_cache()`.

    If `typed` is True, arguments of different types will be cached
    separately. For example, f(3.0) and f(3) will be treated as
    distinct calls with distinct results.

    Arguments to the cached function must be hashabe.

    Calling ``f.cache_info()`` returns a named tuple of cache
    statistics (hits, misses, maxsize, currsize, lifetime, expired).
    The ``expired`` key tracks how many times an element did exist but
    was ignored due having exceeded the cache `lifetime`. Expired items
    are also added to the ``misses`` key.

    Clear the cache and statistics with ``f.cache_info()``. Access the
    underlying function with ``f.__wrapped__`.

    This function follows the implementation of
    :func:`functools.lru_cache`.

    :param maxsize: Number of elements to store, defaults to 128
    :type maxsize: Optional[int], optional
    :param lifetime: Maximum age of cache elements, defaults to 60.0
    :type lifetime: Optional[float], optional
    :param typed: Strict type comparison, defaults to False
    :type typed: bool, optional

    :return: A TLRU-cached wrapper for the decorated function.
    :rtype: Any

    """
    ...


def tlru_cache(maxsize: Union[Callable[..., _T], Optional[int]] = 128,
               lifetime: Union[Optional[float], bool] = 60.0,
               typed: bool = False
               ) -> Union[_TLRUCacheWrapper[_T], Callable[[Callable[..., _T]], _TLRUCacheWrapper[_T]]]:
    """Timed least-recently-used (TLRU) cache decorator.

    This function extends the :func:`functools.lru_cache()` decorator
    provided in the Python standard library by the `lifetime`
    parameter, which controls the maximum age of cache items.

    If `maxsize` is set to None, the LRU features are disabled and only
    the `lifetime` argument will be used for cache invalidation.

    If `lifetime` is set to None, the timed features are disabled,
    resulting in behaviour identical to the original
    :func:`functools.lru_cache()`.

    If `typed` is True, arguments of different types will be cached
    separately. For example, f(3.0) and f(3) will be treated as
    distinct calls with distinct results.

    Arguments to the cached function must be hashabe.

    Calling ``f.cache_info()`` returns a named tuple of cache
    statistics (hits, misses, maxsize, currsize, lifetime, expired).
    The ``expired`` key tracks how many times an element did exist but
    was ignored due having exceeded the cache `lifetime`. Expired items
    are also added to the ``misses`` key.

    Clear the cache and statistics with ``f.cache_info()``. Access the
    underlying function with ``f.__wrapped__`.

    This function follows the implementation of
    :func:`functools.lru_cache`.

    :param maxsize: Number of elements to store, defaults to 128
    :type maxsize: Optional[int], optional
    :param lifetime: Maximum age of cache elements, defaults to 60.0
    :type lifetime: Optional[float], optional
    :param typed: Strict type comparison, defaults to False
    :type typed: bool, optional

    :return: A TLRU-cached wrapper for the decorated function.
    :rtype: Any

    """
    # NOTE: This decorator has two different behaviours depending on the
    # argument types provided. This is inherited from the original
    # implementation of lru_cache in Python version 3.8 and greater:
    #
    # A: maxsize, lifetime and type provided; return a decorator for the cache
    # B: Callable passed instead of maxsize; return the cache itself

    # TODO: Handle negative time

    # Implementation A (part 1)
    if isinstance(maxsize, int):

        # TODO: Document what a maxsize of 0 means

        # Clamp negative maxsize values to 0
        if maxsize < 0:
            maxsize = 0

    # Implementation B
    elif (callable(maxsize) and isinstance(lifetime, float)
            and isinstance(typed, bool)):  # type: ignore
        # user_function was passed in via the maxsize argument
        user_function: Callable[..., _T] = maxsize
        maxsize = 128
        wrapper = _tlru_cache_wrapper(user_function, maxsize, lifetime, typed)
        return functools.update_wrapper(wrapper, user_function)

    # Neither A nor B --> undefined behaviour
    elif maxsize is not None:
        raise TypeError(
            'Expected first argument to be an integer, a callable, or None')

    # Implementation A (part 2)

    def decorating_function(user_function: _FuncT) -> _FuncT:
        wrapper = _tlru_cache_wrapper(user_function, maxsize, lifetime, typed)
        return functools.update_wrapper(wrapper, user_function)

    return decorating_function
