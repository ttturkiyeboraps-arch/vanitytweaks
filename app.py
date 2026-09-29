"""
VanityTweaks - Flask Web Application
Ana sunucu uygulaması: Landing page, Admin Dashboard, API endpoints.
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Admin, LicenseKey, ActivityLog
from datetime import datetime, timedelta
from functools import wraps
import os

# ==================== APP SETUP ====================

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'vanitytweaks-super-secret-key-change-in-production-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vanitytweaks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'admin_login'


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


# ==================== INIT DATABASE ====================

def init_db():
    """Veritabanını oluşturur ve varsayılan admin ekler."""
    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            admin = Admin(username='admin')
            admin.set_password('admin123')  # İlk kurulumda değiştirin!
            db.session.add(admin)
            db.session.commit()
            print("[*] Varsayılan admin oluşturuldu: admin / admin123")

# Otomatik veritabanı ilklendirme (Gunicorn / Production için)
with app.app_context():
    init_db()


# ==================== LANDING PAGE ====================

@app.route('/')
def index():
    """Ana sayfa / Landing page."""
    return render_template('index.html')


@app.route('/download')
def download():
    """İndirme sayfası."""
    return render_template('download.html')


# ==================== ADMIN AUTH ====================

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin giriş sayfası."""
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        admin = Admin.query.filter_by(username=username).first()
        if admin and admin.check_password(password):
            login_user(admin, remember=True)
            log_activity('admin_login', f'Admin login: {username}', request.remote_addr)
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password!', 'danger')

    return render_template('login.html')


