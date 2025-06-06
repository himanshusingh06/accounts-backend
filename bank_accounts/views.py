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
    # Ensure 'account' is in filterset_fields if you want DjangoFilterBackend to handle it
    filterset_fields = ['account', 'transaction_type', 'transaction_head', 'transaction_mode', 'is_reconciled']
    search_fields = ['description', 'party_name', 'cheque_no']
    ordering_fields = ['transaction_date', 'amount', 'created_at']

    def get_queryset(self):
        """
        Optionally restricts the returned transactions to a given user,
        and filters by account, date range, or reconciliation status.
        """
        queryset = super().get_queryset()

        # Filter by authenticated user (superusers see all, others only their own)
        if not self.request.user.is_superuser:
            queryset = queryset.filter(created_by=self.request.user)

        # NEW: Filter by account_id from query parameters
        account_id = self.request.query_params.get('account')
        if account_id:
            try:
                queryset = queryset.filter(account_id=int(account_id))
            except ValueError:
                # Handle invalid account_id gracefully, e.g., return empty or log error
                return Transaction.objects.none() # Return an empty queryset for invalid ID

        # Date range filtering (already present, just ensure it works with other filters)
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(transaction_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transaction_date__lte=end_date)

        return queryset

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
        for tx_id in transaction_ids:
            try:
                # Ensure the transaction belongs to the current user if not superuser, and use get_queryset
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
        # This action implicitly uses get_queryset, so it will now respect account_id
        # and user permissions, as well as date range.
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
        # No need to filter again explicitly here as get_queryset already does that.
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
