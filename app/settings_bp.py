from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .app import db, User, get_setting, set_setting

bp = Blueprint('settings', __name__, url_prefix='/settings')


def require_app_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get('user_id')
        if not user_id:
            return redirect(url_for('login'))
        user = db.session.get(User, user_id)
        if not user or not user.is_kt_admin:
            return redirect(url_for('dashboard'))
        return fn(*args, **kwargs)

    return wrapper


@bp.get('/')
@require_app_admin
def index():
    return render_template('settings/index.html')


@bp.route('/mail', methods=['GET', 'POST'])
@require_app_admin
def mail_settings():
    if request.method == 'POST':
        port = request.form.get('smtp_port', '')
        if not port.isdigit():
            port = '587'
        entries = {
            'mail.smtp.host': request.form.get('smtp_host', ''),
            'mail.smtp.port': port,
            'mail.smtp.user': request.form.get('smtp_user', ''),
            'mail.from.default': request.form.get('from_default', ''),
            'mail.from.name': request.form.get('from_name', ''),
            'mail.from.prework': request.form.get('from_prework', ''),
            'mail.from.certificates': request.form.get('from_certificates', ''),
            'mail.from.clientsetup': request.form.get('from_clientsetup', ''),
        }
        for key, val in entries.items():
            set_setting(key, val)
        db.session.commit()
        flash('Saved')
        return redirect(url_for('settings.mail_settings'))

    host = get_setting('mail.smtp.host', 'smtp.office365.com')
    port = get_setting('mail.smtp.port', '587')
    user = get_setting('mail.smtp.user', '')
    from_default = get_setting('mail.from.default', 'certificates@kepner-tregoe.com')
    from_name = get_setting('mail.from.name', '')
    prework = get_setting('mail.from.prework', from_default)
    certs = get_setting('mail.from.certificates', from_default)
    clientsetup = get_setting('mail.from.clientsetup', from_default)
    values = {
        'smtp_host': host,
        'smtp_port': port,
        'smtp_user': user,
        'from_default': from_default,
        'from_name': from_name,
        'from_prework': prework,
        'from_certificates': certs,
        'from_clientsetup': clientsetup,
    }
    return render_template('settings/mail.html', values=values)


@bp.post('/mail/test')
@require_app_admin
def mail_test():
    from . import emailer
    to_email = request.form.get('test_email', '')
    category = request.form.get('test_category') or 'certificates'
    result = emailer.send_mail(
        to_email, 'CBS test mail', 'This is a CBS test.', category=category
    )
    if result.get('error'):
        flash(result['error'])
    else:
        flash('Test mail queued' if result.get('sent') else 'Test mail mock')
    return redirect(url_for('settings.mail_settings'))
