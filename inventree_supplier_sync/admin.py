from django.contrib import admin

from .models import SupplierPartChange


@admin.register(SupplierPartChange)
class SupplierPartChangeAdmin(admin.ModelAdmin):
    """Class for managing the SupplierPartChange model via the admin interface."""

    list_display = (
        'pk',
        'part',
        'change_type',
        'comment'
    )

    search_fields = [
        'change_type',
    ]
