import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CLIENT = "client"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_CLIENT, "Клиент"),
        (ROLE_ADMIN, "Администратор"),
    ]

    role = models.CharField("Роль", max_length=20, choices=ROLE_CHOICES, default=ROLE_CLIENT)
    phone = models.CharField("Телефон", max_length=20, blank=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.ROLE_ADMIN
        super().save(*args, **kwargs)

    @property
    def is_client(self):
        return self.role == self.ROLE_CLIENT

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    @property
    def full_name(self):
        return self.get_full_name() or self.username

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"


class Category(models.Model):
    name = models.CharField("Название", max_length=100)
    slug = models.SlugField("URL-имя", max_length=100, unique=True)
    description = models.CharField("Описание", max_length=200, blank=True)
    icon = models.CharField("Иконка (эмодзи)", max_length=8, blank=True, default="☕")
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("Показывать на сайте", default=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", verbose_name="Категория"
    )
    name = models.CharField("Название", max_length=120)
    slug = models.SlugField("URL-имя", max_length=140, unique=True)
    description = models.TextField("Описание", blank=True)
    composition = models.CharField("Состав", max_length=200, blank=True)
    price = models.DecimalField("Цена, ₽", max_digits=8, decimal_places=2)
    volume = models.CharField("Объём / вес", max_length=30, blank=True, help_text="Например: 350 мл")
    image = models.ImageField("Фото", upload_to="products/", blank=True)
    is_active = models.BooleanField("В продаже", default=True)
    is_featured = models.BooleanField("На главной", default=False)
    created_at = models.DateTimeField("Добавлен", auto_now_add=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["category__sort_order", "name"]

    def __str__(self):
        return self.name


class Sticker(models.Model):
    name = models.CharField("Название", max_length=60)
    symbol = models.CharField("Стикер (эмодзи)", max_length=8)
    is_active = models.BooleanField("Доступен", default=True)

    class Meta:
        verbose_name = "Стикер"
        verbose_name_plural = "Стикеры"
        ordering = ["name"]

    def __str__(self):
        return f"{self.symbol} {self.name}"


class Order(models.Model):
    STATUS_NEW = "new"
    STATUS_PREPARING = "preparing"
    STATUS_READY = "ready"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_NEW, "Принят"),
        (STATUS_PREPARING, "Готовится"),
        (STATUS_READY, "Готов к выдаче"),
        (STATUS_COMPLETED, "Выдан"),
        (STATUS_CANCELLED, "Отменён"),
    ]
    STATUS_CLASSES = {
        STATUS_NEW: "status-new",
        STATUS_PREPARING: "status-preparing",
        STATUS_READY: "status-ready",
        STATUS_COMPLETED: "status-completed",
        STATUS_CANCELLED: "status-cancelled",
    }
    STATUS_FLOW = [STATUS_NEW, STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED]
    # Заказ считается проданным, если он не отменён.
    SOLD_STATUSES = [STATUS_NEW, STATUS_PREPARING, STATUS_READY, STATUS_COMPLETED]

    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="orders", verbose_name="Клиент"
    )
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    comment = models.CharField("Комментарий", max_length=300, blank=True)
    staff_comment = models.CharField("Комментарий сотрудника", max_length=200, blank=True)
    pickup_time = models.DateTimeField("Время самовывоза", null=True, blank=True)
    total = models.DecimalField("Итого, ₽", max_digits=10, decimal_places=2, default=0)
    items_count = models.PositiveSmallIntegerField("Позиций", default=0)
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)
    completed_at = models.DateTimeField("Выдан", null=True, blank=True)

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-created_at"]

    @property
    def number(self):
        return f"К-{self.pk:05d}" if self.pk else "К-нов"

    @property
    def status_class(self):
        return self.STATUS_CLASSES.get(self.status, "status-new")

    @property
    def status_index(self):
        if self.status == self.STATUS_CANCELLED:
            return -1
        return self.STATUS_FLOW.index(self.status) if self.status in self.STATUS_FLOW else 0

    @property
    def is_active(self):
        return self.status in (self.STATUS_NEW, self.STATUS_PREPARING, self.STATUS_READY)

    def __str__(self):
        return f"{self.number} — {self.client.full_name}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="Заказ"
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Товар"
    )
    name = models.CharField("Название на момент заказа", max_length=120)
    price = models.DecimalField("Цена на момент заказа, ₽", max_digits=8, decimal_places=2)
    quantity = models.PositiveSmallIntegerField("Количество", default=1)

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказа"

    @property
    def total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.name} × {self.quantity}"


class OrderSticker(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="stickers", verbose_name="Заказ"
    )
    sticker = models.ForeignKey(
        Sticker, on_delete=models.PROTECT, related_name="usages", verbose_name="Стикер"
    )
    x = models.FloatField("Позиция X, %", default=50)
    y = models.FloatField("Позиция Y, %", default=50)
    scale = models.FloatField("Масштаб", default=1)
    rotation = models.SmallIntegerField("Поворот, °", default=0)

    class Meta:
        verbose_name = "Стикер на стакане"
        verbose_name_plural = "Стикеры на стакане"

    def __str__(self):
        return f"{self.sticker.symbol} @ {self.x:.0f}%, {self.y:.0f}%"


class BlogPost(models.Model):
    title = models.CharField("Заголовок", max_length=200)
    slug = models.SlugField("URL-имя", max_length=200, unique=True)
    excerpt = models.CharField("Краткое описание", max_length=300)
    body = models.TextField("Текст статьи")
    cover_image = models.ImageField("Обложка", upload_to="blog/", blank=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Автор")
    is_published = models.BooleanField("Опубликована", default=True)
    published_at = models.DateTimeField("Дата публикации", auto_now_add=True)

    class Meta:
        verbose_name = "Статья блога"
        verbose_name_plural = "Статьи блога"
        ordering = ["-published_at"]

    @property
    def reading_minutes(self):
        return max(1, len(self.body.split()) // 180 + 1)

    def __str__(self):
        return self.title
