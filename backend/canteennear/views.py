import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.generic import ListView
from django.db.models import Exists, OuterRef
from .models import APIKey, Canteen, EmailConfirmation, Review, APIUsage
from .models import SupportChat, SupportMessage
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.utils.decorators import method_decorator
from django.utils.html import strip_tags
from django.utils import timezone
from .forms import UserRegisterForm
from django.contrib import messages
from geopy.distance import geodesic

def _catalog_api_key():
    return getattr(settings, "TWO_GIS_MAP_KEY", "")


def send_confirmation_email(request, user):
    confirmation = EmailConfirmation.create_for_user(user)
    confirmation_link = request.build_absolute_uri(
        reverse("confirm_email", args=[confirmation.token])
    )
    context = {
        "user": user,
        "confirmation_link": confirmation_link,
        "site_name": "Столовая Рядом",
    }
    subject = render_to_string(
        "email_confirmation_subject.txt",
        context,
    ).strip()
    text_body = render_to_string(
        "email_confirmation_email.txt",
        context,
    )
    html_body = render_to_string(
        "email_confirmation_email.html",
        context,
    )

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email_message.attach_alternative(html_body, "text/html")
    email_message.send(fail_silently=False)


def email_confirmed_required(user):
    return EmailConfirmation.objects.filter(user=user, used_at__isnull=False).exists()

def home(request):
    canteens = Canteen.objects.order_by('-rating', 'name')[:6]
    return render(request, "home.html", {"canteens": canteens})

def search(request):
    query = request.GET.get("q", "").strip()
    user_lat, user_lng = None, None
    
    if query:
        # Геокодируем адрес через 2GIS
        geo_url = (
            f"https://catalog.api.2gis.com/3.0/items/geocode?q=Казань, {query}"
            f"&fields=items.point&key={_catalog_api_key()}"
        )
        try:
            res = requests.get(geo_url).json()
            point = res['result']['items'][0]['point']
            user_lat, user_lng = point['lat'], point['lon']
            
            # Подгружаем новые места из 2GIS в базу
            fetch_2gis_orgs(user_lat, user_lng)
        except:
            pass

    all_canteens = (
        Canteen.objects.exclude(lat__isnull=True)
        .exclude(lng__isnull=True)
    )
    filtered_canteens = []

    if user_lat:
        for c in all_canteens:
            dist = geodesic((user_lat, user_lng), (c.lat, c.lng)).meters
            if dist <= 1500:
                c.distance = int(dist)
                filtered_canteens.append(c)
        filtered_canteens.sort(key=lambda x: x.distance)
    else:
        filtered_canteens = all_canteens.order_by('-rating')[:10]

    map_markers = [
        {
            "id": c.id,
            "lat": float(c.lat),
            "lng": float(c.lng),
            "name": c.name,
            "address": c.address,
            "detail_url": reverse("canteen_detail", kwargs={"id": c.id}),
        }
        for c in all_canteens
    ]
    map_options = {
        "center_lat": float(user_lat) if user_lat is not None else 55.7961,
        "center_lng": float(user_lng) if user_lng is not None else 49.1064,
        "user_lat": float(user_lat) if user_lat is not None else None,
        "user_lng": float(user_lng) if user_lng is not None else None,
    }

    return render(request, "search.html", {
        "all_canteens": all_canteens,
        "filtered_canteens": filtered_canteens,
        "query": query,
        "user_lat": user_lat,
        "user_lng": user_lng,
        "gis_map_key": settings.TWO_GIS_MAP_KEY,
        "map_markers": map_markers,
        "map_options": map_options,
    })

