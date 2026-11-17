from datetime import timedelta

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone
from django.utils.text import slugify

from .models import BlogPost, Category, Order, Product, Sticker, User


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", "form-control")
            else:
                widget.attrs.setdefault("class", "form-control")


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.CharField(label="Логин", widget=forms.TextInput(attrs={"autofocus": True}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)


class RegisterForm(StyledFormMixin, UserCreationForm):
    email = forms.EmailField(label="E-mail", required=True)
    phone = forms.CharField(label="Телефон", max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с таким e-mail уже зарегистрирован.")
        return email


class CheckoutForm(StyledFormMixin, forms.Form):
    pickup_time = forms.DateTimeField(
        label="Время самовывоза",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text="Если не указать — приготовим как можно скорее.",
    )
    comment = forms.CharField(
        label="Комментарий к заказу",
        required=False,
        max_length=300,
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "Например: без сахара, овсяное молоко"}
        ),
    )

    def clean_pickup_time(self):
        pickup_time = self.cleaned_data.get("pickup_time")
        if pickup_time and pickup_time < timezone.now() - timedelta(minutes=5):
            raise forms.ValidationError("Время самовывоза не может быть в прошлом.")
        return pickup_time


class _SlugMixin:
    """Заполняет slug из названия, если поле оставили пустым."""

    slug_source = "name"
    # Кириллица -> латиница, чтобы URL оставались ASCII.
    TRANSLIT = str.maketrans(
        {
            "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
            "ж": "zh", "з": "z", "и": "i", "й": "j", "к": "k", "л": "l", "м": "m",
            "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
            "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
            "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
        }
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "slug" in self.fields:
            self.fields["slug"].required = False

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        if slug:
            return slug
        source = (self.cleaned_data.get(self.slug_source) or "").lower().translate(self.TRANSLIT)
        base = slugify(source, allow_unicode=False) or "item"
        candidate, index = base, 2
        model = self._meta.model
        while model.objects.filter(slug=candidate).exclude(pk=self.instance.pk).exists():
            candidate = f"{base}-{index}"
            index += 1
        return candidate


class ProductForm(StyledFormMixin, _SlugMixin, forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "category", "name", "slug", "description", "composition", "price",
            "volume", "image", "is_active", "is_featured",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "slug": forms.TextInput(attrs={"placeholder": "заполнится автоматически"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.all()

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price <= 0:
            raise forms.ValidationError("Цена должна быть больше нуля.")
        return price


class CategoryForm(StyledFormMixin, _SlugMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "slug", "description", "icon", "sort_order", "is_active")
        widgets = {"slug": forms.TextInput(attrs={"placeholder": "заполнится автоматически"})}


class StickerForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Sticker
        fields = ("name", "symbol", "is_active")

    def clean_symbol(self):
        symbol = self.cleaned_data["symbol"].strip()
        if len(symbol) > 4:
            raise forms.ValidationError("Оставьте один эмодзи, например ☕ или 🌿.")
        return symbol


class PostForm(StyledFormMixin, _SlugMixin, forms.ModelForm):
    slug_source = "title"

    class Meta:
        model = BlogPost
        fields = ("title", "slug", "excerpt", "body", "cover_image", "is_published")
        widgets = {
            "body": forms.Textarea(attrs={"rows": 12}),
            "slug": forms.TextInput(attrs={"placeholder": "заполнится автоматически"}),
        }

    def clean_excerpt(self):
        excerpt = self.cleaned_data["excerpt"].strip()
        if len(excerpt) < 20:
            raise forms.ValidationError("Краткое описание — минимум 20 символов.")
        return excerpt


class OrderStatusForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(label="Новый статус", choices=Order.STATUS_CHOICES)
    comment = forms.CharField(
        label="Комментарий для клиента",
        required=False,
        max_length=200,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Например: заказ готов, можно забирать"}),
    )
