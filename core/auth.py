# -*- coding: utf-8 -*-
"""登录 / session / 权限装饰器"""
import functools
from datetime import datetime
from flask import session, redirect, url_for, request, abort
import core.db as db
import core.perms as perms


def login():
    """登录成功后写入 session；返回 True/False"""
    pass  # 由 app.py 路由直接处理


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    u = perms.get_user_by_id(uid)
    if not u:
        session.clear()
        return None
    # 会话超时
    last = session.get('last_active')
    if last:
        try:
            if (datetime.now() - datetime.fromisoformat(last)).total_seconds() > 3600:
                session.clear()
                return None
        except ValueError:
            pass
    session['last_active'] = datetime.now().isoformat()
    return u


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u:
            # 手机端未登录 -> 手机登录页，避免跳到 PC 版登录页
            if perms.is_mobile(request):
                return redirect(url_for('m_login', next=request.path))
            return redirect(url_for('login_page', next=request.path))
        return f(*args, **kwargs)
    return wrapper


def need_inbound(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not perms.can_inbound(u):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def need_outbound(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not perms.can_outbound(u):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def need_query(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not perms.can_query(u):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def need_user_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not perms.can_manage_users(u):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def need_forms_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not perms.can_manage_forms(u):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def need_stocktake(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        u = current_user()
        if not u or not perms.can_stocktake(u):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def log_action(user, action, detail=''):
    """记录操作日志"""
    rows = db.read('operation_logs.csv')
    lid = db.next_id(rows, 'log', field='log_id')
    row = dict(log_id=lid, log_time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
               user_name=user['user_name'], action=action, detail=detail,
               ip=request.remote_addr or '')
    db.append('operation_logs.csv', row, db.FIELDS['operation_logs.csv'])
