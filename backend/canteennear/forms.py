from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Электронная почта")

    class Meta:
        model = User
        fields = ["username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = "Имя пользователя"
        self.fields['username'].help_text = "До 150 символов. Только буквы, цифры и символы @/./+/-/_"
        self.fields['password1'].label = "Пароль"
        self.fields['password1'].help_text = (
            "• Пароль не может быть слишком похож на другую вашу личную информацию.<br>"
            "• Пароль должен содержать минимум 8 символов.<br>"
            "• Пароль не может быть полностью числовым."
        )
        self.fields['password2'].label = "Подтверждение пароля"
        self.fields['password2'].help_text = "Введите тот же пароль для проверки"

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user


class UserLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = "Имя пользователя"
        self.fields['password'].label = "Пароль"

    error_messages = {
        'invalid_login': _(
            "Введите правильное имя пользователя и пароль. "
            "Обратите внимание, что оба поля могут быть чувствительны к регистру."
        ),
        'inactive': _("Этот аккаунт не активирован."),
    }