def canteen_detail(request, id):
    canteen = get_object_or_404(Canteen, id=id)
    reviews = canteen.reviews.filter(approved=True).order_by('-created_at')
    
    if request.method == "POST" and request.user.is_authenticated:
        # Запретить оставлять отзывы заблокированным пользователям
        if APIKey.objects.filter(user=request.user, user_blocked=True).exists():
            messages.warning(request, "Ваш аккаунт заблокирован и вы более не можете оставлять отзывы. Для получения дополнительной информации обратитесь в поддержку.")
            return redirect(reverse("canteen_detail", kwargs={"id": canteen.id}))
        text = request.POST.get("text", "").strip()
        rating = request.POST.get("rating", "5")
        
        # Базовая защита: текст не пустой, рейтинг от 1 до 5
        if text and rating.isdigit() and 1 <= int(rating) <= 5:
            # 1. Создаем и сохраняем отзыв
            Review.objects.create(
                canteen=canteen,
                user=request.user,
                text=text[:1000],
                rating=int(rating),
                approved=False,
            )
            # 2. Мгновенно обновляем рейтинг столовой
            canteen.update_rating()

            url = reverse("canteen_detail", kwargs={"id": canteen.id})
            if request.GET.get("from") == "reviews":
                url = f"{url}?from=reviews"
            return redirect(url)

    hide_map = request.GET.get("from") == "reviews"
    show_detail_map = bool(
        canteen.lat is not None and canteen.lng is not None and not hide_map
    )

    return render(request, "canteen_detail.html", {
        "canteen": canteen,
        "reviews": reviews,
        "hide_map": hide_map,
        "show_detail_map": show_detail_map,
        "gis_map_key": settings.TWO_GIS_MAP_KEY,
    })


@login_required
def developer_dashboard(request):
    if not email_confirmed_required(request.user):
        return redirect("email_confirmation_required")

    api_key = APIKey.objects.filter(user=request.user, is_active=True).first()
    raw_key = request.session.pop("developer_api_key", None)
    
    # Получаем информацию об использовании API
    daily_usage = 0
    daily_limit = 1000
    remaining_daily_usage = daily_limit
    if api_key:
        # Считаем использование по всем ключам пользователя, не только по текущему
        daily_usage = APIUsage.get_daily_usage_count_for_user(request.user)
        remaining_daily_usage = max(0, daily_limit - daily_usage)

    if request.method == "POST":
        api_key, raw_key = APIKey.create_for_user(request.user)
        if api_key is None:
            messages.warning(
                request,
                "Вам запрещено создавать новые API ключи. Обратитесь к администратору."
            )
        else:
            request.session["developer_api_key"] = raw_key
        return redirect("developer_dashboard")

    # Проверяем, есть ли активный заблокированный ключ у пользователя
    api_blocked = APIKey.objects.filter(user=request.user, is_active=True, is_blocked=True).exists()
    # Проверяем, заблокирован ли пользователь для создания новых ключей (флаг хранится на ключах)
    user_blocked = APIKey.objects.filter(user=request.user, user_blocked=True).exists()

    return render(request, "developer_dashboard.html", {
        "api_key": api_key,
        "raw_key": raw_key,
        "daily_usage": daily_usage,
        "daily_limit": daily_limit,
        "remaining_daily_usage": remaining_daily_usage,
        "api_blocked": api_blocked,
        "user_blocked": user_blocked,
    })


@login_required
def email_confirmation_required(request):
    if email_confirmed_required(request.user):
        return redirect("developer_dashboard")

    if request.method == "POST":
        try:
            send_confirmation_email(request, request.user)
            messages.success(
                request,
                f"Письмо для подтверждения отправлено на {request.user.email}."
            )
        except Exception:
            messages.warning(
                request,
                "Не удалось отправить письмо. Попробуйте позже."
            )
        return redirect("email_confirmation_required")

    return render(request, "email_confirmation_required.html", {
        "email": request.user.email,
    })


def confirm_email(request, token):
    confirmation = EmailConfirmation.objects.filter(token=token, is_active=True).first()
    if not confirmation:
        return render(request, "email_confirmation_invalid.html", {})

    confirmation.activate_user()
    messages.success(request, "Email успешно подтверждён! Ваш аккаунт активирован. Теперь вы можете войти.")
    return redirect('login')


def _staff_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_staff)(view_func)


@login_required
@_staff_required
def admin_panel(request):
    """Простая панель управления с вкладками; по умолчанию — ссылка на модерацию."""
    return render(request, "admin_panel.html", {})


