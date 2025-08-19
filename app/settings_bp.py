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
    from . import emailer
    categories = ['prework', 'certificates', 'clientsetup']
    if request.method == 'POST':
        for cat in categories:
            key = f'mail.from.{cat}'
            val = request.form.get(cat, '')
            setting = db.session.get(AppSetting, key)
            if setting:
                setting.value = val
            else:
                db.session.add(AppSetting(key=key, value=val))
        db.session.commit()
        flash('Saved')
        return redirect(url_for('settings.mail_settings'))
    values = {cat: emailer.get_from_for(cat) for cat in categories}
    return render_template('settings/mail.html', values=values)


@bp.post('/mail/test')
@require_app_admin
def mail_test():
    from . import emailer
    to_email = request.form.get('test_email', '')
    category = request.form.get('test_category', 'certificates')
    result = emailer.send_mail(to_email, 'Test Email', 'This is a test message', category=category)
    if result.get('sent'):
        flash('Email sent')
    else:
        flash('Logged email to stdout')
    return redirect(url_for('settings.mail_settings'))
