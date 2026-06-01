from django.urls import path

from .views import AgentCanteenSearchView

urlpatterns = [
    path("agent/search/", AgentCanteenSearchView.as_view(), name="api_agent_search"),
]
