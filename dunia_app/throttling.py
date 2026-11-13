import hashlib
import hmac
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse


def rate_limit(scope, *, limit, window, methods=('POST',), include_user=True):
    """Apply a fixed-window throttle using the configured shared Django cache."""
    if limit < 1 or window < 1:
        raise ValueError('limit and window must be positive integers')

    def decorate(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method.upper() not in methods:
                return view_func(request, *args, **kwargs)

            remote_addr = request.META.get('REMOTE_ADDR', 'unknown')
            identities = [f'ip:{remote_addr}']
            user = getattr(request, 'user', None)
            if include_user and user and user.is_authenticated:
                identities.append(f'user:{user.pk}')

            for identity in identities:
                digest = hmac.new(
                    settings.SECRET_KEY.encode('utf-8'),
                    identity.encode('utf-8'),
                    hashlib.sha256,
                ).hexdigest()
                cache_key = f'dunia:ratelimit:{scope}:{digest}'
                if cache.add(cache_key, 1, timeout=window):
                    count = 1
                else:
                    try:
                        count = cache.incr(cache_key)
                    except ValueError:
                        cache.add(cache_key, 1, timeout=window)
                        count = 1
                if count > limit:
                    response = HttpResponse(
                        'Trop de requêtes. Veuillez réessayer plus tard.',
                        status=429,
                        content_type='text/plain; charset=utf-8',
                    )
                    response['Retry-After'] = str(window)
                    response['Cache-Control'] = 'no-store'
                    return response

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorate
