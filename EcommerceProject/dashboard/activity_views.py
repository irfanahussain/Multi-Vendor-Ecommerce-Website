"""Full Activity Log page. Super Admin only."""
from datetime import timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_safe

from .models import ActivityLog
from .views import super_admin_required

DAY_OPTIONS = {'7': 'Last 7 days', '30': 'Last 30 days', '90': 'Last 90 days', 'all': 'All time'}


@super_admin_required
@require_safe
def activity_log(request):
    action = request.GET.get('action', '')
    days = request.GET.get('days', '30')
    if days not in DAY_OPTIONS:
        days = '30'
    entries = ActivityLog.objects.select_related('actor')
    if action in ActivityLog.Action.values:
        entries = entries.filter(action=action)
    else:
        action = ''
    if days != 'all':
        entries = entries.filter(created_at__gte=timezone.now() - timedelta(days=int(days)))
    page_obj = Paginator(entries, 50).get_page(request.GET.get('page'))
    return render(request, 'dashboard/activity.html', {
        'active': 'activity',
        'page_obj': page_obj,
        'actions': ActivityLog.Action.choices,
        'current_action': action,
        'day_options': DAY_OPTIONS,
        'current_days': days,
        'query_base': urlencode({'action': action, 'days': days}) + '&',
    })
