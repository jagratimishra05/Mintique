from decimal import Decimal

from django import forms

from .models import Wallet

TOKEN_CHOICES = [(symbol, symbol) for symbol in Wallet.BALANCE_FIELDS]


class SwapForm(forms.Form):
    """Any-token-to-any-token swap. Both fields default to ETH/MNQ so the
    widget behaves the same as before when a user hasn't touched the token
    pickers, but any of the wallet's supported currencies can now be
    selected on either side."""
    from_token = forms.ChoiceField(choices=TOKEN_CHOICES, widget=forms.HiddenInput())
    to_token = forms.ChoiceField(choices=TOKEN_CHOICES, widget=forms.HiddenInput())
    amount = forms.DecimalField(
        min_value=Decimal("0.000001"),
        max_digits=18,
        decimal_places=8,
        widget=forms.NumberInput(attrs={"placeholder": "0.00", "step": "any"}),
    )

    def clean(self):
        cleaned = super().clean()
        from_token, to_token = cleaned.get("from_token"), cleaned.get("to_token")
        if from_token and to_token and from_token == to_token:
            raise forms.ValidationError("Choose two different currencies to swap between.")
        return cleaned


class ConnectWalletForm(forms.Form):
    wallet_address = forms.CharField(min_length=10, max_length=64)
