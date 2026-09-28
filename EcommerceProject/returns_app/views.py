from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from orders.models import OrderItem
from .forms import ReturnRequestForm
from .models import ReturnRequest
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
            if form.cleaned_data['quantity'] > order_item.quantity:
                messages.error(request, "Return quantity can't exceed purchased quantity.")
            else:
                return_request = form.save(commit=False)
                return_request.order_item = order_item
                return_request.customer = request.user
                return_request.save()
                messages.success(request, 'Return request submitted.')
                return redirect('returns:my_returns')
    else:
        form = ReturnRequestForm(initial={'quantity': order_item.quantity})
    return render(request, 'returns_app/request_return.html', {'form': form, 'order_item': order_item})


@login_required
def my_returns(request):
    returns = ReturnRequest.objects.filter(customer=request.user).order_by('-created_at')
    return render(request, 'returns_app/my_returns.html', {'returns': returns})
