import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BlogPost, Category, Order, OrderItem, OrderSticker, Product, Sticker, User
from .services import (
    CartError,
    cart_summary,
    change_order_status,
    create_order,
    get_design,
)


class BaseData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username="admin", password="admin12345", role=User.ROLE_ADMIN, is_staff=True
        )
        cls.client_user = User.objects.create_user(
            username="client", password="client12345", first_name="Мария"
        )
        cls.other_user = User.objects.create_user(username="other", password="other12345")
        cls.coffee = Category.objects.create(name="Кофе", slug="coffee", icon="☕")
        cls.desserts = Category.objects.create(name="Десерты", slug="desserts", icon="🍰")
        cls.latte = Product.objects.create(
            category=cls.coffee, name="Латте", slug="latte", price=Decimal("310"),
            description="Мягкий кофе", volume="400 мл",
        )
        cls.espresso = Product.objects.create(
            category=cls.coffee, name="Эспрессо", slug="espresso", price=Decimal("190"),
        )
        cls.cheesecake = Product.objects.create(
            category=cls.desserts, name="Чизкейк", slug="cheesecake", price=Decimal("320"),
        )
        cls.hidden = Product.objects.create(
            category=cls.coffee, name="Скрытый", slug="hidden", price=Decimal("100"), is_active=False,
        )
        cls.sticker = Sticker.objects.create(name="Листик", symbol="🌿")
        cls.post = BlogPost.objects.create(
            title="Как выбрать зерно", slug="beans", excerpt="Коротко о главном",
            body="Текст статьи", author=cls.admin,
        )
        cls.draft = BlogPost.objects.create(
            title="Черновик", slug="draft", excerpt="Ещё не готово", body="Текст",
            author=cls.admin, is_published=False,
        )

    def add(self, product, quantity=1):
        return self.client.post(reverse("cart_add", args=[product.pk]), {"quantity": quantity})

    def put_design(self, items):
        return self.client.post(
            reverse("stub_kit_save"),
            data=json.dumps({"stickers": items}),
            content_type="application/json",
        )

    def make_order(self, user=None, status=Order.STATUS_COMPLETED, sticker=False):
        order = Order.objects.create(
            client=user or self.client_user,
            status=status,
            total=Decimal("310"),
            items_count=1,
            completed_at=timezone.now() if status == Order.STATUS_COMPLETED else None,
        )
        OrderItem.objects.create(
            order=order, product=self.latte, name=self.latte.name,
            price=self.latte.price, quantity=1,
        )
        if sticker:
            OrderSticker.objects.create(order=order, sticker=self.sticker, x=40, y=50)
        return order


