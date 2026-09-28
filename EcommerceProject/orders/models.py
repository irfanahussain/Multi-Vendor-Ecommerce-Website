from django.db import models
from django.conf import settings
from django.utils import timezone
from catalog.models import ProductVariant
from accounts.models import Address


# Create your models here.

class Cart(models.Model):
    user=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='cart')
    created_at=models.DateTimeField(auto_now_add=True)

    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    def subtotal(self):
        return sum(item.line_total() for item in self.items.all())


class CartItem(models.Model):
    cart=models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    variant=models.ForeignKey(ProductVariant, on_delete=models.CASCADE)
    quantity=models.PositiveIntegerField(default=1)

    class Meta:
        unique_together=('cart','variant')

    def line_total(self):
        return self.variant.effective_price*self.quantity


class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT ='percent','Percentage'
        FIXED='fixed','Fixed Amount'

    code=models.CharField(max_length=50,unique=True)
    discount_type=models.CharField(max_length=10,choices=DiscountType.choices)
    discount_value=models.DecimalField(max_digits=10,decimal_places=2)
    min_order_amount=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    max_discount=models.DecimalField(max_digits=10,decimal_places=2,blank=True,null=True)
    start_date=models.DateTimeField()
    expiry_date=models.DateTimeField()
    usage_limit=models.PositiveIntegerField(default=0)  
    used_count=models.PositiveIntegerField(default=0)
    customer_usage_limit=models.PositiveIntegerField(default=1)
    is_active=models.BooleanField(default=True)

    def __str__(self):
        return self.code

    def is_valid_now(self):
        now = timezone.now()
        if not self.is_active:
            return False, "This coupon is inactive."
        if now < self.start_date or now > self.expiry_date:
            return False,"This coupon has expired or is not active yet."
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "This coupon has reached its usage limit."
        return True, ""

    def calculate_discount(self, order_subtotal):
        if order_subtotal < self.min_order_amount:
            return 0
        if self.discount_type==self.DiscountType.PERCENT:
            discount=order_subtotal * (self.discount_value/100)
            if self.max_discount:
                discount=min(discount,self.max_discount)
        else:
            discount=self.discount_value
        return min(discount,order_subtotal)


class Order(models.Model):
    class PaymentMethod(models.TextChoices):
        COD='cod','Cash on Delivery'
        ONLINE='online','Online Payment'

    class PaymentStatus(models.TextChoices):
        PENDING='pending','Pending'
        PAID='paid', 'Paid'
        FAILED='failed','Failed'

    order_number=models.CharField(max_length=30, unique=True)
    customer=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,related_name='orders')
    shipping_address=models.ForeignKey(Address, on_delete=models.SET_NULL, null=True)
    coupon=models.ForeignKey(Coupon,on_delete=models.SET_NULL,null=True,blank=True)

    subtotal=models.DecimalField(max_digits=10,decimal_places=2)
    discount_amount=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    tax_amount=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    shipping_charge=models.DecimalField(max_digits=10,decimal_places=2,default=0)
    total_amount=models.DecimalField(max_digits=10,decimal_places=2)

    payment_method=models.CharField(max_length=10,choices=PaymentMethod.choices,default=PaymentMethod.COD)
    payment_status=models.CharField(max_length=10,choices=PaymentStatus.choices,default=PaymentStatus.PENDING)

    created_at=models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.order_number


class VendorOrder(models.Model):
    class Status(models.TextChoices):
        PENDING ='pending','Pending'
        CONFIRMED='confirmed','Confirmed'
        PROCESSING='processing','Processing'
        PACKED='packed','Packed'
        SHIPPED='shipped','Shipped'
        DELIVERED='delivered','Delivered'
        CANCELLED='cancelled','Cancelled'
        RETURNED='returned','Returned'
        REFUNDED='refunded','Refunded'

    order=models.ForeignKey(Order,on_delete=models.CASCADE,related_name='vendor_orders')
    vendor=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,related_name='vendor_orders')
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.PENDING)
    subtotal=models.DecimalField(max_digits=10,decimal_places=2,default=0)

   
    commission_percent=models.DecimalField(max_digits=5, decimal_places=2,default=10)
    commission_amount=models.DecimalField(max_digits=10, decimal_places=2,default=0)
    vendor_earning=models.DecimalField(max_digits=10, decimal_places=2,default=0)

    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    def save(self,*args,**kwargs):
        if self.subtotal:
            self.commission_amount=self.subtotal*(self.commission_percent/100)
            self.vendor_earning=self.subtotal-self.commission_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.order_number}—{self.vendor.username}"


class OrderItem(models.Model):
    vendor_order=models.ForeignKey(VendorOrder,on_delete=models.CASCADE,related_name='items')
    variant=models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True)
    product_name=models.CharField(max_length=255)   
    variant_name=models.CharField(max_length=150,blank=True)
    price=models.DecimalField(max_digits=10,decimal_places=2)  # snapshot price at purchase time
    quantity=models.PositiveIntegerField()

    def line_total(self):
        return self.price * self.quantity

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"
