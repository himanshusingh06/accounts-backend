from django.contrib import admin
from . models import *
# Register your models here.
admin.site.register(BankAccount)
admin.site.register(Transaction)
admin.site.register(LedgerEntry)
admin.site.register(CashbookEntry)
admin.site.register(Payment)
admin.site.register(Budget)
admin.site.register(AdministrativeOrder)