class PublicPagesTests(BaseData):
    def test_home_page(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Латте")

    def test_menu_lists_only_active_products(self):
        response = self.client.get(reverse("menu"))
        self.assertContains(response, "Латте")
        self.assertNotContains(response, "Скрытый")

    def test_menu_filters_by_category(self):
        response = self.client.get(reverse("menu"), {"category": "desserts"})
        self.assertContains(response, "Чизкейк")
        self.assertNotContains(response, "Латте")

    def test_menu_search(self):
        response = self.client.get(reverse("menu"), {"q": "Чиз"})
        self.assertContains(response, "Чизкейк")
        self.assertNotContains(response, "Эспрессо")

    def test_product_detail_and_hidden_product(self):
        self.assertEqual(self.client.get(reverse("product_detail", args=["latte"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("product_detail", args=["hidden"])).status_code, 404)

    def test_blog_pages(self):
        self.assertEqual(self.client.get(reverse("blog")).status_code, 200)
        self.assertEqual(self.client.get(reverse("blog_detail", args=["beans"])).status_code, 200)
        self.assertEqual(self.client.get(reverse("blog_detail", args=["draft"])).status_code, 404)

    def test_public_order_status_by_token(self):
        order = self.make_order(sticker=True)
        response = self.client.get(reverse("order_public", args=[order.public_token]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.number)

    def test_public_order_hides_client_data(self):
        order = self.make_order()
        response = self.client.get(reverse("order_public", args=[order.public_token]))
        self.assertNotContains(response, "client12345")
        self.assertEqual(self.client.get(reverse("order_public", args=["00000000-0000-0000-0000-000000000000"])).status_code, 404)


class CartTests(BaseData):
    def test_add_to_cart(self):
        self.client.post(reverse("cart_add", args=[self.latte.pk]), {"quantity": 2})
        summary = cart_summary(self.client.session)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["total"], Decimal("620"))
        self.assertEqual(self.client.get(reverse("cart")).status_code, 200)

    def test_add_hidden_product_is_rejected(self):
        self.client.post(reverse("cart_add", args=[self.hidden.pk]))
        self.assertEqual(cart_summary(self.client.session)["count"], 0)

    def test_quantity_limited_and_removable(self):
        self.add(self.latte, 50)
        self.assertEqual(cart_summary(self.client.session)["count"], 20)
        self.client.post(reverse("cart_update", args=[self.latte.pk]), {"quantity": 0})
        self.assertEqual(cart_summary(self.client.session)["count"], 0)

    def test_cart_requires_post_for_mutation(self):
        self.assertEqual(self.client.get(reverse("cart_add", args=[self.latte.pk])).status_code, 405)


class CheckoutTests(BaseData):
    def test_checkout_requires_login(self):
        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_empty_cart_redirects(self):
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("checkout"))
        self.assertRedirects(response, reverse("menu"))

    def test_order_snapshots_prices_and_clears_cart(self):
        self.client.force_login(self.client_user)
        self.add(self.latte, 2)

        response = self.client.post(reverse("checkout"), {"comment": "Без сахара"})
        order = Order.objects.get(client=self.client_user)
        self.assertRedirects(response, reverse("order_detail", args=[order.pk]))
        self.assertEqual(order.total, Decimal("620"))
        self.assertEqual(order.items_count, 2)
        self.assertEqual(cart_summary(self.client.session)["count"], 0)

        # Позиция хранит цену на момент оформления, а не текущую цену товара.
        self.latte.price = Decimal("500")
        self.latte.save(update_fields=["price"])
        item = order.items.first()
        item.refresh_from_db()
        self.assertEqual(item.price, Decimal("310"))
        order.refresh_from_db()
        self.assertEqual(order.total, Decimal("620"))

    def test_order_keeps_sticker_design(self):
        self.client.force_login(self.client_user)
        self.add(self.latte)
        self.put_design([{"sticker": self.sticker.pk, "x": 30, "y": 40, "scale": 1.2, "rotation": 15}])
        self.client.post(reverse("checkout"), {})
        order = Order.objects.get(client=self.client_user)
        placed = order.stickers.get()
        self.assertEqual(placed.sticker, self.sticker)
        self.assertEqual(placed.x, 30)
        self.assertEqual(get_design(self.client.session), [])

    def test_pickup_time_in_past_is_rejected(self):
        self.client.force_login(self.client_user)
        self.add(self.latte)
        past = (timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("checkout"), {"pickup_time": past})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_create_order_with_empty_cart_raises(self):
        with self.assertRaises(CartError):
            create_order(self.client.session, self.client_user)


class OrderAccessTests(BaseData):
    def test_order_detail_visible_only_to_owner_and_admin(self):
        order = self.make_order()
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 200)

        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("receipt_pdf", args=[order.pk])).status_code, 403)

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("order_detail", args=[order.pk])).status_code, 200)

    def test_receipt_pdf_for_owner(self):
        order = self.make_order()
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("receipt_pdf", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_my_orders_lists_only_own_orders(self):
        own = self.make_order()
        foreign = self.make_order(user=self.other_user)
        self.client.force_login(self.client_user)
        response = self.client.get(reverse("my_orders"))
        self.assertContains(response, own.number)
        self.assertNotContains(response, foreign.number)


class StickerStudioTests(BaseData):
    def test_save_design_sanitizes_input(self):
        self.put_design(
            [
                {"sticker": self.sticker.pk, "x": 999, "y": -20, "scale": 9, "rotation": 900},
                {"sticker": 99999, "x": 10, "y": 10},
                {"sticker": "мусор"},
            ]
        )
        design = self.client.get(reverse("stub_kit")).context["design"]
        self.assertEqual(len(design), 1)
        self.assertEqual(design[0]["x"], 100)
        self.assertEqual(design[0]["y"], 0)
        self.assertEqual(design[0]["scale"], 2.5)
        self.assertEqual(design[0]["rotation"], 180)

    def test_design_limited_to_twelve_stickers(self):
        self.put_design([{"sticker": self.sticker.pk} for _ in range(20)])
        design = self.client.get(reverse("stub_kit")).context["design"]
        self.assertEqual(len(design), 12)

    def test_save_and_clear_endpoints(self):
        payload = {"stickers": [{"sticker": self.sticker.pk, "x": 20, "y": 30}]}
        response = self.client.post(
            reverse("stub_kit_save"), data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "saved": 1})
        self.assertEqual(self.client.get(reverse("stub_kit")).status_code, 200)

        self.assertEqual(self.client.get(reverse("stub_kit_save")).status_code, 405)
        self.client.post(reverse("stub_kit_clear"))
        design = self.client.get(reverse("stub_kit")).context["design"]
        self.assertEqual(design, [])

    def test_save_rejects_broken_json(self):
        response = self.client.post(
            reverse("stub_kit_save"), data="{не json", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])


