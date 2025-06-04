from django.shortcuts import render

# Create your views here.
# bank_accounts/views.py
from rest_framework import viewsets, status,generics
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from .models import BankAccount, Transaction, LedgerEntry, CashbookEntry, Payment, Budget, AdministrativeOrder
from .serializers import (
    BankAccountSerializer, TransactionSerializer, LedgerEntrySerializer,
    CashbookEntrySerializer, PaymentSerializer, BudgetSerializer,
    AdministrativeOrderSerializer, UserSerializer # Import the new UserSerializer
)
from django.db.models import Sum
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from django.db import transaction


class BankAccountViewSet(viewsets.ModelViewSet):
    # Add the queryset attribute here
    queryset = BankAccount.objects.all() # Define the base queryset for the viewset
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = []
    search_fields = ['account_name', 'account_number', 'bank_name', 'name']
    ordering_fields = ['balance', 'created_at']

    def get_queryset(self):
        # This method can still apply further filtering if needed,
        # but the viewset now has a default queryset.
        # Since you want all users to see all accounts, this can simply return self.queryset
        # or if you previously had a filter here for user-specific data, you'd remove it for global view.
        return self.queryset.all().order_by('-created_at') # Or simply return self.queryset if no further filtering

class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = [ 'account__name', 'account__account_number', 'transaction_type', 'transaction_head', 'transaction_mode', 'is_reconciled','is_pp'] # Add 'is_reconciled'
    search_fields = ['description', 'party_name', 'cheque_no'] # Add party_name to search
    ordering_fields = ['amount', 'date', 'created_at']

    @transaction.atomic  # Wrap in an atomic transaction
    def perform_create(self, serializer):
        transaction = serializer.save(created_by=self.request.user)
        account = transaction.account
        amount = transaction.amount

        if transaction.transaction_type == 'CREDIT':
            account.current_balance += amount
        elif transaction.transaction_type == 'DEBIT':
            account.current_balance -= amount
        account.save()

    @transaction.atomic  # Wrap in an atomic transaction
    def perform_update(self, serializer):
        original_transaction = self.get_object()
        original_account = original_transaction.account
        original_amount = original_transaction.amount
        original_type = original_transaction.transaction_type

        transaction = serializer.save()
        new_account = transaction.account
        new_amount = transaction.amount
        new_type = transaction.transaction_type

        # Scenario 1: Account changed
        if original_account != new_account:
            # Revert original account's balance
            if original_type == 'CREDIT':
                original_account.current_balance -= original_amount
            elif original_type == 'DEBIT':
                original_account.current_balance += original_amount
            original_account.save()

            # Apply new transaction to new account's balance
            if new_type == 'CREDIT':
                new_account.current_balance += new_amount
            elif new_type == 'DEBIT':
                new_account.current_balance -= new_amount
            new_account.save()
        else:
            # Scenario 2: Account is the same, amount or type changed
            # Calculate the *difference* in amount
            amount_difference = new_amount - original_amount

            # Apply the *difference* based on transaction type
            if new_type == 'CREDIT':
                original_account.current_balance += amount_difference
            elif new_type == 'DEBIT':
                original_account.current_balance -= amount_difference
            original_account.save()

    @transaction.atomic  # Wrap in an atomic transaction
    def perform_destroy(self, instance):
        account = instance.account
        amount = instance.amount
        transaction_type = instance.transaction_type

        if transaction_type == 'CREDIT':
            account.current_balance -= amount
        elif transaction_type == 'DEBIT':
            account.current_balance += amount
        account.save()
        instance.delete()

    @action(detail=False, methods=['get'])
    def bank_statement(self, request):
        account_id = request.query_params.get('account_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not all([account_id, start_date, end_date]):
            return Response({"error": "account_id, start_date, and end_date are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            account = BankAccount.objects.get(id=account_id)
            transactions = Transaction.objects.filter(
                account=account,
                transaction_date__range=[start_date, end_date]
            ).order_by('transaction_date')
            serializer = self.get_serializer(transactions, many=True)
            return Response({
                "account": BankAccountSerializer(account).data,
                "transactions": serializer.data
            })
        except BankAccount.DoesNotExist:
            return Response({"error": "Bank account not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LedgerEntryViewSet(viewsets.ModelViewSet):
    queryset = LedgerEntry.objects.all()
    serializer_class = LedgerEntrySerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class CashbookEntryViewSet(viewsets.ModelViewSet):
    queryset = CashbookEntry.objects.all()
    serializer_class = CashbookEntrySerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # When creating a payment, ensure a corresponding transaction is created first
        # This is a simplified example; in a real app, you'd handle this more robustly
        # e.g., by creating the transaction within the serializer's create method.
        transaction_data = self.request.data.get('transaction', {})
        if not transaction_data:
            raise serializers.ValidationError({"transaction": "Transaction details are required."})

        # Ensure transaction_type is 'DEBIT' for payments
        transaction_data['transaction_type'] = 'DEBIT'
        transaction_data['created_by'] = self.request.user.id # Pass user ID

        transaction_serializer = TransactionSerializer(data=transaction_data)
        transaction_serializer.is_valid(raise_exception=True)
        transaction = transaction_serializer.save(created_by=self.request.user) # Save with user

        serializer.save(transaction=transaction)

class BudgetViewSet(viewsets.ModelViewSet):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    permission_classes = [IsAuthenticated]

class AdministrativeOrderViewSet(viewsets.ModelViewSet):
    queryset = AdministrativeOrder.objects.all()
    serializer_class = AdministrativeOrderSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # If a related_transaction_id is provided, link it.
        # Otherwise, the order might be created before the transaction.
        serializer.save()


# --- New User Registration View ---
class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny] # Allow unauthenticated users to register
# --- End New User Registration View ---
