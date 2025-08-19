from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from .app import db, AppSetting, User

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
    categories = ['prework', 'certificates', 'clientsetup']

    def get_setting(key: str, default: str = "") -> str:
        try:
            setting = db.session.get(AppSetting, key)
            return setting.value if setting else default
        except Exception:
            return default

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
        }
        for cat in categories:
            entries[f'mail.from.{cat}'] = request.form.get(cat, '')
        for key, val in entries.items():
            setting = db.session.get(AppSetting, key)
            if setting:
                setting.value = val
            else:
                db.session.add(AppSetting(key=key, value=val))
        db.session.commit()
        flash('Saved')
        return redirect(url_for('settings.mail_settings'))

    values = {
        'smtp_host': get_setting('mail.smtp.host', 'smtp.office365.com'),
        'smtp_port': get_setting('mail.smtp.port', '587'),
        'smtp_user': get_setting('mail.smtp.user', ''),
        'from_default': get_setting('mail.from.default', 'certificates@kepner-tregoe.com'),
        'from_name': get_setting('mail.from.name', ''),
    }
    for cat in categories:
        values[cat] = get_setting(f'mail.from.{cat}', values['from_default'])
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
    if result.get('sent'):
        flash('Test email sent')
    else:
        flash(result.get('error', 'Logged email to stdout'))
    return redirect(url_for('settings.mail_settings'))
