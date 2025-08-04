from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, Numeric
from sqlalchemy.orm import relationship
from .base import Base, TimestampMixin
import enum
from datetime import datetime, timedelta

class SubscriptionType(enum.Enum):
    """Enum for subscription types"""
    MONTHLY = "monthly"      # 30 days
    SIX_MONTHS = "six_months"  # 6 months
    YEARLY = "yearly"        # 1 year

class SubscriptionStatus(enum.Enum):
    """Enum for subscription status"""
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"

class Subscription(Base, TimestampMixin):
    """Subscription model for tracking user payment records"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # User relationship
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="subscriptions")
    
    # Subscription details
    subscription_type = Column(Enum(SubscriptionType), nullable=False)
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING)
    
    # Payment tracking
    amount_paid = Column(Numeric(10, 2), nullable=False)  # Amount in currency (e.g., USD)
    currency = Column(String(3), default="USD")  # ISO currency code
    payment_method = Column(String(50), nullable=True)  # e.g., "stripe", "paypal"
    payment_reference = Column(String(255), nullable=True)  # External payment ID
    
    # Subscription period
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    
    # Auto-renewal settings
    auto_renew = Column(Boolean, default=True)
    next_billing_date = Column(DateTime(timezone=True), nullable=True)
    
    # Cancellation tracking
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(String(500), nullable=True)
    
    def __repr__(self):
        return f"<Subscription(id={self.id}, user_id={self.user_id}, type='{self.subscription_type.value}', status='{self.status.value}')>"
    
    @property
    def is_active(self):
        """Check if subscription is currently active"""
        now = datetime.utcnow()
        return (
            self.status == SubscriptionStatus.ACTIVE and
            self.start_date <= now <= self.end_date
        )
    
    @property
    def is_expired(self):
        """Check if subscription has expired"""
        return datetime.utcnow() > self.end_date
    
    @property
    def days_remaining(self):
        """Get number of days remaining in subscription"""
        if not self.is_active:
            return 0
        remaining = self.end_date - datetime.utcnow()
        return max(0, remaining.days)
    
    def calculate_end_date(self, start_date=None):
        """Calculate end date based on subscription type"""
        if start_date is None:
            start_date = datetime.utcnow()
        
        if self.subscription_type == SubscriptionType.MONTHLY:
            return start_date + timedelta(days=30)
        elif self.subscription_type == SubscriptionType.SIX_MONTHS:
            return start_date + timedelta(days=180)
        elif self.subscription_type == SubscriptionType.YEARLY:
            return start_date + timedelta(days=365)
        else:
            raise ValueError(f"Unknown subscription type: {self.subscription_type}")
    
    def renew_subscription(self, payment_amount, payment_reference=None):
        """Renew the subscription for another period"""
        if not self.auto_renew:
            raise ValueError("Auto-renewal is disabled for this subscription")
        
        # Set new start date to current end date
        new_start_date = self.end_date
        new_end_date = self.calculate_end_date(new_start_date)
        
        # Create new subscription record
        new_subscription = Subscription(
            user_id=self.user_id,
            subscription_type=self.subscription_type,
            status=SubscriptionStatus.ACTIVE,
            amount_paid=payment_amount,
            currency=self.currency,
            payment_method=self.payment_method,
            payment_reference=payment_reference,
            start_date=new_start_date,
            end_date=new_end_date,
            auto_renew=self.auto_renew,
            next_billing_date=new_end_date
        )
        
        return new_subscription
    
    def cancel_subscription(self, reason=None):
        """Cancel the subscription"""
        self.status = SubscriptionStatus.CANCELLED
        self.cancelled_at = datetime.utcnow()
        self.cancellation_reason = reason
        self.auto_renew = False
        self.next_billing_date = None
    
    def to_dict(self):
        """Convert subscription to dictionary for API responses"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "subscription_type": self.subscription_type.value,
            "status": self.status.value,
            "amount_paid": float(self.amount_paid) if self.amount_paid else None,
            "currency": self.currency,
            "payment_method": self.payment_method,
            "payment_reference": self.payment_reference,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "auto_renew": self.auto_renew,
            "next_billing_date": self.next_billing_date.isoformat() if self.next_billing_date else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "cancellation_reason": self.cancellation_reason,
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "days_remaining": self.days_remaining,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        } 