@login_required
@_staff_required
def admin_delete_user(request):
    """Admin page: delete user by email with dry-run and confirmation."""
    from django.contrib.auth.models import User
    try:
        from .models import (
            EmailConfirmation, APIKey, APIUsage, SupportChat, SupportMessage, Review
        )
    except Exception:
        messages.error(request, "Не удалось загрузить модели для удаления пользователя.")
        return redirect('admin_panel')

    result = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        dry_run = request.POST.get('dry_run') == 'on'
        confirm = request.POST.get('confirm') == 'yes'

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            messages.warning(request, f"Пользователь с email {email} не найден.")
            return redirect('admin_delete_user')

        api_keys_qs = APIKey.objects.filter(user=user)
        api_usage_qs = APIUsage.objects.filter(api_key__in=api_keys_qs)
        support_msgs_qs = SupportMessage.objects.filter(sender=user)
        support_chats_qs = SupportChat.objects.filter(user=user)
        reviews_qs = Review.objects.filter(user=user)
        confirmations_qs = EmailConfirmation.objects.filter(user=user)

        result = {
            'user': user,
            'api_keys': api_keys_qs.count(),
            'api_usage': api_usage_qs.count(),
            'support_chats': support_chats_qs.count(),
            'support_messages': support_msgs_qs.count(),
            'reviews': reviews_qs.count(),
            'confirmations': confirmations_qs.count(),
            'dry_run': dry_run,
        }

        if not dry_run and confirm:
            # perform deletion
            api_usage_qs.delete()
            api_keys_qs.delete()
            support_msgs_qs.delete()
            support_chats_qs.delete()
            reviews_qs.delete()
            confirmations_qs.delete()
            user.delete()
            messages.success(request, f"Пользователь {email} и связанные данные удалены.")
            return redirect('admin_panel')

    return render(request, 'admin_delete_user.html', {'result': result})


@login_required
@_staff_required
def admin_users_list(request):
    """Admin page: list users with per-user delete buttons."""
    from django.contrib.auth.models import User
    try:
        from .models import (
            EmailConfirmation, APIKey, APIUsage, SupportChat, SupportMessage, Review
        )
    except Exception:
        messages.error(request, "Не удалось загрузить модели для удаления пользователя.")
        return redirect('admin_panel')

    users = User.objects.order_by('-date_joined')[:200]

    if request.method == 'POST':
        # Expecting 'delete_user_id' and 'confirm' in POST
        uid = request.POST.get('delete_user_id')
        confirm = request.POST.get('confirm') == 'yes'
        if uid and confirm:
            try:
                user = User.objects.get(pk=int(uid))
            except Exception:
                messages.warning(request, 'Пользователь не найден')
                return redirect('admin_users_list')

            api_keys_qs = APIKey.objects.filter(user=user)
            api_usage_qs = APIUsage.objects.filter(api_key__in=api_keys_qs)
            support_msgs_qs = SupportMessage.objects.filter(sender=user)
            support_chats_qs = SupportChat.objects.filter(user=user)
            reviews_qs = Review.objects.filter(user=user)
            confirmations_qs = EmailConfirmation.objects.filter(user=user)

            # Delete related data
            api_usage_qs.delete()
            api_keys_qs.delete()
            support_msgs_qs.delete()
            support_chats_qs.delete()
            reviews_qs.delete()
            confirmations_qs.delete()

            # Finally delete user
            user.delete()
            messages.success(request, 'Пользователь и все связанные данные удалены.')
            return redirect('admin_users_list')
        else:
            messages.warning(request, 'Нужна явная подтверждающая форма (confirm).')
            return redirect('admin_users_list')

    return render(request, 'admin_users_list.html', {'users': users})


@login_required
@_staff_required
def moderation_view(request):
    """Список пока не одобренных отзывов и действия approve/delete."""
    if request.method == "POST":
        action = request.POST.get("action")
        rid = request.POST.get("review_id")
        try:
            review = Review.objects.get(pk=int(rid))
        except Exception:
            review = None

        if review and action == "approve":
            review.approved = True
            review.save()
            review.canteen.update_rating()
        elif review and action == "delete":
            canteen = review.canteen
            review.delete()
            canteen.update_rating()

        return redirect("admin_moderation")

    pending = Review.objects.filter(approved=False).order_by("-created_at")
    return render(request, "moderation.html", {"pending": pending})


