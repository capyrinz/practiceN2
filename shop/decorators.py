from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Пускает только авторизованных пользователей с нужной ролью."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if user.is_superuser or user.role in roles:
                return view(request, *args, **kwargs)
            raise PermissionDenied("Недостаточно прав для этого раздела.")

        return wrapper

    return decorator
