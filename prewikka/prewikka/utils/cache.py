# Copyright (C) 2016-2021 CS GROUP - France. All Rights Reserved.
# Author: Yoann Vandoorselaere <yoannv@gmail.com>
#
# This file is part of the Prewikka program.
#
# SPDX-License-Identifier: BSD-2-Clause
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIEDi
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import collections
import functools
import time

_CacheInfo = collections.namedtuple("CacheInfo", ["hits", "misses", "size"])


class _Cache(object):
    _missing = object()

    def __init__(self, func, duration=None):
        self._cache = {}
        self._cached_func = func
        self._hits = self._misses = 0
        self._duration = duration
        self._times = {}

    def _set(self, key, value):
        self._cache[key] = value
        self._times[key] = time.time()
        return value

    def _get(self, *args, **kwargs):
        key = (args, tuple(kwargs.items()))
        try:
            value = self._cache.get(key, self._missing)
            if value is not self._missing and (not self._duration or self._times[key] + self._duration > time.time()):
                self._hits = self._hits + 1
                return value

            self._misses = self._misses + 1
            return self._set(key, self._cached_func(*args, **kwargs))

        except TypeError as e:
            # uncachable -- for instance, passing a list as an argument.
            # Better to not cache than to blow up entirely.
            env.log.critical("request not cachable: %s(%s): %s" % (self._cached_func.__name__, repr(key), e))
            return self._cached_func(*args, **kwargs)

    def clear(self):
        self._cache.clear()

    def infos(self):
        return _CacheInfo(self._hits, self._misses, len(self._cache))


class _memoize(object):
    def __init__(self, func, name, duration=None):
        self.func = func
        self.cache_objname = name
        self.duration = duration

    def __call__(self, obj, *args, **kwargs):
        return self._setup_cache(obj)._get(obj, *args, **kwargs)

    def _setup_cache(self, obj):
        cache = getattr(obj, self.cache_objname, None)
        if not cache:
            cache = _Cache(self.func, duration=self.duration)
            setattr(obj, self.cache_objname, cache)

        return cache

    def __get__(self, obj, objtype):
        return functools.partial(self.__call__, obj)


class _memoize_property(_memoize):
    def __init__(self, func, name, duration=None):
        self._set_func = None
        _memoize.__init__(self, func, name, duration)

    def setter(self, func):
        self._set_func = func
        return self

    def __set__(self, obj, value):
        if not self._set_func:
            return

        self._set_func(obj, value)
        self._setup_cache(obj)._set((obj,), value)

    def __get__(self, obj, objtype):
        return _memoize.__get__(self, obj, objtype)()


class _request_memoize(_memoize):
    def _setup_cache(self, obj):
        return _memoize._setup_cache(self, env.request.cache)


class _request_memoize_property(_request_memoize, _memoize_property):
    pass


class memoize(object):
    """
        Decorator that will cache the decorated function result value. The cache is stored into
        the instance of the object providing the method.

        Note that calling the cached function with different arguments result in different cache
        entry.

        Usage :

        @memoize("expensive_cache")
        def get_expensive_stuff(self, arg1, argN):
            ... time consuming stuff ...

        The created cache object provide the following API:
        - Cache hits/misses/size statistics:
          self.expensive_cache.infos()

        - Clearing the cache:
          self.expensive_cache.clear()
    """

    def __init__(self, name, duration=None):
        self.name = name
        self.duration = duration

    def __call__(self, func):
        return _memoize(func, self.name, duration=self.duration)


class memoize_property(object):
    """
        Property decorator that cache the method result value. The method is accessible as a Python
        @property, and the cache is stored into the instance of the object providing the method.

        Usage :

        @memoize_property("my_property_cache")
        def my_property(self):
            ... time consuming stuff ...

        The created cache object provide the following API:
        - Cache hits/misses/size statistics:
          self.my_property_cache.infos()

        - Clearing the cache:
          self.my_property_cache.clear()
    """
    def __init__(self, name, duration=None):
        self.name = name
        self.duration = duration

    def __call__(self, func):
        return _memoize_property(func, self.name, duration=self.duration)


class request_memoize(object):
    """
        Decorator that will cache the decorated function result value only in the context of the
        current request. The cache will be stored into the env.request.cache object.

        Note that calling the cached function with different arguments result in different cache
        entry.

        Usage :

        @request_memoize("expensive_cache")
        def get_expensive_stuff(self, arg1, arg2):
            ... time consuming things ...

        The created caching object provide the following API:
        - Cache hits/misses/size statistics:
          env.request.cache.expensive_cache.infos()

        - Clearing the cache:
          env.request.cache.expensive_cache.clear()
    """
    def __init__(self, name):
        self.name = name

    def __call__(self, func):
        return _request_memoize(func, self.name)


class request_memoize_property(object):
    """
        Property decorator that cache the method result value only in the context of the current
        request. The method is accessible like a Python @property, and the cache is stored into
        the env.request.cache object.

        Usage :

        @request_memoize_property("my_property_cache")
        def my_property(self):
            pass

        The created caching object provide the following API:
        - Cache hits/misses/size statistics:
          env.request.cache.my_property_cache.infos()

        - Clearing the cache:
          env.request.cache.my_property_cache.clear()
    """
    def __init__(self, name):
        self.name = name

    def __call__(self, func):
        return _request_memoize_property(func, self.name)
