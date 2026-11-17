from .services import cart_summary, design_preview


def shop(request):
    """Счётчики корзины и стикеров для шапки сайта."""
    if request.path.startswith("/manage/") or request.path.startswith("/django-admin/"):
        return {}
    summary = cart_summary(request.session)
    return {
        "cart_count": summary["count"],
        "cart_total": summary["total"],
        "design_count": len(design_preview(request.session)),
    }
