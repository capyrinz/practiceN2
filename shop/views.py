import json
import re
from datetime import datetime, timedelta
from io import BytesIO

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    CategoryForm,
    CheckoutForm,
    LoginForm,
    OrderStatusForm,
    PostForm,
    ProductForm,
    RegisterForm,
    StickerForm,
)
from .models import BlogPost, Category, Order, OrderItem, Product, Sticker, User
from .pdf import build_receipt_pdf
from .services import (
    CartError,
    add_to_cart,
    cart_summary,
    change_order_status,
    clear_design,
    create_order,
    design_preview,
    remove_from_cart,
    save_design,
    set_quantity,
)

MONTHS = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
ACTIVE_STATUSES = [Order.STATUS_NEW, Order.STATUS_PREPARING, Order.STATUS_READY]


# ---------------------------------------------------------------- публичная витрина


def home(request):
    products = Product.objects.filter(is_active=True, is_featured=True).select_related(
        "category"
    )[:6]
    if not products:
        products = Product.objects.filter(is_active=True).select_related("category")[:6]
    return render(
        request,
        "public/home.html",
        {
            "products": products,
            "categories": Category.objects.filter(is_active=True),
            "posts": BlogPost.objects.filter(is_published=True)[:3],
            "products_total": Product.objects.filter(is_active=True).count(),
        },
    )


def menu(request):
    products = Product.objects.filter(is_active=True, category__is_active=True).select_related(
        "category"
    )
    categories = Category.objects.filter(is_active=True)
    active_slug = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()

    if active_slug:
        products = products.filter(category__slug=active_slug)
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(composition__icontains=query)
        )

    category_counts = dict(
        Product.objects.filter(is_active=True)
        .values_list("category__slug")
        .annotate(total=Count("id"))
    )
    return render(
        request,
        "public/menu.html",
        {
            "products": products,
            "categories": categories,
            "active_slug": active_slug,
            "query": query,
            "category_counts": category_counts,
            "products_total": Product.objects.filter(is_active=True).count(),
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category"), slug=slug, is_active=True
    )
    related = (
        Product.objects.filter(is_active=True, category=product.category)
        .exclude(pk=product.pk)
        .select_related("category")[:3]
    )
    return render(
        request,
        "public/product_detail.html",
        {"product": product, "related": related},
    )


def blog(request):
    posts = BlogPost.objects.filter(is_published=True).select_related("author")
    return render(request, "public/blog.html", {"posts": posts})


def blog_detail(request, slug):
    post = get_object_or_404(
        BlogPost.objects.select_related("author"), slug=slug, is_published=True
    )
    others = BlogPost.objects.filter(is_published=True).exclude(pk=post.pk)[:3]
    return render(request, "public/blog_detail.html", {"post": post, "others": others})


def order_public(request, token):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "stickers__sticker"), public_token=token
    )
    return render(request, "public/order_status.html", {"order": order})


# ---------------------------------------------------------------- авторизация


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.role = User.ROLE_CLIENT
        user.email = form.cleaned_data["email"]
        user.save()
        login(request, user)
        messages.success(request, "Аккаунт создан. Приятного кофе!")
        return redirect("menu")
    return render(request, "auth/register.html", {"form": form})


class AppLoginView(LoginView):
    template_name = "auth/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


@login_required
def dashboard(request):
    if request.user.is_admin:
        return redirect("staff_dashboard")
    return redirect("my_orders")


# ---------------------------------------------------------------- корзина


def cart(request):
    summary = cart_summary(request.session)
    return render(
        request,
        "client/cart.html",
        {
            "items": summary["items"],
            "count": summary["count"],
            "total": summary["total"],
            "design": design_preview(request.session),
        },
    )


@require_POST
def cart_add(request, product_id):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    try:
        add_to_cart(request.session, product_id, max(1, quantity))
    except CartError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, "Добавлено в корзину.")
    return redirect(request.POST.get("next") or "cart")


@require_POST
def cart_update(request, product_id):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    set_quantity(request.session, product_id, quantity)
    return redirect("cart")


@require_POST
def cart_remove(request, product_id):
    remove_from_cart(request.session, product_id)
    messages.success(request, "Товар удалён из корзины.")
    return redirect("cart")


# ---------------------------------------------------------------- стикер-студия


def stub_kit(request):
    stickers = Sticker.objects.filter(is_active=True)
    stickers_json = [
        {"id": s.pk, "symbol": s.symbol, "name": s.name} for s in stickers
    ]
    return render(
        request,
        "client/stub_kit.html",
        {
            "stickers": stickers,
            "design": design_preview(request.session),
            "stickers_json": json.dumps(stickers_json, ensure_ascii=False),
        },
    )


