"""
Сбалансированная выборка отзывов для LLM-агентов (макс. 5 на заведение).
"""

from __future__ import annotations

from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db.models import QuerySet

MAX_REVIEWS_DEFAULT = 5
SEARCH_CONFIG = "russian"

RATING_HIGH = frozenset({4, 5})
RATING_MID = frozenset({2, 3})
RATING_LOW = frozenset({1})


def _review_sort_key(review) -> tuple[float, float]:
    match = float(getattr(review, "match_rank", 0) or 0)
    created = review.created_at.timestamp() if review.created_at else 0.0
    return (-match, -created)


def _annotate_review_rank(
    reviews: QuerySet, search_query: SearchQuery | None
) -> QuerySet:
    if search_query is None:
        return reviews.order_by("-created_at")
    return reviews.annotate(
        match_rank=SearchRank(
            SearchVector("text", config=SEARCH_CONFIG),
            search_query,
        )
    ).order_by("-match_rank", "-created_at")


def _pick(
    pool: list,
    ratings: frozenset[int] | set[int],
    count: int,
    selected_ids: set[int],
) -> list:
    if count <= 0:
        return []
    candidates = [
        review
        for review in pool
        if review.rating in ratings and review.id not in selected_ids
    ]
    candidates.sort(key=_review_sort_key)
    picked = candidates[:count]
    selected_ids.update(review.id for review in picked)
    return picked


def _choose_plan(pool: list) -> list[tuple[frozenset[int] | set[int], int]]:
    has_low = any(review.rating in RATING_LOW for review in pool)
    has_mid = any(review.rating in RATING_MID for review in pool)
    only_high = bool(pool) and all(review.rating in RATING_HIGH for review in pool)

    if has_low:
        return [(RATING_HIGH, 2), (RATING_MID, 2), (RATING_LOW, 1)]
    if has_mid:
        return [(RATING_HIGH, 3), (RATING_MID, 2)]
    if only_high:
        return [({5}, 3), ({4}, 2)]
    return [(RATING_HIGH, MAX_REVIEWS_DEFAULT)]


def select_balanced_reviews(
    reviews: QuerySet,
    search_query: SearchQuery | None,
    *,
    max_reviews: int = MAX_REVIEWS_DEFAULT,
) -> list:
    """
    План A: 2×(5–4★) + 2×(3–2★) + 1×(1★), если есть однозвёздочные.
    План B: 3×(5–4★) + 2×(3–2★), если нет 1★.
    План C: 3×5★ + 2×4★, если только «хорошие» отзывы.
    Внутри категории приоритет — совпадение с FTS-запросом (match_rank).
    """
    pool = list(_annotate_review_rank(reviews, search_query)[:80])
    if not pool:
        return []

    selected: list = []
    selected_ids: set[int] = set()

    for ratings, quota in _choose_plan(pool):
        if len(selected) >= max_reviews:
            break
        need = min(quota, max_reviews - len(selected))
        selected.extend(_pick(pool, ratings, need, selected_ids))

    if len(selected) < max_reviews:
        for review in sorted(pool, key=_review_sort_key):
            if review.id in selected_ids:
                continue
            selected.append(review)
            selected_ids.add(review.id)
            if len(selected) >= max_reviews:
                break

    return selected[:max_reviews]
