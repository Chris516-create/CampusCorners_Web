import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


PROFILE_ICON_CHOICES = (
    ("sparkle", "Star"),
    ("sparko", "Sparko"),
    ("flower", "Flower"),
    ("heart", "Heart"),
)
DEFAULT_PROFILE_ICON = "sparko"


def canonical_email(value):
    return (value or "").strip().casefold()


def is_allowed_ucla_domain(email):
    domain = canonical_email(email).rsplit("@", 1)[-1] if "@" in (email or "") else ""
    return domain in {"ucla.edu", "g.ucla.edu"}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def normalize_email(self, email):
        return canonical_email(email)

    def get_by_natural_key(self, username):
        return self.get(**{self.model.USERNAME_FIELD: canonical_email(username)})

    def create_user(self, email, nickname, password=None, **extra_fields):
        email = canonical_email(email)
        if not email:
            raise ValueError("An email address is required.")
        if not nickname:
            raise ValueError("A nickname is required.")
        user = self.model(email=email, nickname=nickname.strip(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, nickname, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superusers must have staff and superuser permissions.")
        return self.create_user(email, nickname, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    nickname = models.CharField(max_length=30)
    profile_icon = models.CharField(
        max_length=32,
        choices=PROFILE_ICON_CHOICES,
        default=DEFAULT_PROFILE_ICON,
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["nickname"]

    def save(self, *args, **kwargs):
        self.email = canonical_email(self.email)
        self.nickname = self.nickname.strip()
        super().save(*args, **kwargs)

    @property
    def ucla_email_claimed(self):
        return is_allowed_ucla_domain(self.email)

    @property
    def is_verified_ucla(self):
        return self.email_verified_at is not None and self.ucla_email_claimed

    def __str__(self):
        return self.nickname


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")
    promotional_email_opt_in = models.BooleanField(default=False)
    promotional_email_opt_in_at = models.DateTimeField(null=True, blank=True)
    promotional_email_revoked_at = models.DateTimeField(null=True, blank=True)
    preference_copy_version = models.CharField(max_length=32, default="v1")


class UserOnboarding(models.Model):
    class TourStatus(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    STEPS = ("filter", "details", "save", "route")

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="onboarding")
    version = models.PositiveSmallIntegerField(default=1)
    intro_seen = models.BooleanField(default=False)
    tour_status = models.CharField(
        max_length=16, choices=TourStatus.choices, default=TourStatus.NOT_STARTED
    )
    current_step = models.CharField(max_length=16, choices=[(s, s.title()) for s in STEPS], default="filter")
    skipped_steps = models.JSONField(default=list, blank=True)
    selected_tutorial_event_id = models.CharField(max_length=128, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    first_completed_at = models.DateTimeField(null=True, blank=True)


class SavedEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_events")
    event_id = models.CharField(max_length=128)
    saved_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "event_id"], name="saved_event_unique_per_user")
        ]
        indexes = [models.Index(fields=["user", "saved_at"], name="saved_event_user_time_idx")]


class AuthRateBucket(models.Model):
    operation = models.CharField(max_length=24)
    key_digest = models.CharField(max_length=64)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["operation", "key_digest"], name="auth_rate_bucket_unique")
        ]
        indexes = [models.Index(fields=["expires_at"], name="auth_rate_expiry_idx")]
