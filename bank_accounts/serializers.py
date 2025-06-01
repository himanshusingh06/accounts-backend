from rest_framework import serializers
from .models import BankAccount, Transaction, LedgerEntry, CashbookEntry, Payment, Budget, AdministrativeOrder
from django.contrib.auth.models import User

# class UserSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = User
#         fields = ['id', 'username', 'email']

class BankAccountSerializer(serializers.ModelSerializer):
     # This creates a writable field 'balance' that maps to 'current_balance'
    balance = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        source='current_balance', # This is the crucial part: maps 'balance' to 'current_balance'
        required=False, # Make it not required if it can be omitted
        default=0.00 # Set a default if it's not always sent
    )
    class Meta:
        model = BankAccount
        fields = '__all__'



class TransactionSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(
     queryset=BankAccount.objects.all() # This tells DRF which BankAccount objects are valid
    )
    account_name = serializers.CharField(source='account.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    class Meta:
        model = Transaction
        fields = '__all__'
        read_only_fields = ['created_by', 'created_by_username', 'bank_account_name']


class LedgerEntrySerializer(serializers.ModelSerializer):
    # Inherits fields from Transaction implicitly because LedgerEntry is a sub-model
    transaction_type = serializers.CharField(read_only=True) # Force 'DEBIT' or 'CREDIT' based on frontend logic
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = '__all__'

class CashbookEntrySerializer(serializers.ModelSerializer):
    transaction_type = serializers.CharField(read_only=True) # Will be set by `save` method of model
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = CashbookEntry
        fields = '__all__'

class PaymentSerializer(serializers.ModelSerializer):
    transaction = TransactionSerializer(read_only=True) # Nested serializer for transaction details
    transaction_id = serializers.PrimaryKeyRelatedField(
        queryset=Transaction.objects.all(), source='transaction', write_only=True
    )

    class Meta:
        model = Payment
        fields = '__all__'

class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = '__all__'

class AdministrativeOrderSerializer(serializers.ModelSerializer):
    related_transaction = TransactionSerializer(read_only=True)
    related_transaction_id = serializers.PrimaryKeyRelatedField(
        queryset=Transaction.objects.all(), source='related_transaction', write_only=True, allow_null=True, required=False
    )

    class Meta:
        model = AdministrativeOrder
        fields = '__all__'
        

# --- New User Serializer for Registration ---
class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        return user
# --- End New User Serializer ---
