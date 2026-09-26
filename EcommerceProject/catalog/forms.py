from django import forms
from .models import Product,ProductVariant,Category,Brand


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'category','brand','name','sku','short_description','description',
            'image','price','discount_price','tax_percent','weight',
        ]

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['category'].queryset=Category.objects.filter(is_active=True)
        self.fields['brand'].queryset=Brand.objects.filter(is_active=True)


class ProductVariantForm(forms.ModelForm):
    class Meta:
        model=ProductVariant
        fields=['name','sku','price','stock_quantity','image','is_active']


class StockAdjustForm(forms.Form):
    change_quantity=forms.IntegerField(help_text="Positive to add stock,negative to remove.")
    note=forms.CharField(max_length=255,required=False)
