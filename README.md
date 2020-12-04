# TLRU Cache

A time aware least recently used (TLRU) cache for arbitrary methods and functions.

The decorator exposed by this module, `tlru_cache`, is a direct analogue to [`functools.lru_cache()`](https://docs.python.org/3/library/functools.html#functools.lru_cache) found in the Python standard library.

## Usage

To enable TLRU caching for a given method, decorate it using the `tlru_cache` decorator:

```py
from tlru_cache import tlru_cache

@tlru_cache()
def expensive_function(a, b, c=False):
    ...
```

The decorator itself supports the same signature options as the LRU implementation it is based on:

**Option 1:**

This is the primary, more flexible endpoint supporting all parameters.

```py
def tlru_cache(maxsize=128, lifetime=60.0, typed=False):
    ...
```

- `maxsize`: Size of the cache. If `None`, the cache can grow without limit. If set to `0` or a negative value, no items will ever be cached.

    This can be used to count function calls via the `missed` field provided by `f.cache_info()` (see below for details).
- `lifetime`: Shelf life for cached items. When a cache item is older than this value, the cached value will be ignored and discarded. If `None`, cache items will never expire. If set to `0.0` or a negative value, cache items will always expire immediately.

    When a cache item expires, it still counts towards the `missed` field, but is also added to the `expired` field.
- `typed`: If `True`, the argument types will be included in the cache keys, not just their values. Set to `True` this if you care about unique types being cached separately.

**Option 2:**

Starting with Python version 3.8, there is a way to access the `lru_cache()` object directly by only passing a callable. This functionality has been carried over into this library.

Refer to the [`lru_cache()` documentation](https://docs.python.org/3/library/functools.html#functools.lru_cache) for details.

```py
def tlru_cache(user_function):
    ...
```

- `user_function`: The user defined function to cache. The created cache is then returned.

### Cache API

The wrapper for the decorated function exposes the following decorated utilities:

- `f.__wrapped__`: The user function that was wrapped
- `f.cache_info()`: Return a [named tuple](https://docs.python.org/3/library/collections.html#collections.namedtuple) containing cache information. The following fields are available:

  - `hits`: Number of times a cached value was returned
  - `misses`: Number of times no cached value could be found
  - `maxsize`: The size constraint of the cache
  - `currsize`: Current number of items in the cache
  - `lifetime`: Timespan during which cache items are valid
  - `expired`: Number of elements that were missed due to age

- `f.cache_clear()`: Clear the cache and reset cache statistics

## Caveats

Things to look out for when using the `tlru_cache()` decorator. Please note that most of these also apply to the regular [`lru_cache`](https://docs.python.org/3/library/functools.html#functools.lru_cache) and are just listed here for convenience.

- Positional and keyword arguments to the decorated function must be hashable
- Keyword argument order matters; `f(a=1, b=2)` and `f(b=2, a=1)` are stored as separate cache entries

## Installation

This module is available on [PyPI](https://pypi.org/project/tlru-cache/) and can be installed through the pip package manager:

```text
python -m pip install tlru-cache
```