@require_POST
def stub_kit_save(request):
    try:
        payload = json.loads(request.body or "[]")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Некорректный формат данных."}, status=400)
    if isinstance(payload, dict):
        payload = payload.get("stickers", [])
    if not isinstance(payload, list):
        return JsonResponse({"ok": False, "error": "Ожидался список стикеров."}, status=400)
    design = save_design(request.session, payload)
    return JsonResponse({"ok": True, "saved": len(design)})


@require_POST
def stub_kit_clear(request):
    clear_design(request.session)
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------- заказы клиента


@role_required(User.ROLE_CLIENT)
def checkout(request):
    summary = cart_summary(request.session)
    if not summary["items"]:
        messages.info(request, "Корзина пуста — добавьте напиток или десерт.")
        return redirect("menu")

    form = CheckoutForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            order = create_order(
                request.session,
                request.user,
                form.cleaned_data["comment"],
                form.cleaned_data["pickup_time"],
            )
        except CartError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Заказ {order.number} принят. Спасибо!")
            return redirect("order_detail", pk=order.pk)

    return render(
        request,
        "client/checkout.html",
        {
            "form": form,
            "items": summary["items"],
            "total": summary["total"],
            "count": summary["count"],
            "design": design_preview(request.session),
        },
    )


@role_required(User.ROLE_CLIENT)
def my_orders(request):
    orders = Order.objects.filter(client=request.user).prefetch_related("items")
    active = orders.filter(status__in=ACTIVE_STATUSES).count()
    return render(
        request,
        "client/my_orders.html",
        {"orders": orders, "active_count": active, "total_count": orders.count()},
    )


def _can_view_order(user, order):
    return user.is_admin or order.client_id == user.pk


def _get_visible_order(user, pk):
    order = get_object_or_404(
        Order.objects.select_related("client").prefetch_related("items", "stickers__sticker"),
        pk=pk,
    )
    if not _can_view_order(user, order):
        raise PermissionDenied("Это заказ другого клиента.")
    return order


@login_required
def order_detail(request, pk):
    order = _get_visible_order(request.user, pk)
    return render(
        request,
        "client/order_detail.html",
        {
            "order": order,
            "is_admin": request.user.is_admin,
            "statuses": Order.STATUS_CHOICES,
        },
    )


@login_required
def receipt_pdf(request, pk):
    order = _get_visible_order(request.user, pk)
    content = build_receipt_pdf(order)
    return FileResponse(
        BytesIO(content),
        content_type="application/pdf",
        as_attachment=True,
        filename=f"check_{order.number}.pdf",
    )


# ---------------------------------------------------------------- панель администратора


@role_required(User.ROLE_ADMIN)
def staff_dashboard(request):
    orders = Order.objects.all()
    today = timezone.localdate()
    today_orders = orders.filter(created_at__date=today)
    sold = orders.filter(status__in=Order.SOLD_STATUSES)
    month_start = timezone.now() - timedelta(days=30)
    context = {
        "orders_total": orders.count(),
        "orders_today": today_orders.count(),
        "active_count": orders.filter(status__in=ACTIVE_STATUSES).count(),
        "ready_count": orders.filter(status=Order.STATUS_READY).count(),
        "revenue_total": sold.aggregate(total=Sum("total"))["total"] or 0,
        "revenue_month": sold.filter(created_at__gte=month_start).aggregate(
            total=Sum("total")
        )["total"] or 0,
        "clients_count": User.objects.filter(role=User.ROLE_CLIENT).count(),
        "avg_check": sold.aggregate(value=Avg("total"))["value"] or 0,
        "latest": orders.select_related("client")[:8],
        "top_products": OrderItem.objects.filter(order__status__in=Order.SOLD_STATUSES)
        .values("name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")[:5],
    }
    return render(request, "staff/dashboard.html", context)


@role_required(User.ROLE_ADMIN)
def staff_orders(request):
    orders = Order.objects.select_related("client").prefetch_related("items")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    date_from = request.GET.get("from", "")
    date_to = request.GET.get("to", "")

    if status:
        orders = orders.filter(status=status)
    if query:
        filters = (
            Q(client__username__icontains=query)
            | Q(client__last_name__icontains=query)
            | Q(client__first_name__icontains=query)
            | Q(comment__icontains=query)
        )
        if query.isdigit():
            filters |= Q(pk=int(query))
        else:
            match = re.fullmatch(r"[кk]\s*-?\s*(\d+)", query.lower())
            if match:
                filters |= Q(pk=int(match.group(1)))
        orders = orders.filter(filters)
    if date_from:
        orders = orders.filter(created_at__date__gte=date_from)
    if date_to:
        orders = orders.filter(created_at__date__lte=date_to)

    paginator = Paginator(orders, 20)
    page = paginator.get_page(request.GET.get("page"))
    counts = {
        row["status"]: row["total"]
        for row in Order.objects.values("status").annotate(total=Count("id"))
    }
    return render(
        request,
        "staff/orders.html",
        {
            "page": page,
            "orders": page.object_list,
            "statuses": Order.STATUS_CHOICES,
            "status_filter": status,
            "query": query,
            "date_from": date_from,
            "date_to": date_to,
            "counts": counts,
            "total_count": Order.objects.count(),
        },
    )


