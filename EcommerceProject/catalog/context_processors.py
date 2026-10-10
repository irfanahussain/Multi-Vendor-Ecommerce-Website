from django.db.models import Prefetch

from .models import Brand,Category


def nav_categories(request):
    children=Category.objects.filter(is_active=True).only('name','slug','parent').order_by('name')
    top=(Category.objects.filter(is_active=True,parent=None).only('name','slug')
           .order_by('name').prefetch_related(Prefetch('subcategories', queryset=children,to_attr='nav_children')))
    return {
        'nav_categories':list(top[:12]),
        'nav_brands':Brand.objects.filter(is_active=True).only('name')[:12],
    }
