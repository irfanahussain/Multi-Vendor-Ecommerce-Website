from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from orders.models import OrderItem, VendorOrder
from .forms import ReturnRequestForm
from .models import ReturnRequest
from .services import units_claimed
# Create your views here.



@login_required
def request_return(request, order_item_id):
    order_item = get_object_or_404(
        OrderItem, pk=order_item_id, vendor_order__order__customer=request.user,
    )
    if order_item.vendor_order.status != 'delivered':
        messages.error(request, 'Only delivered items can be returned.')
        return redirect('orders:order_detail', order_number=order_item.vendor_order.order.order_number)

    if request.method == 'POST':
        form = ReturnRequestForm(request.POST)
        if form.is_valid():
            created = None
            # Lock the item and its sub-order, then check the remaining quantity and create the request
            # in the same transaction. Two simultaneous requests therefore run one after the other, and
            # the second sees the first one's quantity: accepted units can never exceed purchased units.
            with transaction.atomic():
                locked_item = OrderItem.objects.select_for_update().get(pk=order_item.pk)
                locked_order = VendorOrder.objects.select_for_update().get(pk=locked_item.vendor_order_id)
                remaining = locked_item.quantity - units_claimed(locked_item)
                quantity = form.cleaned_data['quantity']
                if locked_order.status != 'delivered':
                    messages.error(request, 'Only delivered items can be returned.')
                elif quantity < 1:
                    messages.error(request, "Return quantity must be at least 1.")
                elif quantity > remaining:
                    messages.error(request, f"You can return at most {max(remaining, 0)} more of this item.")
                else:
                    created = form.save(commit=False)
                    created.order_item = locked_item
                    created.customer = request.user
                    created.save()
            if created is not None:
                messages.success(request, 'Return request submitted.')
                return redirect('returns:my_returns')
    else:
        form = ReturnRequestForm(initial={'quantity': order_item.quantity})
    return render(request, 'returns_app/request_return.html', {'form': form, 'order_item': order_item})


@login_required
def my_returns(request):
    returns = ReturnRequest.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'returns_app/my_returns.html', {'returns': returns})
