from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('vendor_status', 'Vendor store status'), ('product_status', 'Product status'), ('order_status', 'Order status'), ('stock_adjust', 'Stock adjustment'), ('customer_block', 'Customer blocked or unblocked'), ('coupon_created', 'Coupon created'), ('refund_status', 'Refund status')], max_length=32)),
                ('target_type', models.CharField(blank=True, max_length=40)),
                ('target_id', models.PositiveBigIntegerField(blank=True, null=True)),
                ('summary', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
