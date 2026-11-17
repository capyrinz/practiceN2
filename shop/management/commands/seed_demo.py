"""Демо-данные кофейни «Зерно»: пользователи, меню, стикеры, блог и заказы.

Запуск: python manage.py seed_demo
Команда идемпотентна: повторный запуск не создаёт дубликаты.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from shop.models import (
    BlogPost,
    Category,
    Order,
    OrderItem,
    OrderSticker,
    Product,
    Sticker,
    User,
)
from shop.services import change_order_status

CATEGORIES = [
    ("Кофе", "coffee", "Эспрессо, капучино, латте и другие классические напитки", "☕", 1),
    ("Авторские напитки", "signature", "Сезонные сочетания от бариста", "🥤", 2),
    ("Чай", "tea", "Ягодные и травяные сборы", "🍵", 3),
    ("Десерты", "desserts", "Свежая выпечка к кофе", "🍰", 4),
    ("Зерно", "beans", "Обжарка на вынос, 250 г", "🌱", 5),
]

PRODUCTS = [
    ("coffee", "Эспрессо", 190, "40 мл", "Плотный шот на зерне собственной обжарки", "Арабика Бразилия, 100%", True),
    ("coffee", "Американо", 230, "300 мл", "Эспрессо с горячей водой, чистый вкус", "Арабика Бразилия, вода", True),
    ("coffee", "Капучино", 290, "350 мл", "Классика с плотной молочной пеной", "Эспрессо, молоко 3,2%", True),
    ("coffee", "Латте", 310, "400 мл", "Мягкий напиток с тонким слоем пены", "Эспрессо, молоко 3,2%", True),
    ("coffee", "Флэт уайт", 320, "250 мл", "Больше кофе, меньше молока", "Двойной эспрессо, молоко", False),
    ("coffee", "Раф", 340, "350 мл", "Сливки, ваниль и щепотка соли", "Эспрессо, сливки, ванильный сахар", False),
    ("signature", "Лавандовый раф", 380, "350 мл", "Цветочный сироп и мягкие сливки", "Эспрессо, сливки, лавандовый сироп", True),
    ("signature", "Айс-латте с солёной карамелью", 390, "400 мл", "Холодный кофе с карамельным соусом", "Эспрессо, молоко, карамель, лёд", True),
    ("signature", "Эспрессо-тоник", 350, "300 мл", "Бодрящий микс кофе и тоника", "Эспрессо, тоник, лёд, апельсин", False),
    ("signature", "Матча-латте", 370, "350 мл", "Церемониальная матча на молоке", "Матча, молоко, сироп агавы", False),
    ("tea", "Облепиховый чай", 280, "400 мл", "Ягодный чай с апельсином и мёдом", "Облепиха, апельсин, мёд, чёрный чай", True),
    ("tea", "Чай с чабрецом", 250, "400 мл", "Травяной сбор с лимоном", "Чабрец, мелисса, лимон", False),
    ("desserts", "Круассан", 220, "85 г", "Слоёный, на французском масле", "Пшеничная мука, масло 82,5%", True),
    ("desserts", "Синнабон", 260, "120 г", "Булочка с корицей и сливочной глазурью", "Мука, корица, сливочный сыр", False),
    ("desserts", "Чизкейк", 320, "110 г", "Нью-Йорк на песочной основе", "Сливочный сыр, сливки, песочная основа", True),
    ("desserts", "Брауни", 280, "90 г", "Плотный шоколадный брауни", "Тёмный шоколад, масло, яйцо", False),
    ("beans", "Эфиопия Иргачефф", 890, "250 г", "Цветочный лот с нотками бергамота", "100% арабика, обжарка под фильтр", True),
    ("beans", "Колумбия Уила", 790, "250 г", "Карамель и красные ягоды, обжарка под эспрессо", "100% арабика", False),
]

STICKERS = [
    ("Листик", "🌿"),
    ("Звезда", "⭐"),
    ("Улыбка", "😊"),
    ("Мишка", "🐻"),
    ("Чашка", "☕"),
    ("Сердце", "❤"),
    ("Цветок", "🌸"),
    ("Наушники", "🎧"),
]

POSTS = [
    (
        "Как выбрать зерно для дома",
        "fresh-beans-guide",
        "Дата обжарки, степень помола и способ заваривания — коротко о том, что влияет на вкус.",
        "Свежесть решает больше, чем страна происхождения. Ищите на пачке дату обжарки, а не срок годности: "
        "оптимально использовать зерно в первые 3–6 недель.\n\n"
        "Для турки и эспрессо берите более тёмную обжарку, для воронки и аэропресса — светлую. "
        "Помол подбирайте под способ: чем быстрее вода контактирует с кофе, тем мельче должен быть помол.\n\n"
        "Храните зерно в закрытой банке, без солнца и рядом с холодильником не надо: перепады влажности "
        "портят аромат. Молоть лучше прямо перед завариванием.",
    ),
    (
        "Пять способов заварить кофе без машины",
        "five-brew-methods",
        "Воронка, френч-пресс, аэропресс, турка и колд брю — что выбрать новичку.",
        "Начните с воронки: она прощает ошибки и показывает вкус зерна. Нужны только фильтры, "
        "чайник и весы.\n\n"
        "Френч-пресс даёт плотное тело и хорош для тёмной обжарки. Аэропресс занимает меньше места "
        "и позволяет экспериментировать с давлением.\n\n"
        "Турка требует мелкого помола и внимания: снимите с огня, как только поднимется пена. "
        "Колд брю — самый ленивый вариант: залейте крупный помол холодной водой и оставьте на 12 часов.",
    ),
    (
        "Что происходит в кофейне утром",
        "morning-at-the-cafe",
        "Открытие, настройка помола и первые гости — небольшой репортаж из-за стойки.",
        "В 07:30 мы включаем обжарщик и проверяем помол на первом эспрессо. Если шот течёт быстрее "
        "25 секунд, меняем настройки мельницы.\n\n"
        "К 08:00 готовы круассаны, а на стойке появляется вода для гостей. Первые заказы — всегда "
        "капучино и американо, а к девяти подтягиваются любители флэт уайта.\n\n"
        "Утренняя смена заканчивается в 14:00: мы моем группу, взвешиваем остатки и передаём смену. "
        "Такой ритм помогает держать стабильный вкус каждый день.",
    ),
]


class Command(BaseCommand):
    help = "Заполняет базу демонстрационными данными кофейни «Зерно»."

    def handle(self, *args, **options):
        random.seed(2026)
        users = self._users()
        categories = self._categories()
        products = self._products(categories)
        stickers = self._stickers()
        self._posts(users["admin"])
        created = self._orders(users, products, stickers)

        self.stdout.write(self.style.SUCCESS("Демо-данные готовы."))
        self.stdout.write(
            f"  пользователей: {User.objects.count()}, товаров: {Product.objects.count()}, "
            f"стикеров: {Sticker.objects.count()}, статей: {BlogPost.objects.count()}, "
            f"заказов добавлено: {created} (всего {Order.objects.count()})."
        )
        self.stdout.write("  админ: admin / admin12345")
        self.stdout.write("  клиент: client / client12345")

    # ------------------------------------------------------------------ шаги

    def _users(self):
        result = {}
        admin, _ = User.objects.get_or_create(
            username="admin",
            defaults={
                "first_name": "Анна",
                "last_name": "Бариста",
                "email": "admin@zerno.local",
                "role": User.ROLE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "phone": "+7 (495) 000-00-07",
            },
        )
        admin.role = User.ROLE_ADMIN
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password("admin12345")
        admin.save()
        result["admin"] = admin

        clients = [
            ("client", "Мария", "Соколова", "client@zerno.local", "+7 (916) 111-22-33"),
            ("client2", "Илья", "Морозов", "ilya@zerno.local", "+7 (916) 222-33-44"),
            ("client3", "Дарья", "Ким", "daria@zerno.local", "+7 (916) 333-44-55"),
        ]
        for username, first, last, email, phone in clients:
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "phone": phone,
                    "role": User.ROLE_CLIENT,
                },
            )
            user.role = User.ROLE_CLIENT
            user.set_password("client12345")
            user.save()
            result[username] = user
        return result

    def _categories(self):
        categories = {}
        for name, slug, description, icon, order in CATEGORIES:
            category, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "description": description,
                    "icon": icon,
                    "sort_order": order,
                },
            )
            categories[slug] = category
        return categories

    def _products(self, categories):
        products = []
        counters = {}
        for category_slug, name, price, volume, description, composition, featured in PRODUCTS:
            counters[category_slug] = counters.get(category_slug, 0) + 1
            slug = f"{category_slug}-{counters[category_slug]}"
            product, _ = Product.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "category": categories[category_slug],
                    "price": Decimal(price),
                    "volume": volume,
                    "description": description,
                    "composition": composition,
                    "is_featured": featured,
                },
            )
            products.append(product)
        return products

    def _stickers(self):
        stickers = []
        for name, symbol in STICKERS:
            sticker, _ = Sticker.objects.get_or_create(name=name, defaults={"symbol": symbol})
            stickers.append(sticker)
        return stickers

    def _posts(self, author):
        for title, slug, excerpt, body in POSTS:
            BlogPost.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "excerpt": excerpt,
                    "body": body,
                    "author": author,
                },
            )

    def _orders(self, users, products, stickers):
        if Order.objects.exists():
            self.stdout.write("  заказы уже есть — пропускаем генерацию.")
            return 0

        clients = [users["client"], users["client2"], users["client3"]]
        now = timezone.now()
        comments = [
            "Без сахара, пожалуйста",
            "Овсяное молоко, если можно",
            "Не очень горячий",
            "",
            "С собой, крышку не нужно",
        ]
        staff_notes = ["Заказ готов, можно забирать", "", "Готовим, осталось пару минут"]
        statuses = (
            [Order.STATUS_COMPLETED] * 12
            + [Order.STATUS_CANCELLED] * 2
            + [Order.STATUS_READY] * 2
            + [Order.STATUS_PREPARING] * 2
            + [Order.STATUS_NEW] * 2
        )
        random.shuffle(statuses)

        created_count = 0
        for index, status in enumerate(statuses):
            days_ago = 60 - index * 3
            created_at = now - timedelta(days=days_ago, hours=random.randint(0, 7), minutes=random.randint(0, 59))
            client = clients[index % len(clients)]
            chosen = random.sample(products, k=random.randint(1, 3))
            quantities = [random.randint(1, 2) for _ in chosen]
            total = sum((product.price * quantity for product, quantity in zip(chosen, quantities)), start=Decimal("0"))

            order = Order.objects.create(
                client=client,
                status=Order.STATUS_NEW,
                comment=random.choice(comments),
                total=total,
                items_count=sum(quantities),
                pickup_time=created_at + timedelta(minutes=20),
            )
            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        product=product,
                        name=product.name,
                        price=product.price,
                        quantity=quantity,
                    )
                    for product, quantity in zip(chosen, quantities)
                ]
            )

            design = random.sample(stickers, k=random.randint(0, 3))
            OrderSticker.objects.bulk_create(
                [
                    OrderSticker(
                        order=order,
                        sticker=sticker,
                        x=random.randint(25, 75),
                        y=random.randint(25, 80),
                        scale=round(random.uniform(0.8, 1.4), 2),
                        rotation=random.randint(-25, 25),
                    )
                    for sticker in design
                ]
            )

            if status != Order.STATUS_NEW:
                change_order_status(order, status, random.choice(staff_notes))
            completed_at = created_at + timedelta(minutes=random.randint(8, 25)) if status == Order.STATUS_COMPLETED else None
            Order.objects.filter(pk=order.pk).update(
                created_at=created_at,
                updated_at=created_at,
                completed_at=completed_at,
            )
            created_count += 1
        return created_count
