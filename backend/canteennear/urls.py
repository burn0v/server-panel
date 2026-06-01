from django.contrib import admin
from django.urls import path, include
from django.contrib.auth.views import LoginView, PasswordResetView
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
    path(
        "accounts/password_reset/",
        PasswordResetView.as_view(
            template_name='registration/password_reset_form.html',
            email_template_name='registration/password_reset_email.txt',
            subject_template_name='registration/password_reset_subject.txt',
            html_email_template_name='registration/password_reset_email.html',
        ),
        name='password_reset',
    ),
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
    path("admin-panel/delete-user/", views.admin_delete_user, name="admin_delete_user"),
    path("admin-panel/users/", views.admin_users_list, name="admin_users_list"),
]