@login_required
@_staff_required
def api_analytics_view(request):
    """Аналитика по API использованию и управление ключами пользователей."""
    from django.utils import timezone
    from datetime import timedelta
    
    if request.method == "POST":
        action = request.POST.get("action")
        user_id = request.POST.get("user_id")
        
        try:
            user = User.objects.get(pk=int(user_id))
        except Exception:
            user = None
        
        if user:
            if action == "block_user":
                # Блокируем пользователя для создания новых ключей и делаем все его ключи нерабочими
                APIKey.objects.filter(user=user).update(user_blocked=True, is_blocked=True)
                messages.success(request, f"Пользователь {user.username} заблокирован. Новые ключи создаваться не будут и существующие ключи заблокированы.")
            elif action == "unblock_user":
                # Разблокируем пользователя и все его ключи
                APIKey.objects.filter(user=user).update(user_blocked=False, is_blocked=False)
                messages.success(request, f"Пользователь {user.username} разблокирован и ключи восстановлены.")
            elif action == "block_key":
                key_id = request.POST.get("key_id")
                try:
                    api_key = APIKey.objects.get(pk=int(key_id))
                    api_key.is_blocked = True
                    api_key.save()
                    messages.success(request, f"API ключ пользователя {user.username} заблокирован.")
                except Exception:
                    pass
            elif action == "unblock_key":
                key_id = request.POST.get("key_id")
                try:
                    api_key = APIKey.objects.get(pk=int(key_id))
                    api_key.is_blocked = False
                    api_key.save()
                    messages.success(request, f"API ключ пользователя {user.username} разблокирован.")
                except Exception:
                    pass
        
        return redirect("admin_api_analytics")
    
    # Получаем всех пользователей с активными API ключами
    users_with_api = User.objects.filter(
        api_keys__is_active=True
    ).distinct()
    
    cutoff_time = timezone.now() - timedelta(hours=24)
    
    # Готовим данные для каждого пользователя
    api_stats = []
    for user in users_with_api:
        api_keys = APIKey.objects.filter(user=user, is_active=True)
        daily_usage = APIUsage.objects.filter(
            api_key__in=api_keys,
            timestamp__gte=cutoff_time
        ).count()
        
        is_user_blocked = APIKey.objects.filter(user=user, user_blocked=True).exists()
        
        api_stats.append({
            'user': user,
            'api_keys': api_keys,
            'daily_usage': daily_usage,
            'daily_limit': 1000,
            'remaining': max(0, 1000 - daily_usage),
            'usage_percent': int((daily_usage / 1000) * 100),
            'is_user_blocked': is_user_blocked,
        })
    
    # Сортируем по использованию (больше всего используют первыми)
    api_stats.sort(key=lambda x: x['daily_usage'], reverse=True)
    
    return render(request, "api_analytics.html", {
        "api_stats": api_stats,
    })


@login_required
def support_view(request):
    """Пользовательская вкладка поддержки: список чатов и создание нового."""
    # Список чатов пользователя
    chats = SupportChat.objects.filter(user=request.user).order_by('-created_at')

    if request.method == 'POST':
        subject = request.POST.get('subject', '').strip()
        initial_msg = request.POST.get('message', '').strip()
        chat = SupportChat.objects.create(user=request.user, subject=subject)
        if initial_msg:
            SupportMessage.objects.create(chat=chat, sender=request.user, text=initial_msg, from_admin=False)
        return redirect('support_chat', chat_id=chat.id)

    return render(request, 'support_user_list.html', {'chats': chats, 'suppress_messages': True})


