import io
import textwrap
from decimal import Decimal as D

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image, ImageColor, ImageDraw, ImageFont

from accounts.models import Address
from catalog.models import Brand, Category, Product, ProductVariant, StockHistory
from vendors.models import VendorStore

User = get_user_model()

ADDRESSES = [
    ('Umar', 'Umar', '9811122233', '12, MG Road', 'Bengaluru', 'Karnataka', '560001', True),
    ('Farhana', 'Farhana Hussain', '9822233344', '45, Park Street', 'Kolkata', 'West Bengal', '700016', True),
    ('Emil_Aydin', 'Emil Aydin', '9833344455', '7, Marine Drive', 'Mumbai', 'Maharashtra', '400020', True),
    ('Ezin_Ayan', 'Ezin Ayan', '9844455566', '22, Anna Salai', 'Chennai', 'Tamil Nadu', '600002', True),
    ('Hana', 'Hana', '9811122233', 'Mavoor', 'Kozhikode', 'Kerala', '673661', True),
]

# (name, parent) - parents must be listed before their children
CATEGORIES = [
    ('Electronics', None), ('Fashion', None), ('Beauty', None), ('Home & Living', None),
    ('Sports', None), ('Books', None), ('Kids & Toys', None),
    ('Headphones', 'Electronics'), ('Smartwatches', 'Electronics'), ('Mobiles', 'Electronics'),
]

# Colour used for the generated placeholder pictures
CATEGORY_COLORS = {
    'Electronics': '#4F46E5', 'Headphones': '#6B4C9A', 'Smartwatches': '#3B6FB6', 'Mobiles': '#2563EB',
    'Fashion': '#C2548A', 'Beauty': '#D9822B', 'Home & Living': '#2F8F83', 'Sports': '#2E8B57',
    'Books': '#8A5A44', 'Kids & Toys': '#E0568C',
}

BRANDS = ('Boat', 'Nike', 'Samsung', 'Puma')

