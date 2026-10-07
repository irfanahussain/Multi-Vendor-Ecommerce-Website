import re
from decimal import Decimal

from django import forms
from django.utils.text import slugify

from catalog.models import Brand, Category
from orders.models import Coupon


def _bootstrap(form):
    """Give every widget its Bootstrap class on the server, so forms look right without JS."""
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            css = 'form-check-input'
        elif isinstance(widget, forms.Select):
            css = 'form-select'
        else:
            css = 'form-control'
        widget.attrs['class'] = f"{widget.attrs.get('class', '')} {css}".strip()


class _NameSlugForm(forms.ModelForm):
    """Shared by Category and Brand.

    The models build a slug from the name only when it is blank, and never check
    it for clashes. A duplicate would surface as a 500 (IntegrityError), so the
    slug is worked out and checked here and reported as a normal form error.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get('name') or '').strip()
        typed_slug = cleaned.get('slug')
        slug = typed_slug or slugify(name)
        if name and not slug:
            self.add_error('name', 'Name must contain letters or numbers.')
        elif slug:
            clash = self._meta.model.objects.filter(slug=slug)
            if self.instance.pk:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                if typed_slug:
                    self.add_error('slug', 'This slug is already used.')
                else:
                    self.add_error('name', f'A record with the slug "{slug}" already exists. Use a different name or set a slug.')
            else:
                cleaned['slug'] = slug
        return cleaned


def _descendant_ids(category):
    """The category's own id plus all of its sub-categories (any depth)."""
    seen = {category.pk}
    frontier = [category.pk]
    while frontier:
        children = set(Category.objects.filter(parent_id__in=frontier).values_list('pk', flat=True)) - seen
        seen |= children
        frontier = list(children)
    return seen


class CategoryForm(_NameSlugForm):
    class Meta:
        model = Category
        fields = ['name', 'slug', 'parent', 'image', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
        help_texts = {'slug': 'Leave blank to generate it from the name.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = Category.objects.order_by('name')
        if self.instance.pk:
            # A category can't be moved under itself or one of its own sub-categories.
            parents = parents.exclude(pk__in=_descendant_ids(self.instance))
        self.fields['parent'].queryset = parents
        self.fields['parent'].empty_label = '— Top level —'


class BrandForm(_NameSlugForm):
    class Meta:
        model = Brand
        fields = ['name', 'slug', 'logo', 'description', 'is_active']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
        help_texts = {'slug': 'Leave blank to generate it from the name.'}


_DT_FORMATS = ['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']


class CouponAdminForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        input_formats=_DT_FORMATS,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )
    expiry_date = forms.DateTimeField(
        input_formats=_DT_FORMATS,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
    )

    class Meta:
        model = Coupon
        fields = ['code', 'discount_type', 'discount_value', 'min_order_amount', 'max_discount',
                  'start_date', 'expiry_date', 'usage_limit', 'customer_usage_limit', 'is_active']
        help_texts = {
            'code': 'Saved in capitals, because customers\' codes are matched in capitals.',
            'discount_value': 'A percentage (1-100) or an amount, depending on the type.',
            'max_discount': 'Optional cap for percentage coupons.',
            'usage_limit': 'Total uses allowed. 0 = unlimited.',
            'customer_usage_limit': 'Uses allowed per customer.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _bootstrap(self)

    def clean_code(self):
        code = (self.cleaned_data['code'] or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9_-]+', code):
            raise forms.ValidationError('Use only letters, numbers, "-" and "_" (no spaces).')
        clash = Coupon.objects.filter(code__iexact=code)
        if self.instance.pk:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError('A coupon with this code already exists.')
        return code

    def clean_discount_value(self):
        value = self.cleaned_data['discount_value']
        if value is not None and value <= 0:
            raise forms.ValidationError('Discount must be greater than zero.')
        return value

    def clean_max_discount(self):
        value = self.cleaned_data.get('max_discount')
        if value is not None and value <= 0:
            raise forms.ValidationError('Maximum discount must be greater than zero (or leave it blank).')
        return value

    def clean_min_order_amount(self):
        value = self.cleaned_data.get('min_order_amount')
        if value is not None and value < 0:
            raise forms.ValidationError('Minimum order amount cannot be negative.')
        return value

    def clean(self):
        cleaned = super().clean()
        if (cleaned.get('discount_type') == Coupon.DiscountType.PERCENT
                and cleaned.get('discount_value') is not None
                and cleaned['discount_value'] > Decimal('100')):
            self.add_error('discount_value', 'A percentage discount cannot be more than 100.')
        start, expiry = cleaned.get('start_date'), cleaned.get('expiry_date')
        if start and expiry and expiry <= start:
            self.add_error('expiry_date', 'Expiry must be after the start date.')
        return cleaned
