from django import forms
from .models import VendorStore


class VendorStoreForm(forms.ModelForm):
    class Meta:
        model=VendorStore
        fields = ['store_name','logo','banner','business_description','business_address','contact_number']
