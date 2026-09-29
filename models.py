"""
EMTweaks - Database Models
SQLAlchemy ile veritabanı modelleri.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import string

db = SQLAlchemy()


class Admin(UserMixin, db.Model):
    """Admin kullanıcı modeli."""
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class LicenseKey(db.Model):
    """Lisans key modeli."""
    __tablename__ = 'license_keys'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    plan = db.Column(db.String(10), nullable=False)  # M1, Y1, LT
    status = db.Column(db.String(20), default='unused')  # unused, active, expired, revoked
    hwid = db.Column(db.String(64), nullable=True)
    activated_ip = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    activated_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    last_check = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.String(200), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)

    PLAN_NAMES = {
        'BASIC': 'Basic (24 Tweaks)',
        'STANDARD': 'Standard (70 Tweaks)',
        'ADVANCED': 'Advanced (338 Tweaks)',
        'PRO': 'Pro (Everything)',
        'M1': '1 Aylık',
        'Y1': '1 Yıllık',
        'LT': 'Lifetime',
    }

    PLAN_DAYS = {
        'BASIC': 999999,
        'STANDARD': 999999,
        'ADVANCED': 999999,
        'PRO': 999999,
        'M1': 30,
        'Y1': 365,
        'LT': 999999,
    }

    @staticmethod
    def generate_key(plan: str) -> str:
        """Benzersiz key üretir."""
        chars = string.ascii_uppercase + string.digits
        part1 = ''.join(secrets.choice(chars) for _ in range(4))
        part2 = ''.join(secrets.choice(chars) for _ in range(4))
        part3 = ''.join(secrets.choice(chars) for _ in range(4))
        part4 = ''.join(secrets.choice(chars) for _ in range(4))
        return f"VT-{plan}-{part1}-{part2}-{part3}-{part4}"

    @property
    def plan_name(self):
        return self.PLAN_NAMES.get(self.plan, self.plan)

    @property
    def is_expired(self):
        if self.plan == 'LT':
            return False
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    @property
    def days_remaining(self):
        if self.plan == 'LT':
            return 999999
        if self.expires_at is None:
            return 0
        delta = self.expires_at - datetime.utcnow()
        return max(0, delta.days)

    @property
    def status_display(self):
        if self.status == 'revoked':
            return 'Revoked'
        if self.status == 'active' and self.is_expired:
            return 'Expired'
        return self.status.capitalize()

    def activate(self, hwid: str, ip: str = None):
        """Key'i aktive eder."""
        self.status = 'active'
        self.hwid = hwid
        self.activated_ip = ip
        self.activated_at = datetime.utcnow()
        days = self.PLAN_DAYS.get(self.plan, 30)
        self.expires_at = datetime.utcnow() + timedelta(days=days)
        self.last_check = datetime.utcnow()

    def revoke(self):
        """Key'i iptal eder."""
        self.status = 'revoked'
        self.hwid = None

    def reset(self):
        """Key'i sıfırlar (HWID kaldırır, tekrar kullanılabilir yapar)."""
        self.status = 'unused'
        self.hwid = None
        self.activated_at = None
        self.expires_at = None
        self.activated_ip = None
        self.last_check = None


class ActivityLog(db.Model):
    """Aktivite log modeli."""
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False)
    detail = db.Column(db.String(500), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    hwid = db.Column(db.String(64), nullable=True)
    key_id = db.Column(db.Integer, db.ForeignKey('license_keys.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
