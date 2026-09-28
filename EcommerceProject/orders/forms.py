from django import forms


class CouponForm(forms.Form):
    code=forms.CharField(max_length=50)


class CheckoutForm(forms.Form):
    PAYMENT_CHOICES = (('cod', 'Cash on Delivery'),('online','Online Payment(demo)'))
    address_id=forms.IntegerField()
    payment_method=forms.ChoiceField(choices=PAYMENT_CHOICES)
