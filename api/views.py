from django.contrib.postgres.search import SearchQuery

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from canteennear.models import APIKey, APIUsage, Review

from .review_balancer import select_balanced_reviews
from .search import build_search_query, is_postgresql, search_canteens
from .serializers import AgentCanteenSerializer

# Константы для API лимитов
DAILY_API_LIMIT = 1000


class AgentCanteenSearchView(APIView):
    """
    GET /api/agent/search/?query=вкусный+шашлык

    Полнотекстовый поиск заведений + до 5 сбалансированных отзывов на каждое.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        api_key = self._authenticate_api_key(request)
        if not api_key:
            raise AuthenticationFailed(
                "API-ключ обязателен. Передайте заголовок Authorization: Bearer <ваш_ключ> или X-API-Key."
            )
        
        # Проверяем, не заблокирован ли ключ или пользователь
        if api_key.is_blocked:
            return Response(
                {
                    "detail": "Ваш API ключ заблокирован администратором.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        if api_key.user_blocked:
            return Response(
                {
                    "detail": "Вам запрещено использовать API. Обратитесь к администратору.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Проверяем суточный лимит по пользователю, не по конкретному ключу
        user = api_key.user
        daily_usage = APIUsage.get_daily_usage_count_for_user(user)
        if daily_usage >= DAILY_API_LIMIT:
            return Response(
                {
                    "detail": f"Достигнут суточный лимит запросов ({DAILY_API_LIMIT}). Попробуйте позже.",
                    "daily_limit": DAILY_API_LIMIT,
                    "daily_usage": daily_usage,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        raw_query = (request.query_params.get("query") or "").strip()
        if not raw_query:
            return Response(
                {"detail": "Параметр query обязателен, например ?query=вкусный шашлык"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not is_postgresql():
            return Response(
                {
                    "detail": (
                        "Эндпоинт использует PostgreSQL Full-Text Search. "
                        "Запустите проект с PostgreSQL (без USE_SQLITE=1)."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            limit = min(int(request.query_params.get("limit", 20)), 50)
        except (TypeError, ValueError):
            limit = 20

        search_query: SearchQuery = build_search_query(raw_query)
        canteens = search_canteens(raw_query, limit=limit)

        payload = []
        for canteen in canteens:
            reviews_qs = Review.objects.filter(canteen=canteen, approved=True)
            balanced = select_balanced_reviews(reviews_qs, search_query)
            payload.append(
                {
                    "id": canteen.id,
                    "name": canteen.name,
                    "address": canteen.address,
                    "rating": canteen.rating,
                    "reviews": [
                        {
                            "id": review.id,
                            "rating": review.rating,
                            "text": review.text,
                            "created_at": review.created_at,
                        }
                        for review in balanced
                    ],
                }
            )

        # Логируем использование API
        APIUsage.log_usage(api_key)
        # Пересчитываем использование по пользователю
        daily_usage = APIUsage.get_daily_usage_count_for_user(user)

        serializer = AgentCanteenSerializer(payload, many=True)
        return Response(
            {
                "query": raw_query,
                "count": len(serializer.data),
                "results": serializer.data,
                "daily_usage": daily_usage,
                "daily_limit": DAILY_API_LIMIT,
            }
        )

    def _authenticate_api_key(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        raw_key = None
        if auth_header.startswith("Bearer "):
            raw_key = auth_header[len("Bearer "):].strip()
        elif request.META.get("HTTP_X_API_KEY"):
            raw_key = request.META.get("HTTP_X_API_KEY").strip()

        if not raw_key:
            return None

        key_hash = APIKey.hash_key(raw_key)
        return APIKey.objects.filter(key_hash=key_hash, is_active=True).first()
