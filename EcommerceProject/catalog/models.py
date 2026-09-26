from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.urls import reverse


class Category(models.Model):
    name=models.CharField(max_length=100)
    slug=models.SlugField(unique=True,blank=True)
    parent=models.ForeignKey('self',on_delete=models.CASCADE,null=True,blank=True,related_name='subcategories')
    image=models.ImageField(upload_to='categories/',blank=True,null=True)
    description=models.TextField(blank=True)
    is_active=models.BooleanField(default=True)

    class Meta:
        verbose_name_plural='Categories'

    def __str__(self):
        return self.name

    def save(self,*args,**kwargs):
        if not self.slug:
            self.slug=slugify(self.name)
        super().save(*args, **kwargs)


class Brand(models.Model):
    name=models.CharField(max_length=100)
    slug=models.SlugField(unique=True,blank=True)
    logo=models.ImageField(upload_to='brands/',blank=True,null=True)
    description=models.TextField(blank=True)
    is_active=models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def save(self,*args,**kwargs):
        if not self.slug:
            self.slug=slugify(self.name)
        super().save(*args,**kwargs)


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT='draft','Draft'
        PENDING='pending','Pending Approval'
        APPROVED='approved','Approved'
        REJECTED='rejected','Rejected'
        ACTIVE='active','Active'
        INACTIVE='inactive','Inactive'

    vendor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE,related_name='products')
    category=models.ForeignKey(Category, on_delete=models.SET_NULL, null=True,related_name='products')
    brand=models.ForeignKey(Brand,on_delete=models.SET_NULL,null=True,blank=True,related_name='products')

    name=models.CharField(max_length=255)
    slug=models.SlugField(unique=True,blank=True,max_length=280)
    sku=models.CharField(max_length=100,unique=True)
    description=models.TextField(blank=True)
    short_description=models.CharField(max_length=255,blank=True)
    image=models.ImageField(upload_to='products/',blank=True,null=True)

    price=models.DecimalField(max_digits=10, decimal_places=2)
    discount_price=models.DecimalField(max_digits=10, decimal_places=2,blank=True,null=True)
    tax_percent=models.DecimalField(max_digits=5, decimal_places=2, default=0)
    weight=models.DecimalField(max_digits=8,decimal_places=2,blank=True,null=True)

    status=models.CharField(max_length=20,choices=Status.choices,default=Status.PENDING)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    def save(self,*args,**kwargs):
        if not self.slug:
            base_slug=slugify(self.name)
            slug=base_slug
            counter=1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug=f"{base_slug}-{counter}"
                counter+=1
            self.slug=slug
        super().save(*args,**kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('catalog:product_detail',args=[self.slug])

    @property
    def display_price(self):
        return self.discount_price if self.discount_price else self.price

    @property
    def discount_percent(self):
        if self.discount_price and self.price:
            return round((1 - (self.discount_price/self.price)) * 100)
        return 0

    def total_stock(self):
        variants = self.variants.all()
        if variants:
            return sum(v.stock_quantity for v in variants)
        return 0

    def average_rating(self):
        reviews=self.reviews.filter(is_hidden=False)
        if not reviews:
            return 0
        return round(sum(r.rating for r in reviews)/len(reviews), 1)


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=150, default='Default')  
    sku = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)  # overrides product price if set
    stock_quantity = models.PositiveIntegerField(default=0)
    image = models.ImageField(upload_to='variants/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    @property
    def effective_price(self):
        if self.price is not None:
            return self.price
        return self.product.display_price

    def in_stock(self):
        return self.stock_quantity > 0


class StockHistory(models.Model):
    class Reason(models.TextChoices):
        RESTOCK='restock','Restock'
        SALE='sale','Sale'
        RETURN='return','Return'
        ADJUSTMENT='adjustment','Manual Adjustment'

    variant=models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='stock_history')
    change_quantity=models.IntegerField()  # positive = added, negative = removed
    reason=models.CharField(max_length=20, choices=Reason.choices)
    note=models.CharField(max_length=255, blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural='Stock History'
        ordering=['-created_at']

    def __str__(self):
        return f"{self.variant}{self.change_quantity:+d}({self.reason})"
