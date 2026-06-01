import hashlib
import secrets

import requests
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.db.models import Avg
from django.utils import timezone

class Canteen(models.Model):
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    rating = models.FloatField(default=0)
    working_hours = models.CharField(max_length=200, default="Время работы не указано")
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    def save(self, *args, **kwargs):
        # Авто-поиск координат через 2GIS Geocoding
        if not self.lat or not self.lng:
            api_key = getattr(settings, "TWO_GIS_MAP_KEY", "")
            # Ищем координаты по адресу в Казани
            url = f"https://catalog.api.2gis.com/3.0/items/geocode?q=Казань, {self.address}&fields=items.point&key={api_key}"
            try:
                res = requests.get(url).json()
                point = res['result']['items'][0]['point']
                self.lat = point['lat']
                self.lng = point['lon']
            except:
                pass 
        super().save(*args, **kwargs)

    def update_rating(self):
        # Вычисляем среднюю оценку по всем отзывам этой столовой
        avg_rating = self.reviews.filter(approved=True).aggregate(Avg('rating'))['rating__avg']
        # Если отзывы есть, округляем до 1 знака. Если нет — ставим 0
        self.rating = round(avg_rating, 1) if avg_rating else 0
        self.save()

    def __str__(self):
        return self.name


class Review(models.Model):
    canteen = models.ForeignKey(Canteen, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    rating = models.IntegerField(default=5)
    approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Отзыв от {self.user.username} на {self.canteen.name}"


class APIKey(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False)  # Блокировка ключа администратором
    user_blocked = models.BooleanField(default=False)  # Блокировка создания новых ключей для пользователя

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "active" if self.is_active else "revoked"
        return f"API key for {self.user.username} ({status})"

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def create_for_user(cls, user):
        # Проверяем, не заблокирован ли пользователь
        if cls.objects.filter(user=user, user_blocked=True).exists():
            return None, None
        
        raw_key = secrets.token_hex(32)
        key_hash = cls.hash_key(raw_key)
        cls.objects.filter(user=user, is_active=True).update(is_active=False)
        api_key = cls.objects.create(user=user, key_hash=key_hash, is_active=True)
        return api_key, raw_key


class EmailConfirmation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_confirmations")
    token = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "active" if self.is_active else "used"
        return f"Email confirmation for {self.user.username} ({status})"

    @staticmethod
    def create_token() -> str:
        return secrets.token_urlsafe(32)

    @classmethod
    def create_for_user(cls, user):
        cls.objects.filter(user=user, is_active=True).update(is_active=False)
        token = cls.create_token()
        return cls.objects.create(user=user, token=token)

    def mark_used(self):
        self.is_active = False
        self.used_at = timezone.now()
        self.save()

    def activate_user(self):
        """Активирует пользователя и помечает подтверждение как использованное."""
        self.user.is_active = True
        self.user.save()
        self.mark_used()

    @property
    def is_valid(self) -> bool:
        return self.is_active and self.used_at is None


class APIUsage(models.Model):
    api_key = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name="usage_logs")
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["-timestamp"]
    
    def __str__(self):
        return f"APIUsage for {self.api_key} at {self.timestamp}"
    
    @classmethod
    def get_daily_usage_count(cls, api_key):
        """Возвращает количество использований API-ключа за последние 24 часа"""
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=24)
        return cls.objects.filter(
            api_key=api_key,
            timestamp__gte=cutoff_time
        ).count()
    
    @classmethod
    def get_daily_usage_count_for_user(cls, user):
        """Возвращает количество использований API всеми ключами пользователя за последние 24 часа"""
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=24)
        # Получаем все ключи пользователя
        user_api_keys = APIKey.objects.filter(user=user)
        # Считаем логи для всех ключей
        return cls.objects.filter(
            api_key__in=user_api_keys,
            timestamp__gte=cutoff_time
        ).count()
    
    @classmethod
    def log_usage(cls, api_key):
        """Логирует использование API-ключа"""
        return cls.objects.create(api_key=api_key)


class SupportChat(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="support_chats")
    subject = models.CharField(max_length=200, blank=True)
    is_closed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        status = "closed" if self.is_closed else "open"
        return f"SupportChat({self.user.username}) [{status}]"

    def close(self):
        from django.utils import timezone
        self.is_closed = True
        self.closed_at = timezone.now()
        self.save()


class SupportMessage(models.Model):
    chat = models.ForeignKey(SupportChat, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    from_admin = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        # Avoid verbose debug-like representation being displayed in templates/messages.
        # Return an empty string so accidental stringification doesn't show timestamps.
        return ""


def _user_email_confirmed(self):
    return EmailConfirmation.objects.filter(user=self, used_at__isnull=False).exists()

User.add_to_class("email_confirmed", property(_user_email_confirmed))
