# college_bank_backend/bank_accounts/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UserRegistrationView, 
    BankAccountViewSet, TransactionViewSet, LedgerEntryViewSet
)

router = DefaultRouter()
router.register(r'bank-accounts', BankAccountViewSet, basename='bankaccount')
router.register(r'transactions', TransactionViewSet, basename='transaction') # <--- Check this line
router.register(r'ledger-entries', LedgerEntryViewSet, basename='ledgerentry') # <--- Check this line

urlpatterns = [
    path('register/', UserRegistrationView.as_view(), name='register'),
    #path('dashboard-summary/', DashboardSummaryView.as_view(), name='dashboard-summary'),
    path('', include(router.urls)), # Important: This includes all routes from the router
]