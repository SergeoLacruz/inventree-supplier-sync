from django.db import models


class SupplierPartChange(models.Model):

    class Meta:
        app_label = "inventree_supplier_sync"

    part = models.ForeignKey('part.Part', on_delete=models.SET_NULL, null=True)
    change_type = models.CharField(max_length=100, null=True)
    old_value = models.CharField(max_length=100, null=True)
    new_value = models.CharField(max_length=100, null=True)
    comment = models.CharField(max_length=250, null=True)
    link = models.CharField(max_length=250, null=True)
    updated_at = models.DateTimeField(auto_now=True)
