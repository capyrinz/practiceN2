from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import path

from shop import views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    # витрина
    path("", views.home, name="home"),
    path("menu/", views.menu, name="menu"),
    path("menu/<slug:slug>/", views.product_detail, name="product_detail"),
    path("blog/", views.blog, name="blog"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("order/<uuid:token>/", views.order_public, name="order_public"),
    # аккаунт
    path("register/", views.register, name="register"),
    path("login/", views.AppLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # корзина
    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:product_id>/", views.cart_add, name="cart_add"),
    path("cart/update/<int:product_id>/", views.cart_update, name="cart_update"),
    path("cart/remove/<int:product_id>/", views.cart_remove, name="cart_remove"),
    # стикер-студия
    path("sticker-studio/", views.stub_kit, name="stub_kit"),
    path("sticker-studio/save/", views.stub_kit_save, name="stub_kit_save"),
    path("sticker-studio/clear/", views.stub_kit_clear, name="stub_kit_clear"),
    # заказы клиента
    path("checkout/", views.checkout, name="checkout"),
    path("my-orders/", views.my_orders, name="my_orders"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/receipt.pdf", views.receipt_pdf, name="receipt_pdf"),
    # панель администратора
    path("manage/", views.staff_dashboard, name="staff_dashboard"),
    path("manage/orders/", views.staff_orders, name="staff_orders"),
    path("manage/orders/<int:pk>/", views.staff_order_detail, name="staff_order_detail"),
    path("manage/orders/<int:pk>/status/", views.staff_order_status, name="staff_order_status"),
    path("manage/orders/<int:pk>/delete/", views.staff_order_delete, name="staff_order_delete"),
    path("manage/products/", views.staff_products, name="staff_products"),
    path("manage/products/new/", views.product_form, name="product_create"),
    path("manage/products/<int:pk>/edit/", views.product_form, name="product_edit"),
    path("manage/products/<int:pk>/toggle/", views.product_toggle, name="product_toggle"),
    path("manage/categories/", views.staff_categories, name="staff_categories"),
    path("manage/categories/new/", views.category_form, name="category_create"),
    path("manage/categories/<int:pk>/edit/", views.category_form, name="category_edit"),
    path("manage/categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
    path("manage/stickers/", views.staff_stickers, name="staff_stickers"),
    path("manage/stickers/new/", views.sticker_form, name="sticker_create"),
    path("manage/stickers/<int:pk>/edit/", views.sticker_form, name="sticker_edit"),
    path("manage/stickers/<int:pk>/toggle/", views.sticker_toggle, name="sticker_toggle"),
    path("manage/posts/", views.staff_posts, name="staff_posts"),
    path("manage/posts/new/", views.post_form, name="post_create"),
    path("manage/posts/<int:pk>/edit/", views.post_form, name="post_edit"),
    path("manage/posts/<int:pk>/toggle/", views.post_toggle, name="post_toggle"),
    path("manage/users/", views.staff_users, name="staff_users"),
    path("manage/users/<int:pk>/toggle/", views.user_toggle, name="user_toggle"),
    path("manage/stats/", views.staff_stats, name="staff_stats"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Кофейня «Зерно»"
admin.site.site_title = "Зерно"
admin.site.index_title = "Служебное администрирование"