@login_required
def support_chat_view(request, chat_id):
    chat = get_object_or_404(SupportChat, pk=chat_id, user=request.user)

    # Пользователь не может писать в закрытый чат
    if chat.is_closed and request.method == 'POST':
        messages.warning(request, 'Чат закрыт — вы не можете отправлять сообщения.')
        return redirect('support_chat', chat_id=chat.id)

    if request.method == 'POST' and not chat.is_closed:
        if 'close_chat' in request.POST:
            chat.close()
            messages.success(request, 'Чат закрыт.')
            return redirect('support')
        text = request.POST.get('message', '').strip()
        if text:
            SupportMessage.objects.create(chat=chat, sender=request.user, text=text, from_admin=False)
        return redirect('support_chat', chat_id=chat.id)
    messages_qs = chat.messages.select_related('sender').all()
    return render(request, 'support_chat.html', {'chat': chat, 'messages': messages_qs, 'suppress_messages': True})


@login_required
@_staff_required
def admin_support_list(request):
    """Админская панель — список активных чатов (open)."""
    active_chats = SupportChat.objects.filter(is_closed=False).order_by('-created_at')
    return render(request, 'admin_support_list.html', {'chats': active_chats, 'suppress_messages': True})


@login_required
@_staff_required
def admin_support_chat(request, chat_id):
    chat = get_object_or_404(SupportChat, pk=chat_id)

    if request.method == 'POST':
        if 'close_chat' in request.POST:
            chat.close()
            messages.success(request, 'Чат закрыт.')
            return redirect('admin_support_list')
        text = request.POST.get('message', '').strip()
        if text:
            # Администратор отправляет сообщение
            SupportMessage.objects.create(chat=chat, sender=request.user, text=text, from_admin=True)
        return redirect('admin_support_chat', chat_id=chat.id)
    messages_qs = chat.messages.select_related('sender').all()
    return render(request, 'admin_support_chat.html', {'chat': chat, 'messages': messages_qs, 'suppress_messages': True})


@login_required
@_staff_required
def admin_support_archive(request):
    closed = SupportChat.objects.filter(is_closed=True).order_by('-closed_at')
    return render(request, 'admin_support_archive.html', {'chats': closed, 'suppress_messages': True})

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Создаём неактивного пользователя
            user.save()
            username = form.cleaned_data.get('username')
            try:
                send_confirmation_email(request, user)
                return render(request, 'email_confirmation_pending.html', {
                    'email': user.email,
                })
            except Exception:
                messages.warning(
                    request,
                    f'Аккаунт создан для {username}, но письмо на {user.email} не удалось отправить. Попробуйте позже.',
                )
                return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'register.html', {'form': form})


# Запросы к 2GIS Catalog API: отдельный поисковый запрос на каждый тип заведения,
# затем объединение результатов (параметр `q` задаёт текстовый поиск по рубрикам/названиям).
FOOD_PLACE_QUERIES = (
    "столовая",
    "кафе",
    "ресторан",
    "бар",
    "пиццерия",
    "кофейня",
    "фастфуд",
    "стейк-хаус",
)


class EstablishmentsWithReviewsView(ListView):
    """Заведения, у которых есть хотя бы один отзыв."""
    model = Canteen
    template_name = "reviews_list.html"
    context_object_name = "canteens"

    def get_queryset(self):
        return (
            Canteen.objects.filter(Exists(Review.objects.filter(canteen_id=OuterRef("pk"), approved=True)))
            .order_by("-rating", "name")
        )


def fetch_2gis_orgs(lat, lng):
    """Подгружаем заведения общепита из 2GIS вокруг точки (несколько поисковых запросов)."""
    url = "https://catalog.api.2gis.com/3.0/items"
    base_params = {
        "point": f"{lng},{lat}",
        "radius": 1000,
        "fields": "items.point,items.address_name,items.schedule",
        "key": _catalog_api_key(),
    }
    for q in FOOD_PLACE_QUERIES:
        params = {**base_params, "q": q}
        try:
            res = requests.get(url, params=params, timeout=10).json()
            for item in res.get("result", {}).get("items", []):
                name = item.get("name")
                address = item.get("address_name", "Адрес не указан")
                point = item.get("point") or {}
                plat, plng = point.get("lat"), point.get("lon")
                if plat is None or plng is None:
                    continue
                if not Canteen.objects.filter(lat=plat, lng=plng).exists():
                    Canteen.objects.create(
                        name=name,
                        address=address,
                        lat=plat,
                        lng=plng,
                    )
        except Exception:
            continue