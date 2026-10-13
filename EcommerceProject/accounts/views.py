from django.shortcuts import render
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import RegisterForm,ProfileForm,AddressForm
from .models import Address
from vendors.models import VendorStore
# Create your views here.

def register_view(request):
    if request.method=='POST':
        form=RegisterForm(request.POST)
        if form.is_valid():
            user=form.save()
            if user.role==user.Role.VENDOR:
                VendorStore.objects.create(
                    vendor=user,
                    store_name=f"{user.username}'s Store",
                    status=VendorStore.Status.PENDING,
                )
            login(request,user)
            messages.success(request,'Account created successfully!')
            return redirect('dashboard:redirect')
    else:
        form = RegisterForm()
    return render(request,'accounts/register.html',{'form':form})


@login_required
def profile_view(request):
    if request.method=='POST':
        form=ProfileForm(request.POST,request.FILES,instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request,'Profile updated.')
            return redirect('accounts:profile')
    else:
        form =ProfileForm(instance=request.user)
    addresses = request.user.addresses.all()
    return render(request, 'accounts/profile.html', {'form': form, 'addresses': addresses})


@login_required
def address_add(request):
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, 'Address added.')
            # Only same-site targets: a ?next= pointing elsewhere must not redirect the customer off-site.
            next_url = request.GET.get('next', '')
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure()):
                next_url = ''
            return redirect(next_url or 'accounts:profile')
    else:
        form = AddressForm()
    return render(request, 'accounts/address_form.html', {'form': form})


@login_required
def address_delete(request, pk):
    address = get_object_or_404(Address,pk=pk,user=request.user)
    address.delete()
    messages.success(request,'Address removed.')
    return redirect('accounts:profile')