class AuthTests(BaseData):
    def test_register_creates_client_and_logs_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "newbie", "first_name": "Пётр", "last_name": "Иванов",
                "email": "new@zerno.local", "phone": "+79990000000",
                "password1": "Str0ngPass!42", "password2": "Str0ngPass!42",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newbie")
        self.assertEqual(user.role, User.ROLE_CLIENT)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_register_rejects_duplicate_email(self):
        User.objects.create_user(username="mailer", password="x", email="dup@zerno.local")
        response = self.client.post(
            reverse("register"),
            {
                "username": "newbie2", "email": "DUP@zerno.local",
                "password1": "Str0ngPass!42", "password2": "Str0ngPass!42",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "уже зарегистрирован")

    def test_admin_login_lands_on_dashboard(self):
        response = self.client.post(
            reverse("login"), {"username": "admin", "password": "admin12345"}
        )
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("staff_dashboard"))

    def test_blocked_user_cannot_login(self):
        self.client_user.is_active = False
        self.client_user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("login"), {"username": "client", "password": "client12345"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)


class StaffAccessTests(BaseData):
    def test_client_cannot_open_staff_pages(self):
        self.client.force_login(self.client_user)
        for name in ("staff_dashboard", "staff_orders", "staff_products", "staff_stats", "staff_users"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_anonymous_redirected_from_staff(self):
        response = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_admin_opens_all_staff_pages(self):
        self.make_order(sticker=True)
        self.client.force_login(self.admin)
        names = [
            "staff_dashboard", "staff_orders", "staff_products", "staff_categories",
            "staff_stickers", "staff_posts", "staff_users", "staff_stats",
            "product_create", "category_create", "sticker_create", "post_create",
        ]
        for name in names:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class StaffOrderTests(BaseData):
    def test_status_change_sets_completed_at(self):
        order = self.make_order(status=Order.STATUS_READY)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("staff_order_status", args=[order.pk]),
            {"status": Order.STATUS_COMPLETED, "comment": "Заказ выдан"},
        )
        self.assertRedirects(response, reverse("staff_order_detail", args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.completed_at)
        self.assertEqual(order.staff_comment, "Заказ выдан")

    def test_invalid_status_is_ignored_by_service(self):
        order = self.make_order()
        with self.assertRaises(ValueError):
            change_order_status(order, "teleported")

    def test_delete_only_cancelled_order(self):
        active = self.make_order(status=Order.STATUS_NEW)
        cancelled = self.make_order(status=Order.STATUS_CANCELLED)
        self.client.force_login(self.admin)

        response = self.client.post(reverse("staff_order_delete", args=[active.pk]))
        self.assertRedirects(response, reverse("staff_order_detail", args=[active.pk]))
        self.assertTrue(Order.objects.filter(pk=active.pk).exists())

        response = self.client.post(reverse("staff_order_delete", args=[cancelled.pk]))
        self.assertRedirects(response, reverse("staff_orders"))
        self.assertFalse(Order.objects.filter(pk=cancelled.pk).exists())

    def test_orders_search_by_number_and_filters(self):
        order = self.make_order()
        self.make_order(status=Order.STATUS_NEW)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("staff_orders"), {"q": order.number.lower()})
        self.assertContains(response, order.number)
        response = self.client.get(reverse("staff_orders"), {"status": Order.STATUS_NEW})
        self.assertEqual(response.context["page"].paginator.count, 1)


