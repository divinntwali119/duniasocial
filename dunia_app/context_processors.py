def unread_notifications_count(request):
    """Expose the authenticated user's unread notification count to templates."""
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {'unread_notifications_count': 0}
    return {
        'unread_notifications_count': user.notifications_dunia.filter(lue=False).count(),
    }
