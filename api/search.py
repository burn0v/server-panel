"""
Полнотекстовый поиск заведений (PostgreSQL FTS).
"""

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import connection
from django.db.models import Case, F, Max, When

from canteennear.models import Canteen

SEARCH_CONFIG = "russian"
DEFAULT_LIMIT = 20
MIN_RANK = 0.01


def is_postgresql() -> bool:
    return connection.vendor == "postgresql"


def build_canteen_search_vector() -> SearchVector:
    return (
        SearchVector("name", weight="A", config=SEARCH_CONFIG)
        + SearchVector("reviews__text", weight="B", config=SEARCH_CONFIG)
    )


def build_search_query(raw_query: str) -> SearchQuery:
    return SearchQuery(raw_query, config=SEARCH_CONFIG)


def search_canteens(raw_query: str, *, limit: int = DEFAULT_LIMIT) -> list[Canteen]:
    """
    Ищет заведения по name и текстам отзывов.
    Сортировка — по SearchRank (релевантность), не по дате.
    """
    if not is_postgresql():
        raise RuntimeError("Full-text search requires PostgreSQL.")

    search_query = build_search_query(raw_query)
    vector = build_canteen_search_vector()

    ranked = (
        Canteen.objects.annotate(search=vector)
        .annotate(rank=SearchRank(F("search"), search_query))
        .values("pk")
        .annotate(best_rank=Max("rank"))
        .filter(best_rank__gte=MIN_RANK)
        .order_by("-best_rank")[:limit]
    )

    id_to_rank = {row["pk"]: row["best_rank"] for row in ranked}
    if not id_to_rank:
        return []

    order = Case(
        *[When(pk=pk, then=pos) for pos, pk in enumerate(id_to_rank.keys())]
    )
    canteens = list(Canteen.objects.filter(pk__in=id_to_rank).order_by(order))
    for canteen in canteens:
        canteen.fts_rank = id_to_rank[canteen.pk]
    return canteens
