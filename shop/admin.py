from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import BlogPost, Category, Order, OrderItem, OrderSticker, Product, Sticker, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Кофейня", {"fields": ("role", "phone")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Кофейня", {"fields": ("role", "phone", "email")}),
    )
    list_display = ("username", "full_name", "role", "email", "phone", "is_active")
    list_filter = ("role", "is_active")
    search_fields = ("username", "first_name", "last_name", "email", "phone")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "volume", "is_active", "is_featured")
    list_filter = ("category", "is_active", "is_featured")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Sticker)
class StickerAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "is_active")
    list_filter = ("is_active",)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


class OrderStickerInline(admin.TabularInline):
    model = OrderSticker
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "client", "status", "total", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("client__username", "comment")
    inlines = [OrderItemInline, OrderStickerInline]


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_published", "published_at")
    list_filter = ("is_published",)
    search_fields = ("title", "excerpt")
    prepopulated_fields = {"slug": ("title",)}
