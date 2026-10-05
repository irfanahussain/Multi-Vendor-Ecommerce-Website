from .models import Brand, Category


def nav_categories(request):
    return {
        'nav_categories': Category.objects.filter(is_active=True, parent=None).only('name', 'slug')[:12],
        'nav_brands': Brand.objects.filter(is_active=True).only('name')[:12],
    }
