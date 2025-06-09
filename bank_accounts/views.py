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


# NEW Imports needed for balance update
from bank_accounts.models import BankAccount # Assuming BankAccount model is in bank_accounts app
from bank_accounts.serializers import BankAccountSerializer # Also need serializer for bank_statement action
from django.db import transaction as db_transaction # For atomic database operations
from django.db.models import F # For atomic updates to prevent race conditions
from django.utils.dateparse import parse_date # NEW: To parse date strings safely



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
    filterset_fields = ['account', 'transaction_type', 'transaction_head', 'transaction_mode', 'is_reconciled']
    search_fields = ['description', 'party_name', 'cheque_no']
    ordering_fields = ['transaction_date', 'amount', 'created_at']

    def get_queryset(self):
        """
        Optionally restricts the returned transactions to a given user,
        and filters by account, date range, or reconciliation status.
        """
        queryset = super().get_queryset()

        if not self.request.user.is_superuser:
            queryset = queryset.filter(created_by=self.request.user)

        # Filter by account_id from query parameters
        account_id = self.request.query_params.get('account')
        if account_id:
            try:
                queryset = queryset.filter(account_id=int(account_id))
            except ValueError:
                return Transaction.objects.none() # Return an empty queryset for invalid ID

        # Date range filtering
        start_date_str = self.request.query_params.get('transaction_date__gte')
        end_date_str = self.request.query_params.get('transaction_date__lte')

        # Debugging: Print received date strings
        print(f"Backend: Received start_date_str: {start_date_str}, end_date_str: {end_date_str}")

        if start_date_str:
            parsed_start_date = parse_date(start_date_str)
            if parsed_start_date:
                queryset = queryset.filter(transaction_date__gte=parsed_start_date)
                print(f"Backend: Applying start date filter: {parsed_start_date}")
            else:
                print(f"Backend: Could not parse start date: {start_date_str}")

        if end_date_str:
            parsed_end_date = parse_date(end_date_str)
            if parsed_end_date:
                queryset = queryset.filter(transaction_date__lte=parsed_end_date)
                print(f"Backend: Applying end date filter: {parsed_end_date}")
            else:
                print(f"Backend: Could not parse end date: {end_date_str}")

        # Final check: Ensure the queryset is being filtered
        print(f"Backend: Final queryset count before return: {queryset.count()}")
        return queryset

    @db_transaction.atomic # Ensure atomic operations for balance updates
    def perform_create(self, serializer):
        """
        Save the new transaction and update the associated bank account's balance.
        """
        transaction_instance = serializer.save(created_by=self.request.user)

        account = transaction_instance.account
        amount = transaction_instance.amount

        if transaction_instance.transaction_type == 'CREDIT':
            account.current_balance = F('current_balance') + amount
        elif transaction_instance.transaction_type == 'DEBIT':
            account.current_balance = F('current_balance') - amount
        account.save(update_fields=['current_balance'])

    @db_transaction.atomic # Ensure atomic operations for balance updates
    def perform_update(self, serializer):
        """
        Update the transaction and adjust the associated bank account's balance.
        Handles changes in amount or type.
        """
        # Get old instance data before saving changes
        old_transaction_instance = self.get_object()
        old_amount = old_transaction_instance.amount
        old_type = old_transaction_instance.transaction_type

        # Save the new transaction data
        transaction_instance = serializer.save()

        new_amount = transaction_instance.amount
        new_type = transaction_instance.transaction_type
        account = transaction_instance.account

        # Only update balance if amount or type has changed for the same account
        if old_amount != new_amount or old_type != new_type:
            # Revert old transaction's impact
            if old_type == 'CREDIT':
                account.current_balance = F('current_balance') - old_amount
            elif old_type == 'DEBIT':
                account.current_balance = F('current_balance') + old_amount

            # Apply new transaction's impact
            if new_type == 'CREDIT':
                account.current_balance = F('current_balance') + new_amount
            elif new_type == 'DEBIT':
                account.current_balance = F('current_balance') - new_amount

            account.save(update_fields=['current_balance'])

    @db_transaction.atomic # Ensure atomic operations for balance updates
    def perform_destroy(self, instance):
        """
        Delete the transaction and revert its impact on the associated bank account's balance.
        """
        account = instance.account
        amount = instance.amount
        transaction_type = instance.transaction_type

        # Revert the transaction's impact before deleting it
        if transaction_type == 'CREDIT':
            account.current_balance = F('current_balance') - amount
        elif transaction_type == 'DEBIT':
            account.current_balance = F('current_balance') + amount
        account.save(update_fields=['current_balance'])

        # Now delete the transaction
        instance.delete()


    @action(detail=False, methods=['post'], url_path='bulk-reconcile')
    def bulk_reconcile(self, request):
        """
        Marks a list of transactions as reconciled.
        Requires a list of transaction IDs in the request body:
        { "transaction_ids": [1, 2, 3] }
        """
        if not request.user.is_staff and not request.user.is_superuser:
            return Response(
                {"detail": "You do not have permission to perform this action."},
                status=status.HTTP_403_FORBIDDEN
            )

        transaction_ids = request.data.get('transaction_ids', [])

        if not isinstance(transaction_ids, list):
            return Response(
                {"detail": "Invalid data. 'transaction_ids' must be a list."},
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_count = 0
        with db_transaction.atomic(): # Use atomic block for bulk operations
            for tx_id in transaction_ids:
                try:
                    transaction = self.get_queryset().get(id=tx_id)
                    if not transaction.is_reconciled:
                        transaction.is_reconciled = True
                        transaction.save(update_fields=['is_reconciled'])
                        updated_count += 1
                except Transaction.DoesNotExist:
                    print(f"Transaction with ID {tx_id} not found or not accessible.")
                except Exception as e:
                    print(f"Error reconciling transaction {tx_id}: {e}")

        return Response(
            {"message": f"Successfully reconciled {updated_count} transactions."},
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['get'])
    def bank_statement(self, request):
        account_id = request.query_params.get('account_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if not account_id or not start_date or not end_date:
            return Response(
                {"error": "Account ID, start date, and end date are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # The account_id and date range are already passed as query params
        # and handled by get_queryset(). Just order them for the statement.
        transactions = self.get_queryset().order_by('transaction_date')

        serializer = self.get_serializer(transactions, many=True)
        try:
            account = BankAccount.objects.get(id=account_id)
            account_serializer = BankAccountSerializer(account)
        except BankAccount.DoesNotExist:
            return Response(
                {"error": "Bank account not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            'account': account_serializer.data,
            'transactions': serializer.data
        })

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

# class PaymentViewSet(viewsets.ModelViewSet):
#     queryset = Payment.objects.all()
#     serializer_class = PaymentSerializer
#     permission_classes = [IsAuthenticated]

#     def perform_create(self, serializer):
#         # When creating a payment, ensure a corresponding transaction is created first
#         # This is a simplified example; in a real app, you'd handle this more robustly
#         # e.g., by creating the transaction within the serializer's create method.
#         transaction_data = self.request.data.get('transaction', {})
#         if not transaction_data:
#             raise serializers.ValidationError({"transaction": "Transaction details are required."})

#         # Ensure transaction_type is 'DEBIT' for payments
#         transaction_data['transaction_type'] = 'DEBIT'
#         transaction_data['created_by'] = self.request.user.id # Pass user ID

#         transaction_serializer = TransactionSerializer(data=transaction_data)
#         transaction_serializer.is_valid(raise_exception=True)
#         transaction = transaction_serializer.save(created_by=self.request.user) # Save with user

#         serializer.save(transaction=transaction)

# class BudgetViewSet(viewsets.ModelViewSet):
#     queryset = Budget.objects.all()
#     serializer_class = BudgetSerializer
#     permission_classes = [IsAuthenticated]

# class AdministrativeOrderViewSet(viewsets.ModelViewSet):
#     queryset = AdministrativeOrder.objects.all()
#     serializer_class = AdministrativeOrderSerializer
#     permission_classes = [IsAuthenticated]

#     def perform_create(self, serializer):
#         # If a related_transaction_id is provided, link it.
#         # Otherwise, the order might be created before the transaction.
#         serializer.save()


# --- New User Registration View ---
class UserRegistrationView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny] # Allow unauthenticated users to register
# --- End New User Registration View ---