@app.route('/admin/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))


# ==================== ADMIN DASHBOARD ====================

@app.route('/admin')
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """Admin ana panel."""
    total_keys = LicenseKey.query.count()
    active_keys = LicenseKey.query.filter_by(status='active').count()
    unused_keys = LicenseKey.query.filter_by(status='unused').count()
    expired_count = 0

    # Expired olanları say ve güncelle
    active_licenses = LicenseKey.query.filter_by(status='active').all()
    for lic in active_licenses:
        if lic.is_expired:
            lic.status = 'expired'
            expired_count += 1
    if expired_count > 0:
        db.session.commit()
        active_keys -= expired_count

    expired_keys = LicenseKey.query.filter_by(status='expired').count()
    revoked_keys = LicenseKey.query.filter_by(status='revoked').count()

    # Plan dağılımı
    m1_count = LicenseKey.query.filter_by(plan='M1').count()
    y1_count = LicenseKey.query.filter_by(plan='Y1').count()
    lt_count = LicenseKey.query.filter_by(plan='LT').count()

    # Son aktiviteler
    recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(15).all()

    return render_template('dashboard.html',
        total_keys=total_keys,
        active_keys=active_keys,
        unused_keys=unused_keys,
        expired_keys=expired_keys,
        revoked_keys=revoked_keys,
        m1_count=m1_count,
        y1_count=y1_count,
        lt_count=lt_count,
        recent_logs=recent_logs,
    )


# ==================== KEY MANAGEMENT ====================

@app.route('/admin/keys')
@login_required
def admin_keys():
    """Key yönetim sayfası."""
    status_filter = request.args.get('status', 'all')
    plan_filter = request.args.get('plan', 'all')

    query = LicenseKey.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if plan_filter != 'all':
        query = query.filter_by(plan=plan_filter)

    keys = query.order_by(LicenseKey.created_at.desc()).all()

    return render_template('keys.html',
        keys=keys,
        status_filter=status_filter,
        plan_filter=plan_filter,
    )


@app.route('/admin/keys/create', methods=['POST'])
@login_required
def admin_create_keys():
    """Key üretme."""
    plan = request.form.get('plan', 'M1')
    count = int(request.form.get('count', 1))
    note = request.form.get('note', '').strip()

    if plan not in ('M1', 'Y1', 'LT'):
        flash('Invalid plan!', 'danger')
        return redirect(url_for('admin_keys'))

    if count < 1 or count > 100:
        flash('You can generate between 1 and 100 keys!', 'danger')
        return redirect(url_for('admin_keys'))

    created_keys = []
    for _ in range(count):
        key_str = LicenseKey.generate_key(plan)
        # Unique check
        while LicenseKey.query.filter_by(key=key_str).first():
            key_str = LicenseKey.generate_key(plan)

        new_key = LicenseKey(
            key=key_str,
            plan=plan,
            note=note,
            created_by=current_user.id,
        )
        db.session.add(new_key)
        created_keys.append(key_str)

    db.session.commit()
    log_activity('key_create', f'Generated {count} {plan} keys', request.remote_addr)

    flash(f'{count} {LicenseKey.PLAN_NAMES[plan]} key(s) generated successfully!', 'success')

    # Save keys to session
    from flask import session
    session['last_created_keys'] = created_keys

    return redirect(url_for('admin_keys'))


@app.route('/admin/keys/<int:key_id>/revoke', methods=['POST'])
@login_required
def admin_revoke_key(key_id):
    """Revoke key."""
    key = LicenseKey.query.get_or_404(key_id)
    key.revoke()
    db.session.commit()
    log_activity('key_revoke', f'Key revoked: {key.key}', request.remote_addr)
    flash(f'Key revoked: {key.key}', 'warning')
    return redirect(url_for('admin_keys'))


@app.route('/admin/keys/<int:key_id>/reset', methods=['POST'])
@login_required
def admin_reset_key(key_id):
    """Reset key (Remove HWID)."""
    key = LicenseKey.query.get_or_404(key_id)
    key.reset()
    db.session.commit()
    log_activity('key_reset', f'Key reset: {key.key}', request.remote_addr)
    flash(f'Key reset successfully: {key.key}', 'info')
    return redirect(url_for('admin_keys'))


@app.route('/admin/keys/<int:key_id>/delete', methods=['POST'])
@login_required
def admin_delete_key(key_id):
    """Delete key."""
    key = LicenseKey.query.get_or_404(key_id)
    key_str = key.key
    db.session.delete(key)
    db.session.commit()
    log_activity('key_delete', f'Key deleted: {key_str}', request.remote_addr)
    flash(f'Key deleted: {key_str}', 'danger')
    return redirect(url_for('admin_keys'))


@app.route('/admin/keys/bulk-delete', methods=['POST'])
@login_required
def admin_bulk_delete():
    """Bulk delete keys."""
    key_ids = request.form.getlist('key_ids')
    if key_ids:
        count = LicenseKey.query.filter(LicenseKey.id.in_(key_ids)).delete(synchronize_session=False)
        db.session.commit()
        log_activity('key_bulk_delete', f'{count} keys bulk deleted', request.remote_addr)
        flash(f'{count} keys deleted!', 'warning')
    return redirect(url_for('admin_keys'))


# ==================== USER MANAGEMENT ====================

@app.route('/admin/users')
@login_required
def admin_users():
    """Aktif kullanıcılar sayfası."""
    active_users = LicenseKey.query.filter(
        LicenseKey.status == 'active',
        LicenseKey.hwid.isnot(None)
    ).order_by(LicenseKey.activated_at.desc()).all()

    return render_template('users.html', users=active_users)


# ==================== ACTIVITY LOGS ====================

@app.route('/admin/logs')
@login_required
def admin_logs():
    """Aktivite logları."""
    page = request.args.get('page', 1, type=int)
    logs = ActivityLog.query.order_by(
        ActivityLog.created_at.desc()
    ).paginate(page=page, per_page=50, error_out=False)
    return render_template('logs.html', logs=logs)


# ==================== API ENDPOINTS ====================

@app.route('/api/activate', methods=['POST'])
def api_activate():
    """
    Key aktivasyon API.
    Body: {"key": "EM-M1-XXXX-XXXX-XXXX-XXXX", "hwid": "abc123..."}
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Geçersiz istek.'}), 400

    key_str = data.get('key', '').strip().upper()
    hwid = data.get('hwid', '').strip()

    if not key_str or not hwid:
        return jsonify({'success': False, 'message': 'Key ve HWID gereklidir.'}), 400

    # Key'i bul
    license_key = LicenseKey.query.filter_by(key=key_str).first()

    if not license_key:
        log_activity('activate_fail', f'Key bulunamadı: {key_str}', request.remote_addr, hwid)
        return jsonify({'success': False, 'message': 'Geçersiz key!'}), 404

    # Durum kontrolleri
    if license_key.status == 'revoked':
        log_activity('activate_fail', f'İptal edilmiş key: {key_str}', request.remote_addr, hwid)
        return jsonify({'success': False, 'message': 'Bu key iptal edilmiş!'}), 403

    if license_key.status == 'active':
        if license_key.hwid == hwid:
            # Aynı HWID, zaten aktif
            if license_key.is_expired:
                license_key.status = 'expired'
                db.session.commit()
                return jsonify({'success': False, 'message': 'Key süresi dolmuş!'}), 403
            
            license_key.last_check = datetime.utcnow()
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Key zaten aktif.',
                'plan': license_key.plan,
                'plan_name': license_key.plan_name,
                'days_remaining': license_key.days_remaining,
                'expires_at': license_key.expires_at.isoformat() if license_key.expires_at else None,
            })
        else:
            log_activity('activate_fail', f'Farklı HWID ile deneme: {key_str}', request.remote_addr, hwid)
            return jsonify({'success': False, 'message': 'Bu key başka bir bilgisayarda aktif!'}), 403

    if license_key.status == 'expired':
        log_activity('activate_fail', f'Süresi dolmuş key: {key_str}', request.remote_addr, hwid)
        return jsonify({'success': False, 'message': 'Key süresi dolmuş!'}), 403

    # Aktivasyon
    license_key.activate(hwid, request.remote_addr)
    db.session.commit()

    log_activity('activate_success', f'Key aktive edildi: {key_str} (Plan: {license_key.plan_name})',
                 request.remote_addr, hwid, license_key.id)

    return jsonify({
        'success': True,
        'message': f'Key başarıyla aktive edildi! Plan: {license_key.plan_name}',
        'plan': license_key.plan,
        'plan_name': license_key.plan_name,
        'days_remaining': license_key.days_remaining,
        'expires_at': license_key.expires_at.isoformat() if license_key.expires_at else None,
    })


@app.route('/api/verify', methods=['POST'])
def api_verify():
    """
    Lisans doğrulama API. Client her açılışta bunu çağırır.
    Body: {"key": "...", "hwid": "..."}
    """
    data = request.get_json()
    if not data:
        return jsonify({'valid': False, 'message': 'Geçersiz istek.'}), 400

    key_str = data.get('key', '').strip().upper()
    hwid = data.get('hwid', '').strip()

    if not key_str or not hwid:
        return jsonify({'valid': False, 'message': 'Key ve HWID gereklidir.'}), 400

    license_key = LicenseKey.query.filter_by(key=key_str).first()

    if not license_key:
        return jsonify({'valid': False, 'message': 'Geçersiz key!'}), 404

    if license_key.status == 'revoked':
        return jsonify({'valid': False, 'message': 'Key iptal edilmiş!'}), 403

    if license_key.status != 'active':
        return jsonify({'valid': False, 'message': 'Key aktif değil.'}), 403

    if license_key.hwid != hwid:
        return jsonify({'valid': False, 'message': 'HWID uyuşmuyor!'}), 403

    if license_key.is_expired:
        license_key.status = 'expired'
        db.session.commit()
        return jsonify({'valid': False, 'message': 'Key süresi dolmuş!'}), 403

    # Geçerli - last_check güncelle
    license_key.last_check = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'valid': True,
        'message': 'Lisans geçerli.',
        'plan': license_key.plan,
        'plan_name': license_key.plan_name,
        'days_remaining': license_key.days_remaining,
        'expires_at': license_key.expires_at.isoformat() if license_key.expires_at else None,
    })


@app.route('/api/heartbeat', methods=['POST'])
def api_heartbeat():
    """
    Heartbeat API - client düzenli aralıklarla çağırır.
    Body: {"key": "...", "hwid": "..."}
    """
    data = request.get_json()
    if not data:
        return jsonify({'valid': False}), 400

    key_str = data.get('key', '').strip().upper()
    hwid = data.get('hwid', '').strip()

    license_key = LicenseKey.query.filter_by(key=key_str, hwid=hwid, status='active').first()

    if not license_key or license_key.is_expired:
        return jsonify({'valid': False}), 403

    license_key.last_check = datetime.utcnow()
    db.session.commit()
    return jsonify({'valid': True, 'days_remaining': license_key.days_remaining})


# ==================== HELPERS ====================

def log_activity(action, detail, ip=None, hwid=None, key_id=None):
    """Aktivite logu kaydeder."""
    log = ActivityLog(
        action=action,
        detail=detail,
        ip_address=ip,
        hwid=hwid,
        key_id=key_id,
    )
    db.session.add(log)
    db.session.commit()


# ==================== TEMPLATE FILTERS ====================

@app.template_filter('timeago')
def timeago_filter(dt):
    """Zaman farkını okunabilir formata çevirir."""
    if not dt:
        return '-'
    now = datetime.utcnow()
    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        return f'{int(seconds // 60)}m ago'
    elif seconds < 86400:
        return f'{int(seconds // 3600)}h ago'
    elif seconds < 604800:
        return f'{int(seconds // 86400)}d ago'
    else:
        return dt.strftime('%m/%d/%Y %H:%M')


@app.template_filter('format_date')
def format_date_filter(dt):
    if not dt:
        return '-'
    return dt.strftime('%d.%m.%Y %H:%M')


# ==================== RUN ====================

if __name__ == '__main__':
    init_db()
    print("\n" + "=" * 50)
    print("  EMTweaks Server başlatıldı!")
    print("  Site:  http://localhost:5000")
    print("  Admin: http://localhost:5000/admin")
    print("  Admin Giriş: admin / admin123")
    print("=" * 50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