def _get_order_for_staff(pk):
    return get_object_or_404(
        Order.objects.select_related("client").prefetch_related("items", "stickers__sticker"),
        pk=pk,
    )


@role_required(User.ROLE_ADMIN)
def staff_order_detail(request, pk):
    order = _get_order_for_staff(pk)
    return render(
        request,
        "staff/order_detail.html",
        {
            "order": order,
            "status_form": OrderStatusForm(initial={"status": order.status}),
            "statuses": Order.STATUS_CHOICES,
        },
    )


@role_required(User.ROLE_ADMIN)
@require_POST
def staff_order_status(request, pk):
    order = _get_order_for_staff(pk)
    form = OrderStatusForm(request.POST)
    if form.is_valid():
        changed = change_order_status(
            order, form.cleaned_data["status"], form.cleaned_data["comment"]
        )
        messages.success(request, "Статус обновлён." if changed else "Статус не изменился.")
    else:
        messages.error(request, "Не удалось изменить статус: проверьте значение.")
    return redirect("staff_order_detail", pk=pk)


@role_required(User.ROLE_ADMIN)
@require_POST
def staff_order_delete(request, pk):
    order = _get_order_for_staff(pk)
    number = order.number
    if order.status != Order.STATUS_CANCELLED:
        messages.error(request, "Удалить можно только отменённый заказ.")
        return redirect("staff_order_detail", pk=pk)
    with transaction.atomic():
        if order.items.exists():
            messages.info(request, "Позиции заказа удалены вместе с заказом.")
        order.delete()
    messages.success(request, f"Заказ {number} удалён.")
    return redirect("staff_orders")


# ---------------------------------------------------------------- товары


@role_required(User.ROLE_ADMIN)
def staff_products(request):
    products = Product.objects.select_related("category")
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    if category_id:
        products = products.filter(category_id=category_id)
    return render(
        request,
        "staff/products.html",
        {
            "products": products,
            "categories": Category.objects.all(),
            "query": query,
            "category_filter": category_id,
            "active_count": Product.objects.filter(is_active=True).count(),
        },
    )


@role_required(User.ROLE_ADMIN)
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Товар сохранён.")
        return redirect("staff_products")
    return render(
        request,
        "staff/product_form.html",
        {"form": form, "product": product},
    )


@role_required(User.ROLE_ADMIN)
@require_POST
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_active = not product.is_active
    product.save(update_fields=["is_active"])
    messages.success(request, "Видимость товара изменена.")
    return redirect("staff_products")


# ---------------------------------------------------------------- категории


@role_required(User.ROLE_ADMIN)
def staff_categories(request):
    categories = Category.objects.annotate(products_count=Count("products"))
    return render(request, "staff/categories.html", {"categories": categories})


@role_required(User.ROLE_ADMIN)
def category_form(request, pk=None):
    category = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Категория сохранена.")
        return redirect("staff_categories")
    return render(
        request,
        "staff/category_form.html",
        {"form": form, "category": category},
    )


