from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User
from .validators import validate_deliverable_email


class RegisterForm(forms.ModelForm):
    full_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "John Creator", "autocomplete": "name"})
    )
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        validate_deliverable_email(email)
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            password_validation.validate_password(p1)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data["full_name"].strip()
        parts = full_name.split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.username = self.cleaned_data["email"].split("@")[0] + "_" + User.objects.count().__str__()
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com", "autocomplete": "email", "autofocus": True})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "current-password"})
    )


class WalletAuthForm(forms.Form):
    wallet_address = forms.CharField(max_length=64)

    def clean_wallet_address(self):
        addr = self.cleaned_data["wallet_address"].strip()
        if not addr.lower().startswith("0x") or len(addr) < 10:
            raise forms.ValidationError("Enter a valid wallet address.")
        return addr


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "bio", "avatar"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 3, "placeholder": "Tell collectors about yourself..."}),
        }
