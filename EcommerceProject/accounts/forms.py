from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Address


class RegisterForm(UserCreationForm):
    ROLE_CHOICES = (
        (User.Role.CUSTOMER,'Customer — I want to shop'),
        (User.Role.VENDOR,'Vendor — I want to sell'),
    )
    role=forms.ChoiceField(choices=ROLE_CHOICES, widget=forms.RadioSelect)
    email=forms.EmailField(required=True)
    mobile_number=forms.CharField(required=False)

    class Meta:
        model=User
        fields=['username','email','mobile_number','role','password1','password2']

    def save(self,commit=True):
        user=super().save(commit=False)
        user.role=self.cleaned_data['role']
        user.email=self.cleaned_data['email']
        user.mobile_number=self.cleaned_data.get('mobile_number', '')
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model=User
        fields=['first_name','last_name','email','mobile_number','profile_image']


class AddressForm(forms.ModelForm):
    class Meta:
        model=Address
        fields=['full_name','phone','address_line','city','state','pincode','is_default']