@role_required(User.ROLE_ADMIN)
@require_POST
def category_toggle(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    messages.success(request, "Статус категории изменён.")
    return redirect("staff_categories")


# ---------------------------------------------------------------- стикеры


@role_required(User.ROLE_ADMIN)
def staff_stickers(request):
    stickers = Sticker.objects.annotate(usages_count=Count("usages"))
    return render(request, "staff/stickers.html", {"stickers": stickers})


@role_required(User.ROLE_ADMIN)
def sticker_form(request, pk=None):
    sticker = get_object_or_404(Sticker, pk=pk) if pk else None
    form = StickerForm(request.POST or None, instance=sticker)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Стикер сохранён.")
        return redirect("staff_stickers")
    return render(
        request,
        "staff/sticker_form.html",
        {"form": form, "sticker": sticker},
    )


@role_required(User.ROLE_ADMIN)
@require_POST
def sticker_toggle(request, pk):
    sticker = get_object_or_404(Sticker, pk=pk)
    sticker.is_active = not sticker.is_active
    sticker.save(update_fields=["is_active"])
    messages.success(request, "Доступность стикера изменена.")
    return redirect("staff_stickers")


# ---------------------------------------------------------------- блог


@role_required(User.ROLE_ADMIN)
def staff_posts(request):
    posts = BlogPost.objects.select_related("author")
    return render(request, "staff/posts.html", {"posts": posts})


@role_required(User.ROLE_ADMIN)
def post_form(request, pk=None):
    post = get_object_or_404(BlogPost, pk=pk) if pk else None
    form = PostForm(request.POST or None, request.FILES or None, instance=post)
    if request.method == "POST" and form.is_valid():
        article = form.save(commit=False)
        if not article.author:
            article.author = request.user
        article.save()
        messages.success(request, "Статья сохранена.")
        return redirect("staff_posts")
    return render(request, "staff/post_form.html", {"form": form, "post": post})


@role_required(User.ROLE_ADMIN)
@require_POST
def post_toggle(request, pk):
    post = get_object_or_404(BlogPost, pk=pk)
    post.is_published = not post.is_published
    post.save(update_fields=["is_published"])
    messages.success(request, "Публикация статьи изменена.")
    return redirect("staff_posts")


# ---------------------------------------------------------------- пользователи


@role_required(User.ROLE_ADMIN)
def staff_users(request):
    role = request.GET.get("role", User.ROLE_CLIENT)
    query = request.GET.get("q", "").strip()
    users = User.objects.filter(role=role).annotate(orders_count=Count("orders"))
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    return render(
        request,
        "staff/users.html",
        {
            "users": users,
            "role": role,
            "roles": User.ROLE_CHOICES,
            "query": query,
        },
    )


@role_required(User.ROLE_ADMIN)
@require_POST
def user_toggle(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "Нельзя заблокировать собственную учётную запись.")
        return redirect("staff_users")
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, "Доступ пользователя изменён.")
    return redirect(request.POST.get("next") or "staff_users")


# ---------------------------------------------------------------- статистика


@role_required(User.ROLE_ADMIN)
def staff_stats(request):
    today = timezone.localdate()
    start_day = today - timedelta(days=13)
    start = timezone.make_aware(datetime(start_day.year, start_day.month, start_day.day))
    orders = list(
        Order.objects.filter(created_at__gte=start, status__in=Order.SOLD_STATUSES)
        .prefetch_related("items")
    )

    labels, revenue, orders_count = [], [], []
    for offset in range(14):
        day = start_day + timedelta(days=offset)
        labels.append(f"{day.day:02d}.{day.month:02d}")
        day_orders = [o for o in orders if timezone.localtime(o.created_at).date() == day]
        revenue.append(float(sum((o.total for o in day_orders), start=0)))
        orders_count.append(len(day_orders))

    sold_items = OrderItem.objects.filter(order__status__in=Order.SOLD_STATUSES)
    top_products = list(
        sold_items.values("name")
        .annotate(qty=Sum("quantity"), revenue=Sum(F("price") * F("quantity")))
        .order_by("-qty")[:6]
    )
    category_shares = list(
        sold_items.filter(product__isnull=False)
        .values("product__category__name")
        .annotate(quantity=Sum("quantity"))
        .order_by("-quantity")
    )
    status_rows = [
        {
            "status": value,
            "label": label,
            "count": Order.objects.filter(status=value).count(),
        }
        for value, label in Order.STATUS_CHOICES
    ]
    sold = Order.objects.filter(status__in=Order.SOLD_STATUSES)
    month_start = timezone.now() - timedelta(days=30)
    total_revenue = sold.aggregate(total=Sum("total"))["total"] or 0

    context = {
        "labels": labels,
        "revenue": revenue,
        "orders_count": orders_count,
        "top_products": top_products,
        "category_labels": [row["product__category__name"] for row in category_shares],
        "category_values": [row["quantity"] for row in category_shares],
        "status_rows": status_rows,
        "total_orders": Order.objects.count(),
        "total_revenue": total_revenue,
        "month_revenue": sold.filter(created_at__gte=month_start).aggregate(
            total=Sum("total")
        )["total"] or 0,
        "avg_check": sold.aggregate(value=Avg("total"))["value"] or 0,
        "clients_count": User.objects.filter(role=User.ROLE_CLIENT).count(),
        "completed_count": Order.objects.filter(status=Order.STATUS_COMPLETED).count(),
        "cancel_rate": (
            round(
                Order.objects.filter(status=Order.STATUS_CANCELLED).count()
                / Order.objects.count()
                * 100,
                1,
            )
            if Order.objects.exists()
            else 0
        ),
        "best_day": max(zip(labels, revenue), key=lambda pair: pair[1]) if labels else None,
    }
    return render(request, "staff/stats.html", context)