class StaffCatalogTests(BaseData):
    def test_product_create_and_toggle(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("product_create"),
            {
                "category": self.coffee.pk, "name": "Флэт уайт", "slug": "",
                "description": "Меньше молока", "composition": "Эспрессо, молоко",
                "price": "320", "volume": "250 мл", "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("staff_products"))
        product = Product.objects.get(name="Флэт уайт")
        self.assertEqual(product.slug, "flet-uajt")

        self.client.post(reverse("product_toggle", args=[product.pk]))
        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_product_price_must_be_positive(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("product_create"),
            {"category": self.coffee.pk, "name": "Ноль", "price": "0", "is_active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name="Ноль").exists())

    def test_category_and_sticker_crud(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("category_create"),
            {"name": "Чай", "slug": "tea", "icon": "🍵", "sort_order": 3, "is_active": "on"},
        )
        self.assertTrue(Category.objects.filter(slug="tea").exists())

        self.client.post(
            reverse("sticker_create"), {"name": "Звезда", "symbol": "⭐", "is_active": "on"}
        )
        self.assertTrue(Sticker.objects.filter(symbol="⭐").exists())

    def test_post_create_assigns_author(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("post_create"),
            {
                "title": "Новая статья", "slug": "",
                "excerpt": "Достаточно длинное краткое описание",
                "body": "Текст", "is_published": "on",
            },
        )
        self.assertRedirects(response, reverse("staff_posts"))
        post = BlogPost.objects.get(title="Новая статья")
        self.assertEqual(post.author, self.admin)


class StaffUserTests(BaseData):
    def test_block_and_unblock_user(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle", args=[self.other_user.pk]))
        self.other_user.refresh_from_db()
        self.assertFalse(self.other_user.is_active)

        self.client.post(reverse("user_toggle", args=[self.other_user.pk]))
        self.other_user.refresh_from_db()
        self.assertTrue(self.other_user.is_active)

    def test_cannot_block_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse("user_toggle", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_user_search(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff_users"), {"role": User.ROLE_CLIENT, "q": "Мария"})
        self.assertContains(response, "client")


class StatsTests(BaseData):
    def test_stats_page_has_chart_data(self):
        for _ in range(3):
            self.make_order()
        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff_stats"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["labels"]), 14)
        self.assertEqual(len(response.context["revenue"]), 14)
        self.assertEqual(sum(response.context["orders_count"]), 3)
        self.assertEqual(response.context["total_orders"], 3)
        self.assertEqual(response.context["completed_count"], 3)
        self.assertEqual(len(response.context["status_rows"]), len(Order.STATUS_CHOICES))
        self.assertContains(response, "revenueChart")

    def test_cancelled_orders_excluded_from_revenue(self):
        self.make_order()
        self.make_order(status=Order.STATUS_CANCELLED)
        self.client.force_login(self.admin)
        response = self.client.get(reverse("staff_stats"))
        self.assertEqual(response.context["total_revenue"], Decimal("310"))
