import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import AuthRateBucket


class RateLimitExceeded(Exception):
    def __init__(self, retry_after):
        self.retry_after = max(1, int(retry_after))


def _digest(operation, subject):
    key = settings.SECRET_KEY.encode("utf-8")
    message = f"{operation}\0{subject}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _bucket(operation, subject, window, now):
    key_digest = _digest(operation, subject)
    bucket, _ = AuthRateBucket.objects.select_for_update().get_or_create(
        operation=operation,
        key_digest=key_digest,
        defaults={"count": 0, "expires_at": now + window},
    )
    if bucket.expires_at <= now:
        bucket.count = 0
        bucket.expires_at = now + window
        bucket.save(update_fields=["count", "expires_at"])
    return bucket


def reserve_many(operations, increment=False):
    now = timezone.now()
    with transaction.atomic():
        AuthRateBucket.objects.filter(expires_at__lte=now).delete()
        buckets = [
            (limit, _bucket(operation, subject, window, now))
            for operation, subject, limit, window in operations
        ]
        blocked = [bucket for limit, bucket in buckets if bucket.count >= limit]
        if blocked:
            raise RateLimitExceeded((min(b.expires_at for b in blocked) - now).total_seconds())
        if increment:
            for _, bucket in buckets:
                bucket.count += 1
                bucket.save(update_fields=["count"])


def reserve(operation, subject, limit, window, increment=False):
    reserve_many([(operation, subject, limit, window)], increment=increment)


def check_login_limits(email, ip):
    quarter_hour = timedelta(minutes=15)
    reserve_many([
        ("login_email", email, 5, quarter_hour),
        ("login_ip", ip, 20, quarter_hour),
    ])


def record_login_failure(email, ip):
    quarter_hour = timedelta(minutes=15)
    reserve_many([
        ("login_email", email, 5, quarter_hour),
        ("login_ip", ip, 20, quarter_hour),
    ], increment=True)


def clear_login_failures(email, ip):
    AuthRateBucket.objects.filter(
        operation__in=["login_email", "login_ip"],
        key_digest__in=[_digest("login_email", email), _digest("login_ip", ip)],
    ).delete()


def count_registration(ip):
    reserve("register_ip", ip, 5, timedelta(hours=1), increment=True)
