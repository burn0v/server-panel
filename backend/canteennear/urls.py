from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView
from . import views
from .forms import UserLoginForm

urlpatterns = [
    path("", views.home, name="home"),
    path('admin/', admin.site.urls),
    path("search/", views.search, name="search"),
    path(
        "reviews/",
        views.EstablishmentsWithReviewsView.as_view(),
        name="reviews_list",
    ),
    path("canteen/<int:id>/", views.canteen_detail, name="canteen_detail"),
    path("register/", views.register, name="register"),
    path("accounts/login/", LoginView.as_view(
        template_name='registration/login.html',
        authentication_form=UserLoginForm
    ), name='login'),
    path("accounts/", include("django.contrib.auth.urls")),
    path("developers/", views.developer_dashboard, name="developer_dashboard"),
    path("support/", views.support_view, name="support"),
    path("support/<int:chat_id>/", views.support_chat_view, name="support_chat"),
    path("developers/confirm-needed/", views.email_confirmation_required, name="email_confirmation_required"),
    path("developers/confirm-email/<str:token>/", views.confirm_email, name="confirm_email"),
    path("api/", include("api.urls")),
    path("admin-panel/", views.admin_panel, name="admin_panel"),
    path("admin-panel/moderation/", views.moderation_view, name="admin_moderation"),
    path("admin-panel/api-analytics/", views.api_analytics_view, name="admin_api_analytics"),
    path("admin-panel/support/", views.admin_support_list, name="admin_support_list"),
    path("admin-panel/support/<int:chat_id>/", views.admin_support_chat, name="admin_support_chat"),
    path("admin-panel/support/archive/", views.admin_support_archive, name="admin_support_archive"),
]
