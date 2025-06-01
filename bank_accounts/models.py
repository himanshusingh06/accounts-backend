# bank_accounts/models.py
from django.db import models
from django.contrib.auth.models import User # For user authentication

class BankAccount(models.Model):
    """Represents a bank account held by the college."""
    name = models.CharField(max_length=255, unique=True)
    account_number = models.CharField(max_length=50, unique=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.account_number})"

class Transaction(models.Model):
    """Base model for all financial transactions."""
    TRANSACTION_TYPES = (
        ('DEBIT', 'Debit'),
        ('CREDIT', 'Credit'),
    )
    TRANSACTION_MODE = (
        ('NEFT', 'NEFT'),
        ('RTGS', 'RTGS'),
        ('CHEQUE', 'CHEQUE'),
        ('CASH', 'CASH'),
        ('OTHER', 'OTHER'),
    )

    TRANSACTION_HEADS = (
    # Previous 20
    ('ADVANCE', 'ADVANCE'),
    ('REIMBURSEMENT', 'REIMBURSEMENT'),
    ('ELECTRICITY', 'Electricity Bill'),
    ('REMUNERATION_TEACHERS', 'Teachers Remuneration'),
    ('SALARIES_STAFF', 'Staff Salaries'),
    ('MAINTENANCE_BUILDING', 'Building Maintenance'),
    ('LIBRARY_BOOKS', 'Library Books/Resources'),
    ('LAB_EQUIPMENT', 'Lab Equipment Purchase'),
    ('SPORTS_EQUIPMENT', 'Sports Equipment'),
    ('HOSTEL_EXPENSES', 'Hostel Operations/Maintenance'),
    ('ADVERTISING_MARKETING', 'Advertising & Marketing'),
    ('STUDENT_WELFARE', 'Student Welfare Activities'),
    ('UTILITIES_WATER', 'Water Bill'),
    ('TELEPHONE_INTERNET', 'Telephone & Internet Bills'),
    ('TRANSPORTATION', 'Transportation Costs'),
    ('EXAM_FEES_COLLECTION', 'Exam Fees Collection'),
    ('ADMISSION_FEES_COLLECTION', 'Admission Fees Collection'),
    ('DONATIONS_RECEIVED', 'Donations Received'),
    ('BANK_INTEREST_EARNED', 'Bank Interest Earned'),
    ('VENDOR_PAYMENT_SUPPLIES', 'Vendor Payment - Office Supplies'),
    ('SECURITY_SERVICES', 'Security Services'),
    ('AUDIT_FEES', 'Audit Fees'),

    # New 20 additions
    ('SCHOLARSHIPS_DISBURSED', 'Scholarships Disbursed'),
    ('CULTURAL_EVENTS', 'Cultural Event Expenses'),
    ('SPORTS_EVENTS', 'Sports Event Expenses'),
    ('RENT_RECEIVED', 'Rent Received (Property/Facilities)'),
    ('SEMINARS_WORKSHOPS', 'Seminars & Workshops Expenses'),
    ('RESEARCH_GRANTS_RECEIVED', 'Research Grants Received'),
    ('BANK_CHARGES', 'Bank Charges/Fees'),
    ('STUDENT_FEES_TUITION', 'Student Tuition Fees'),
    ('EQUIPMENT_REPAIR', 'Equipment Repair & Servicing'),
    ('UNIFORM_PURCHASE', 'Uniform Purchase'),
    ('PRINTING_STATIONERY', 'Printing & Stationery'),
    ('GOVT_GRANTS_RECEIVED', 'Government Grants Received'),
    ('TAX_PAYMENTS', 'Tax Payments'),
    ('LOAN_REPAYMENT', 'Loan Repayment (Principal & Interest)'),
    ('CONSTRUCTION_EXPENSES', 'New Construction/Renovation'),
    ('OTHERS', 'OTHERS')
)
    account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    transaction_head = models.CharField(max_length=50, choices=TRANSACTION_HEADS)
    transaction_mode = models.CharField(max_length=50, choices=TRANSACTION_MODE)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    cheque_no = models.CharField(max_length=10, blank=True, null=True )
    description = models.TextField(blank=True, null=True)
    transaction_date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date', '-created_at'] # Order by latest transactions

    def __str__(self):
        return f"{self.transaction_type} {self.amount} on {self.transaction_date}"

class LedgerEntry(Transaction):
    """Specific entry for the general ledger."""
    # Inherits from Transaction, so it has account, type, amount, date, etc.
    reference_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    # You might add specific ledger accounts here if needed, e.g., a ForeignKey to a ChartOfAccounts model

    def save(self, *args, **kwargs):
        # Update bank account balance on save
        if not self.pk: # Only on creation
            if self.transaction_type == 'CREDIT':
                self.account.current_balance += self.amount
            elif self.transaction_type == 'DEBIT':
                self.account.current_balance -= self.amount
            self.account.save()
        super().save(*args, **kwargs)

class CashbookEntry(Transaction):
    """Specific entry for the cash book (cash-in-hand transactions)."""
    # Inherits from Transaction
    is_cash_in = models.BooleanField(default=True) # True for cash received, False for cash paid out
    # You might have a separate 'CashInHand' account in BankAccount model, or a specific cash account.

    def save(self, *args, **kwargs):
        # This logic assumes 'account' for CashbookEntry refers to a specific cash account.
        # You might need more sophisticated logic if cash is handled separately from bank accounts.
        if not self.pk:
            if self.is_cash_in:
                self.transaction_type = 'CREDIT'
            else:
                self.transaction_type = 'DEBIT'
        super().save(*args, **kwargs)


class Payment(models.Model):
    """Base model for all payments (teachers, vendors)."""
    PAYMENT_TYPES = (
        ('TEACHER', 'Teacher Payment'),
        ('VENDOR', 'Vendor Payment'),
        ('OTHER', 'Other Payment'),
    )
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='payment_details')
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPES)
    payee_name = models.CharField(max_length=255)
    reference_document = models.CharField(max_length=255, blank=True, null=True, help_text="e.g., Invoice number, administrative order ID")
    payment_method = models.CharField(max_length=50, default='Bank Transfer') # e.g., 'Bank Transfer', 'Cheque', 'Cash'
    payment_date = models.DateField()
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.payment_type} to {self.payee_name} for {self.transaction.amount}"

class Budget(models.Model):
    """Represents a budget for a specific period or category."""
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    allocated_amount = models.DecimalField(max_digits=15, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Budget: {self.name} ({self.start_date} to {self.end_date})"

class AdministrativeOrder(models.Model):
    """Represents an administrative order for a payment or transaction."""
    order_number = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    order_date = models.DateField()
    approved_by = models.CharField(max_length=255)
    amount_sanctioned = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    related_transaction = models.OneToOneField(Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name='admin_order')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Admin Order: {self.order_number} - {self.title}"