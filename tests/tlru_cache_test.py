import time
import unittest

# pylint: disable=import-error
from tlru_cache import tlru_cache


class TLRUCacheTest(unittest.TestCase):

    def test_cache_access(self) -> None:
        """Test basic cache access."""
        run_counter = 0

        @tlru_cache()
        def cached_function(value: int) -> int:
            nonlocal run_counter
            run_counter += 1
            return value ** 2

        _ = cached_function(2)
        _ = cached_function(2)
        self.assertTrue(run_counter == 1, 'function not run exactly once')

    def test_cache_clear(self) -> None:
        """Test the cache clearing function."""
        run_counter = 0

        @tlru_cache()
        def cached_function(value: int) -> int:
            nonlocal run_counter
            run_counter += 1
            return value ** 2

        _ = cached_function(2)
        cached_function.cache_clear()
        _ = cached_function(2)
        self.assertTrue(run_counter == 2, 'function did not run twice')

    def test_cache_info(self) -> None:
        """Test the cache statistics object."""

        @tlru_cache(maxsize=5, lifetime=0.001)
        def cached_function(value: int) -> int:
            return value ** 2

        _ = cached_function(1)
        _ = cached_function(2)
        _ = cached_function(1)
        time.sleep(0.005)
        _ = cached_function(2)
        info = cached_function.cache_info()
        self.assertTupleEqual(
            tuple(info),
            (1, 3, 5, 1, 0.001, 1),
            'cache_info tuple mismatch')
        self.assertDictEqual(
            # NOTE: This method is valid and part of the namedtuple interface
            # according to the "collections" module documentation. The leading
            # underscore is only used to avoid name clashes with custom field
            # names.
            # pylint: disable=protected-access
            info._asdict(),  # type: ignore
            {
                'hits': 1,
                'misses': 3,
                'maxsize': 5,
                'currsize': 1,
                'lifetime': 0.001,
                'expired': 1
            },
            'cache_info dict mismatch')

    def test_cache_lru(self) -> None:
        """Test the regular LRU cache component."""

        @tlru_cache(maxsize=5, lifetime=None)
        def cached_function(value: int) -> int:
            return value ** 2

        _ = [cached_function(i) for i in range(1, 6)]
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 0)
        self.assertEqual(info.misses, 5)
        self.assertEqual(info.maxsize, 5)
        self.assertEqual(info.currsize, 5)
        self.assertIs(info.lifetime, None)
        _ = cached_function(3)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 5)
        self.assertEqual(info.currsize, 5)
        _ = cached_function(6)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 6)
        self.assertEqual(info.currsize, 5)
        _ = cached_function(1)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 7)

    def test_cache_timed(self) -> None:
        """Test the timed LRU cache."""

        @tlru_cache(maxsize=10, lifetime=0.05)
        def cached_function(value: int) -> int:
            return value ** 2

        _ = [cached_function(i) for i in range(1, 6)]
        time.sleep(0.025)
        _ = [cached_function(i) for i in range(6, 11)]
        time.sleep(0.02)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 0)
        self.assertEqual(info.misses, 10)
        self.assertEqual(info.maxsize, 10)
        self.assertEqual(info.currsize, 10)
        self.assertEqual(info.lifetime, 0.05)
        _ = cached_function(3)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 10)
        self.assertEqual(info.currsize, 10)
        time.sleep(0.02)  # First batch of elements expires
        _ = cached_function(1)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 1)
        self.assertEqual(info.misses, 11)
        self.assertEqual(info.maxsize, 10)
        self.assertEqual(info.currsize, 6)
        self.assertEqual(info.lifetime, 0.05)
        self.assertEqual(info.expired, 1)

    def test_cache_typed(self) -> None:
        """Test the 'typed' parameter."""

        @tlru_cache(typed=True)
        def cached_function(value: int) -> int:
            return value ** 2

        _ = cached_function(1)
        _ = cached_function(1.0)
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 0)
        self.assertEqual(info.misses, 2)

    def test_infinity_cache(self) -> None:
        """Test a cache with no constraints whatsoever."""

        @tlru_cache(maxsize=None, lifetime=None)
        def cached_function(value: int) -> int:
            return value ** 2

        _ = [cached_function(i) for i in range(1024)]
        _ = [cached_function(i) for i in range(1023, -1, -1)]
        _ = [cached_function(i) for i in range(1024)]
        info = cached_function.cache_info()
        self.assertEqual(info.hits, 2048)
        self.assertEqual(info.misses, 1024)
        self.assertIs(info.maxsize, None)
        self.assertEqual(info.currsize, 1024)
        self.assertIs(info.lifetime, None)
        self.assertEqual(info.expired, 0)