R, S, A = StockHistory.Reason.RESTOCK, StockHistory.Reason.SALE, StockHistory.Reason.ADJUSTMENT
# name, category, brand, sku, price, discount, tax, description, [(variant, sku, [(qty, reason, note)])]
PRODUCTS = [
    ('Boat Rockerz 450 Headphones', 'Headphones', 'Boat', 'BOAT-RKZ450', '1999', '1299', '18',
     'Wireless over-ear headphones with 15-hour battery.',
     [('Black', 'BOAT-RKZ450-BLK', [(30, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('Blue', 'BOAT-RKZ450-BLU', [(10, R, 'Initial stock'), (-2, S, 'Order sale')])]),
    ('Boat Watch Xtend', 'Smartwatches', 'Boat', 'BOAT-XTEND', '3999', '2499', '18',
     'Smartwatch with calling, heart-rate and sleep tracking.',
     [('Black', 'BOAT-XTEND-BLK', [(20, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('Pink', 'BOAT-XTEND-PNK', [(5, R, 'Initial stock'), (-2, S, 'Order sale')])]),
    ('Nike Revolution 6 Shoes', 'Sports', 'Nike', 'NIKE-REV6', '3495', '2799', '12',
     'Lightweight everyday running shoes.',
     [('UK 7', 'NIKE-REV6-7', [(10, R, 'Initial stock')]),
      ('UK 8', 'NIKE-REV6-8', [(15, R, 'Initial stock'), (-3, S, 'Order sale')]),
      ('UK 9', 'NIKE-REV6-9', [(5, R, 'Initial stock'), (-5, S, 'Sold out')])]),
    ('Cotton Casual Shirt', 'Fashion', None, 'SHIRT-CTN01', '999', None, '12',
     'Soft breathable cotton shirt for daily wear.',
     [('M', 'SHIRT-CTN01-M', [(30, R, 'Initial stock')]),
      ('L', 'SHIRT-CTN01-L', [(25, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('XL', 'SHIRT-CTN01-XL', [(10, R, 'Initial stock'), (-5, S, 'Order sale')])]),
    ('Aloe Vera Face Gel 200ml', 'Beauty', None, 'BEAUTY-ALOE200', '349', '279', '18',
     'Hydrating aloe vera gel for face and skin.',
     [('Default', 'BEAUTY-ALOE200-D', [(60, R, 'Initial stock')])]),
    ('Ceramic Coffee Mug Set (2 pcs)', 'Home & Living', None, 'HOME-MUG2', '599', '449', '12',
     'Set of two ceramic mugs, 300ml each.',
     [('Default', 'HOME-MUG2-D', [(50, R, 'Initial stock'), (-10, S, 'Order sale')])]),
    # ---- new products ----
    ('Samsung Galaxy M14 5G', 'Mobiles', 'Samsung', 'SAM-M14', '14999', '12999', '18',
     '5G smartphone with 6000mAh battery and 50MP camera.',
     [('4GB + 128GB Silver', 'SAM-M14-4-SIL', [(25, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('6GB + 128GB Blue', 'SAM-M14-6-BLU', [(15, R, 'Initial stock'), (-3, S, 'Order sale')])]),
    ('Boat Airdopes 141 Earbuds', 'Headphones', 'Boat', 'BOAT-AD141', '2990', '1099', '18',
     'True wireless earbuds with 42-hour playback.',
     [('Black', 'BOAT-AD141-BLK', [(50, R, 'Initial stock'), (-10, S, 'Order sale')]),
      ('White', 'BOAT-AD141-WHT', [(10, R, 'Initial stock'), (-6, S, 'Order sale')])]),
    ('Puma Training T-Shirt', 'Fashion', 'Puma', 'PUMA-TEE01', '1299', '899', '12',
     'Moisture-wicking round neck training tee.',
     [('S', 'PUMA-TEE01-S', [(20, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('M', 'PUMA-TEE01-M', [(30, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('L', 'PUMA-TEE01-L', [(20, R, 'Initial stock'), (-2, S, 'Order sale')])]),
    ('Nike Sports Backpack', 'Sports', 'Nike', 'NIKE-BAG01', '2495', '1899', '12',
     'Spacious 25L backpack with padded laptop sleeve.',
     [('Default', 'NIKE-BAG01-D', [(20, R, 'Initial stock'), (-2, S, 'Order sale')])]),
    ('Yoga Mat 6mm', 'Sports', None, 'SPORT-YOGA6', '799', '599', '12',
     'Non-slip 6mm yoga and exercise mat.',
     [('Purple', 'SPORT-YOGA6-PUR', [(30, R, 'Initial stock')]),
      ('Blue', 'SPORT-YOGA6-BLU', [(25, R, 'Initial stock'), (-3, S, 'Order sale')])]),
    ('Matte Lipstick', 'Beauty', None, 'BEAUTY-LIP01', '499', '399', '18',
     'Long-lasting matte lipstick, smooth finish.',
     [('Rose', 'BEAUTY-LIP01-ROS', [(40, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('Red', 'BEAUTY-LIP01-RED', [(25, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('Nude', 'BEAUTY-LIP01-NUD', [(10, R, 'Initial stock'), (-4, S, 'Order sale')])]),
    ('Stainless Steel Water Bottle 1L', 'Home & Living', None, 'HOME-BTL1', '699', '549', '12',
     'Insulated bottle that keeps drinks cold for 24 hours.',
     [('Silver', 'HOME-BTL1-SIL', [(50, R, 'Initial stock'), (-5, S, 'Order sale')]),
      ('Black', 'HOME-BTL1-BLK', [(35, R, 'Initial stock'), (-5, S, 'Order sale')])]),
    ('LED Desk Lamp', 'Home & Living', None, 'HOME-LAMP01', '1299', '999', '18',
     'Adjustable LED lamp with three brightness levels.',
     [('Default', 'HOME-LAMP01-D', [(16, R, 'Initial stock'), (-2, S, 'Order sale')])]),
    
    ('Kids Building Blocks Set (100 pcs)', 'Kids & Toys', None, 'TOY-BLK100', '899', '699', '12',
     'Colourful interlocking blocks for ages 4 and up.',
     [('Default', 'TOY-BLK100-D', [(30, R, 'Initial stock'), (-5, S, 'Order sale')])]),
]


# ---------- pictures ----------
# Put your own photos in EcommerceProject/seed_images/ named by product SKU
# (e.g. BOAT-RKZ450.jpg) or by category slug (e.g. fashion.png). Anything missing
# gets a generated coloured placeholder with the product name on it.
IMAGE_DIR = settings.BASE_DIR / 'seed_images'


def custom_image(key):
    for ext in ('.jpg', '.jpeg', '.png', '.webp'):
        path = IMAGE_DIR / f'{key}{ext}'
        if path.exists():
            return path.read_bytes(), ext
    return None


def _font(px):
    for name in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        return ImageFont.load_default()


def make_image(title, color, size=800, px=58, wrap=16):
    base = ImageColor.getrgb(color)
    light = tuple(int(c + (255 - c) * 0.18) for c in base)
    img = Image.new('RGB', (size, size), base)
    d = ImageDraw.Draw(img)
    d.ellipse((-200, -200, 380, 380), fill=light)
    d.ellipse((size - 330, size - 330, size + 200, size + 200), fill=light)
    font = _font(px)
    lines = textwrap.wrap(title, wrap)[:5]
    line_h = int(px * 1.3)
    y = (size - line_h * len(lines)) // 2
    for line in lines:
        w = d.textlength(line, font=font)
        d.text(((size - w) / 2, y), line, font=font, fill='white')
        y += line_h
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=88)
    return buf.getvalue(), '.jpg'


def attach_image(field, key, title, color, px=58, wrap=16, refresh=False):
    custom = custom_image(key)  # your own photo in seed_images/ always wins
    # a picture counts only if the file really exists (deleted files are redrawn)
    has_file = bool(field) and field.storage.exists(field.name)
    if has_file and not custom and not refresh:
        return  # keep the picture that is already there
    data, ext = custom or make_image(title, color, px=px, wrap=wrap)
    field.save(f'{key}{ext}', ContentFile(data), save=True)


def get_or_make(model, name, **defaults):
    obj = model.objects.filter(name=name).first()
    return obj or model.objects.create(name=name, **defaults)


class Command(BaseCommand):
    help = 'Fill demo groups, categories, addresses, products (with pictures), variants and stock history. Safe to re-run.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh-images', action='store_true',
                            help='Redraw the generated pictures even if a product/category already has one')

    @transaction.atomic
    def handle(self, *args, **opts):
        refresh = opts['refresh_images']
        # Groups (admin permissions only; the app itself uses User.role)
        group_perms = {
            'Vendor Managers': Permission.objects.filter(content_type__app_label='vendors'),
            'Catalog Editors': Permission.objects.filter(content_type__app_label='catalog',
                                                         content_type__model__in=['product', 'productvariant', 'category', 'brand']),
            'Order Support': Permission.objects.filter(content_type__app_label='orders',
                                                       content_type__model__in=['order', 'vendororder']),
        }
        for name, perms in group_perms.items():
            g, _ = Group.objects.get_or_create(name=name)
            g.permissions.set(perms)

        # Vendor + approved store
        vendor, made = User.objects.get_or_create(
            username='techhub_vendor',
            defaults={'role': User.Role.VENDOR, 'email': 'vendor@techhub.com', 'mobile_number': '9876543210'})
        if made:
            vendor.set_password('Vendor@12345')
            vendor.save()
        VendorStore.objects.get_or_create(vendor=vendor, defaults={
            'store_name': 'TechHub Store', 'contact_number': '9876543210', 'status': VendorStore.Status.APPROVED})

        # Categories (+ pictures)
        cats = {}
        for name, parent in CATEGORIES:
            cat = get_or_make(Category, name, parent=cats.get(parent) if parent else None)
            cats[name] = cat
            attach_image(cat.image, cat.slug, name, CATEGORY_COLORS.get(name, '#6B4C9A'), px=100, wrap=12, refresh=refresh)

        brands = {n: get_or_make(Brand, n) for n in BRANDS}

        # Addresses (skips customers that don't exist)
        for uname, full, phone, line, city, state, pin, default in ADDRESSES:
            user = User.objects.filter(username=uname).first()
            if not user:
                self.stdout.write(self.style.WARNING(f'User {uname} not found - skipped address'))
                continue
            Address.objects.get_or_create(user=user, address_line=line, defaults={
                'full_name': full, 'phone': phone, 'city': city, 'state': state,
                'pincode': pin, 'is_default': default})

        # Products, pictures, variants, stock history
        new_products = 0
        for name, cat, brand, sku, price, disc, tax, desc, variants in PRODUCTS:
            product, made = Product.objects.get_or_create(sku=sku, defaults={
                'vendor': vendor, 'category': cats[cat], 'brand': brands.get(brand), 'name': name,
                'description': desc, 'short_description': desc[:200], 'price': D(price),
                'discount_price': D(disc) if disc else None, 'tax_percent': D(tax),
                'status': Product.Status.ACTIVE})
            new_products += made
            attach_image(product.image, sku, name, CATEGORY_COLORS.get(cat, '#6B4C9A'), refresh=refresh)
            for vname, vsku, logs in variants:
                variant, vmade = ProductVariant.objects.get_or_create(
                    sku=vsku, defaults={'product': product, 'name': vname, 'stock_quantity': 0})
                if vmade:
                    for qty, reason, note in logs:
                        StockHistory.objects.create(variant=variant, change_quantity=qty, reason=reason, note=note)
                    variant.stock_quantity = sum(q for q, _, _ in logs)
                    variant.save()
        self.stdout.write(self.style.SUCCESS(
            f'Demo data ready: {new_products} new products, {len(PRODUCTS)} in total. '
            'Vendor login: techhub_vendor / Vendor@12345'))
