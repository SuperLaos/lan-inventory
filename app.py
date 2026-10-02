# -*- coding: utf-8 -*-
"""市场管理中心物料仓库进销存系统 —— Flask 主程序"""
import os
import configparser
from datetime import datetime, date
from io import BytesIO
from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, abort, Response)

import core.db as db
import core.perms as perms
import core.auth as auth
from core.seed import seed

app = Flask(__name__)

# ---- 配置 ----
_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(app.root_path, 'config.ini'), encoding='utf-8')
HOST = _cfg.get('server', 'host', fallback='0.0.0.0')
PORT = _cfg.getint('server', 'port', fallback='5000')
DEBUG = _cfg.getboolean('server', 'debug', fallback=False)
SESSION_TIMEOUT = _cfg.getint('session', 'timeout_minutes', fallback='60')


def _load_secret_key():
    """Flask 会话密钥：存 data/.flask_key（已 gitignore，不进仓库），
    首次运行随机生成，重启后保持不变，所有已登录会话不失效。"""
    import secrets as _s
    key_file = os.path.join(app.root_path, 'data', '.flask_key')
    if os.path.exists(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            k = f.read().strip()
            if k:
                return k
    k = _s.token_hex(32)
    os.makedirs(os.path.dirname(key_file), exist_ok=True)
    with open(key_file, 'w', encoding='utf-8') as f:
        f.write(k)
    return k


app.config['SECRET_KEY'] = _load_secret_key()
app.jinja_env.globals['now'] = datetime.now
app.jinja_env.globals['perms_role_name'] = lambda r: perms.ROLE_NAMES.get(r, r)
app.jinja_env.globals['perms_dept_name'] = perms.get_dept_name
app.jinja_env.globals['perms'] = perms

# 种子数据（首次运行）
seed()


# ================= UA 分流（手机自动跳 /m，PC 自动跳回） =================
MOBILE_EXEMPT = ('/logout', '/api/')  # 这些路径不做设备跳转


def resp_tpl(name, **ctx):
    """按设备渲染模板：手机 -> mobile/xxx.html，PC -> xxx.html"""
    t = 'mobile/' + name if perms.is_mobile(request) else name
    return render_template(t, **ctx)


@app.before_request
def device_redirect():
    if request.method not in ('GET', 'HEAD'):
        return None
    path = request.path
    if path.startswith('/static') or path.startswith(MOBILE_EXEMPT):
        return None
    mob = perms.is_mobile(request)
    if mob and not path.startswith('/m'):
        return redirect('/m' + ('' if path == '/' else path))
    if not mob and path.startswith('/m'):
        return redirect(path[2:] or '/')
    return None


# ================= 工具函数 =================
def today():
    return date.today().strftime('%Y-%m-%d')


def users_in_dept(dept_id):
    """该部门下的所有人员（所属部门包含 dept_id）"""
    return [u for u in db.read('users.csv') if dept_id in (u.get('dept_ids') or '').split(';')]


def dept_pairs():
    return [(d['dept_id'], d['dept_name']) for d in db.read('departments.csv')]


def category_pairs():
    return [(c['category_id'], c['category_name']) for c in db.read('categories.csv')]


def unit_pairs():
    return [(u['unit_id'], u['unit_name']) for u in db.read('units.csv')]


def supplier_names():
    return [s['supplier_name'] for s in db.read('suppliers.csv')]


def company_dept_names():
    """全公司部门名（含 7 个部门 + 外部部门），供领用部门下拉"""
    return [d['dept_name'] for d in db.read('company_depts.csv')]


def stock_of(dept_id, user_id):
    """某部门+人员名下的库存记录"""
    return [s for s in db.read('stock.csv')
            if s['dept_id'] == dept_id and s['user_id'] == user_id]


# ================= 登录 / 改密 =================
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        name = (request.form.get('user_name') or '').strip()
        pwd = (request.form.get('password') or '').strip()
        u = perms.get_user_by_name(name)
        if not u or u['password'] != pwd:
            return resp_tpl('login.html', error='用户名或密码错误')
        session.clear()
        session['uid'] = u['user_id']
        session['login_at'] = datetime.now().isoformat()
        session['last_active'] = datetime.now().isoformat()
        if u.get('force_change_password') == '1':
            return redirect(url_for('change_password'))
        return redirect(url_for('index'))
    return resp_tpl('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    u = auth.current_user()
    if not u:
        return redirect(url_for('login_page'))
    if request.method == 'POST':
        p1 = (request.form.get('new_pwd') or '').strip()
        p2 = (request.form.get('confirm_pwd') or '').strip()
        if len(p1) < 4:
            return resp_tpl('change_password.html', error='新密码至少 4 位')
        if p1 != p2:
            return resp_tpl('change_password.html', error='两次密码不一致')

        def _set(r):
            r['password'] = p1
            r['force_change_password'] = '0'
            return r

        db.update_rows('users.csv',
                       lambda r: r['user_id'] == u['user_id'],
                       _set, db.FIELDS['users.csv'])
        auth.log_action(u, '修改密码')
        session['pwd_just_changed'] = '1'
        return redirect(url_for('index'))
    return resp_tpl('change_password.html', user=u)


# ================= 首页 =================
@app.route('/')
@auth.login_required
def index():
    u = auth.current_user()
    rows = perms.filter_rows(db.read('stock.csv'), u)
    for r in rows:
        r['dept_name'] = perms.get_dept_name(r['dept_id'])
        r['user_name'] = perms.get_user_name(r['user_id'])
    warns = [r for r in rows if r['quantity'].isdigit() and r['safety_threshold'].isdigit()
             and int(r['quantity']) < int(r['safety_threshold'])]

    def count_today(rows_, date_field):
        return sum(1 for r in rows_ if r.get(date_field) == today())

    ins = perms.filter_rows(db.read('stock_in.csv'), u)
    outs = perms.filter_rows(db.read('stock_out.csv'), u)
    return resp_tpl('index.html', user=u, menu=perms.menu(u),
                           warns=warns, today=today(),
                           today_in=count_today(ins, 'in_date'),
                           today_out=count_today(outs, 'out_date'),
                           total_stock=len(rows), low_count=len(warns),
                           bid_visible=perms.can_see_bid_price(u))


# ================= 入库 =================
@app.route('/inbound', methods=['GET'])
@auth.need_inbound
def inbound():
    u = auth.current_user()
    return resp_tpl('inbound.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), categories=category_pairs(),
                           units=unit_pairs(), suppliers=supplier_names(),
                           today=today())


@app.route('/api/users_by_dept')
@auth.login_required
def api_users_by_dept():
    dept = request.args.get('dept_id', '')
    return jsonify([{'user_id': x['user_id'], 'user_name': x['user_name']}
                    for x in users_in_dept(dept)])


@app.route('/api/stock_by_owner')
@auth.login_required
def api_stock_by_owner():
    """某部门+人员名下库存（供续作入库/出库级联）"""
    dept = request.args.get('dept_id', '')
    uid = request.args.get('user_id', '')
    rows = stock_of(dept, uid)
    return jsonify([dict(stock_id=r['stock_id'], material_id=r['material_id'],
                         material_name=r['material_name'],
                         category_name=r['category_name'],
                         supplier_name=r['supplier_name'], unit_name=r['unit_name'],
                         quantity=r['quantity'],
                         safety_threshold=r['safety_threshold'],
                         last_in_date=r['last_in_date']) for r in rows])


@app.route('/inbound/new', methods=['POST'])
@auth.need_inbound
def inbound_new():
    u = auth.current_user()
    f = request.form
    dept_id = f.get('dept_id', '').strip()
    user_id = f.get('user_id', '').strip()
    category_id = f.get('category_id', '').strip()
    material_name = (f.get('material_name') or '').strip()
    supplier = (f.get('supplier_name') or '').strip()
    unit_id = f.get('unit_id', '').strip()
    qty = (f.get('quantity') or '').strip()
    threshold = (f.get('safety_threshold') or '').strip()
    in_date = f.get('in_date') or today()
    bid_date = f.get('bid_date', '').strip()
    bid_price = (f.get('bid_price') or '').strip()

    # ---- 校验 ----
    errs = []
    if not (dept_id and user_id and category_id and material_name and supplier
            and unit_id and qty and threshold):
        errs.append('所有带 * 的字段都必填')
    if not qty.isdigit() or int(qty) <= 0:
        errs.append('入库数量必须是大于 0 的整数')
    if not threshold.isdigit() or int(threshold) < 0:
        errs.append('安全库存阈值必须是 0 或正整数')
    if not bid_date or not bid_price:
        errs.append('新品入库必须填写中标时间和中标价格')
    try:
        float(bid_price)
    except ValueError:
        errs.append('中标价格必须是数字')
    if errs:
        return resp_tpl('inbound.html', user=u, menu=perms.menu(u),
                               depts=dept_pairs(), categories=category_pairs(),
                               units=unit_pairs(), suppliers=supplier_names(),
                               today=today(), errors=errs, form=f)

    # 查重：该物料+部门+人员是否已有库存记录
    for s in stock_of(dept_id, user_id):
        if s['material_name'] == material_name:
            return resp_tpl('inbound.html', user=u, menu=perms.menu(u),
                                   depts=dept_pairs(), categories=category_pairs(),
                                   units=unit_pairs(), suppliers=supplier_names(),
                                   today=today(),
                                   errors=[f'「{material_name}」在 {perms.get_dept_name(dept_id)} '
                                           f'{perms.get_user_name(user_id)} 名下已有库存记录，'
                                           f'请改走「续作入库」'],
                                   form=f)

    # 供应商不在字典里 → 自动新增
    sup_rows = db.read('suppliers.csv')
    if supplier not in [x['supplier_name'] for x in sup_rows]:
        sid = db.next_id(sup_rows, 's', field='supplier_id')
        db.append('suppliers.csv', dict(supplier_id=sid, supplier_name=supplier),
                  db.FIELDS['suppliers.csv'])

    # 物料字典：有则复用，无则新增
    mat_rows = db.read('materials.csv')
    mat = next((m for m in mat_rows
                if m['material_name'] == material_name and m['category_id'] == category_id), None)
    if mat is None:
        mat_id = db.next_id(mat_rows, 'm', field='material_id')
        db.append('materials.csv', dict(material_id=mat_id, category_id=category_id,
                                        material_name=material_name, unit_id=unit_id),
                  db.FIELDS['materials.csv'])
    else:
        mat_id = mat['material_id']

    cat_name = next((c['category_name'] for c in db.read('categories.csv')
                     if c['category_id'] == category_id), '')
    unit_name = next((x['unit_name'] for x in db.read('units.csv')
                      if x['unit_id'] == unit_id), '')

    stock_rows = db.read('stock.csv')
    stock_id = db.next_id(stock_rows, 's', field='stock_id')
    db.append('stock.csv', dict(stock_id=stock_id, material_id=mat_id,
                                category_name=cat_name, material_name=material_name,
                                supplier_name=supplier, unit_name=unit_name,
                                dept_id=dept_id, user_id=user_id,
                                quantity=qty, safety_threshold=threshold,
                                last_in_date=in_date),
              db.FIELDS['stock.csv'])

    in_rows = db.read('stock_in.csv')
    in_id = db.next_id(in_rows, 'in', field='in_id')
    db.append('stock_in.csv', dict(in_id=in_id, in_date=in_date, stock_id=stock_id,
                                   material_id=mat_id, material_name=material_name,
                                   category_name=cat_name, supplier_name=supplier,
                                   unit_name=unit_name, dept_id=dept_id, user_id=user_id,
                                   quantity=qty, safety_threshold=threshold,
                                   operation_type='new', bid_date=bid_date,
                                   bid_price=bid_price, operator_name=u['user_name']),
              db.FIELDS['stock_in.csv'])

    auth.log_action(u, '新品入库',
                    f'{material_name} ×{qty}{unit_name} → '
                    f'{perms.get_dept_name(dept_id)}/{perms.get_user_name(user_id)}')
    return resp_tpl('inbound.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), categories=category_pairs(),
                           units=unit_pairs(), suppliers=supplier_names(),
                           today=today(),
                           success=f'新品入库成功：{material_name} ×{qty}{unit_name}')


@app.route('/inbound/restock', methods=['POST'])
@auth.need_inbound
def inbound_restock():
    u = auth.current_user()
    f = request.form
    dept_id = f.get('dept_id', '').strip()
    user_id = f.get('user_id', '').strip()
    stock_id = f.get('stock_id', '').strip()
    supplier = (f.get('supplier_name') or '').strip()
    qty = (f.get('quantity') or '').strip()
    threshold = (f.get('safety_threshold') or '').strip()
    in_date = f.get('in_date') or today()

    errs = []
    if not (dept_id and user_id and stock_id and supplier and qty and threshold):
        errs.append('所有带 * 的字段都必填')
    if not qty.isdigit() or int(qty) <= 0:
        errs.append('入库数量必须是大于 0 的整数')
    if not threshold.isdigit() or int(threshold) < 0:
        errs.append('安全库存阈值必须是 0 或正整数')

    stock_rows = db.read('stock.csv')
    target = next((s for s in stock_rows if s['stock_id'] == stock_id), None)
    if target is None:
        errs.append('所选库存记录不存在，请检查部门/人员/物料选择')
    elif target['dept_id'] != dept_id or target['user_id'] != user_id:
        errs.append('该物料不属于所选部门+人员，不能续作入库')

    if errs:
        return resp_tpl('inbound.html', user=u, menu=perms.menu(u),
                               depts=dept_pairs(), categories=category_pairs(),
                               units=unit_pairs(), suppliers=supplier_names(),
                               today=today(), errors=errs, form=f, tab='restock')

    if supplier not in supplier_names():
        sup_rows = db.read('suppliers.csv')
        sid = db.next_id(sup_rows, 's', field='supplier_id')
        db.append('suppliers.csv', dict(supplier_id=sid, supplier_name=supplier),
                  db.FIELDS['suppliers.csv'])

    new_qty = int(target['quantity']) + int(qty)

    def _upd(r):
        if r['stock_id'] == stock_id:
            r['quantity'] = str(new_qty)
            r['safety_threshold'] = threshold
            r['last_in_date'] = in_date
        return r

    db.update_rows('stock.csv', lambda r: r['stock_id'] == stock_id,
                   _upd, db.FIELDS['stock.csv'])

    in_rows = db.read('stock_in.csv')
    in_id = db.next_id(in_rows, 'in', field='in_id')
    db.append('stock_in.csv', dict(in_id=in_id, in_date=in_date,
                                   stock_id=target['stock_id'],
                                   material_id=target['material_id'],
                                   material_name=target['material_name'],
                                   category_name=target['category_name'],
                                   supplier_name=supplier,
                                   unit_name=target['unit_name'],
                                   dept_id=dept_id, user_id=user_id,
                                   quantity=qty, safety_threshold=threshold,
                                   operation_type='restock', bid_date='', bid_price='',
                                   operator_name=u['user_name']),
              db.FIELDS['stock_in.csv'])

    auth.log_action(u, '续作入库',
                    f'{target["material_name"]} ×{qty}{target["unit_name"]} → '
                    f'{perms.get_dept_name(dept_id)}/{perms.get_user_name(user_id)}')
    return resp_tpl('inbound.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), categories=category_pairs(),
                           units=unit_pairs(), suppliers=supplier_names(),
                           today=today(),
                           success=f'续作入库成功：{target["material_name"]} ×{qty}'
                                   f'{target["unit_name"]}，当前库存 {new_qty}')


# ================= 出库 =================
@app.route('/outbound', methods=['GET'])
@auth.need_outbound
def outbound():
    u = auth.current_user()
    return resp_tpl('outbound.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), company_depts=company_dept_names(),
                           today=today())


@app.route('/outbound', methods=['POST'])
@auth.need_outbound
def outbound_do():
    u = auth.current_user()
    f = request.form
    dept_id = f.get('dept_id', '').strip()
    user_id = f.get('user_id', '').strip()
    stock_id = f.get('stock_id', '').strip()
    recv_dept = (f.get('recv_dept') or '').strip()
    recv_person = (f.get('recv_person') or '').strip()
    apply_no = (f.get('apply_no') or '').strip()
    apply_qty = (f.get('apply_qty') or '').strip()
    actual_qty = (f.get('actual_qty') or '').strip()
    purpose = (f.get('purpose') or '').strip()
    remark = (f.get('remark') or '').strip()
    out_date = f.get('out_date') or today()

    errs = []
    if not (dept_id and user_id and stock_id and recv_dept and recv_person
            and apply_no and apply_qty and actual_qty):
        errs.append('所有带 * 的字段都必填')
    if not apply_qty.isdigit() or int(apply_qty) <= 0:
        errs.append('申请数量必须是大于 0 的整数')
    if not actual_qty.isdigit() or int(actual_qty) <= 0:
        errs.append('实际领用数量必须是大于 0 的整数')

    stock_rows = db.read('stock.csv')
    target = next((s for s in stock_rows if s['stock_id'] == stock_id), None)
    if target is None:
        errs.append('所选库存记录不存在')
    else:
        if int(actual_qty) > int(apply_qty):
            errs.append(f'实际领用数量（{actual_qty}）不能大于申请数量（{apply_qty}）')
        if int(actual_qty) > int(target['quantity']):
            errs.append(f'超出现有库存：当前库存 {target["quantity"]}'
                        f'{target["unit_name"]}，实际领用 {actual_qty}')

    if errs:
        return resp_tpl('outbound.html', user=u, menu=perms.menu(u),
                               depts=dept_pairs(), company_depts=company_dept_names(),
                               today=today(), errors=errs, form=f)

    new_qty = int(target['quantity']) - int(actual_qty)

    def _upd(r):
        if r['stock_id'] == stock_id:
            r['quantity'] = str(new_qty)
        return r

    db.update_rows('stock.csv', lambda r: r['stock_id'] == stock_id,
                   _upd, db.FIELDS['stock.csv'])

    out_rows = db.read('stock_out.csv')
    out_id = db.next_id(out_rows, 'o', field='out_id')
    db.append('stock_out.csv', dict(out_id=out_id, out_date=out_date,
                                    stock_id=target['stock_id'],
                                    material_id=target['material_id'],
                                    material_name=target['material_name'],
                                    category_name=target['category_name'],
                                    supplier_name=target['supplier_name'],
                                    unit_name=target['unit_name'],
                                    dept_id=dept_id, user_id=user_id,
                                    recv_dept_id=recv_dept, recv_person=recv_person,
                                    apply_no=apply_no, apply_qty=apply_qty,
                                    actual_qty=actual_qty, purpose=purpose,
                                    remark=remark, operator_name=u['user_name']),
              db.FIELDS['stock_out.csv'])

    auth.log_action(u, '出库',
                    f'{target["material_name"]} ×{actual_qty}{target["unit_name"]} '
                    f'→ {recv_dept}/{recv_person}')
    return resp_tpl('outbound.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), company_depts=company_dept_names(),
                           today=today(),
                           success=f'出库成功：{target["material_name"]} ×{actual_qty}'
                                   f'{target["unit_name"]}，剩余库存 {new_qty}')


# ================= 库存查询 =================
@app.route('/inventory')
@auth.need_query
def inventory():
    u = auth.current_user()
    q_dept = request.args.get('dept_id', '')
    q_user = request.args.get('user_id', '')
    q_name = (request.args.get('keyword') or '').strip()

    rows = perms.filter_rows(db.read('stock.csv'), u)
    if q_dept:
        rows = [r for r in rows if r['dept_id'] == q_dept]
    if q_user:
        rows = [r for r in rows if r['user_id'] == q_user]
    if q_name:
        rows = [r for r in rows if q_name in r['material_name']]

    for r in rows:
        r['dept_name'] = perms.get_dept_name(r['dept_id'])
        r['user_name'] = perms.get_user_name(r['user_id'])
        r['low'] = r['quantity'].isdigit() and r['safety_threshold'].isdigit() \
            and int(r['quantity']) < int(r['safety_threshold'])

    users = sorted({(r['user_id'], r.get('user_name', '')) for r in rows},
                   key=lambda x: x[1])
    return resp_tpl('inventory.html', user=u, menu=perms.menu(u),
                           rows=rows, depts=dept_pairs(), users=users,
                           q_dept=q_dept, q_user=q_user, q_name=q_name)


# ================= 出入库明细 =================
@app.route('/transactions')
@auth.need_query
def transactions():
    u = auth.current_user()
    q_type = request.args.get('type', 'all')
    q_dept = request.args.get('dept_id', '')
    q_user = request.args.get('user_id', '')
    q_from = request.args.get('from_date', '')
    q_to = request.args.get('to_date', '')
    q_name = (request.args.get('keyword') or '').strip()

    rows = []
    if q_type in ('all', 'in'):
        for r in perms.filter_rows(db.read('stock_in.csv'), u):
            r['_type'] = '入库'
            r['_date'] = r['in_date']
            r['_qty'] = r['quantity']
            r['_id'] = r['in_id']
            rows.append(r)
    if q_type in ('all', 'out'):
        for r in perms.filter_rows(db.read('stock_out.csv'), u):
            r['_type'] = '出库'
            r['_date'] = r['out_date']
            r['_qty'] = '-' + r['actual_qty'] if r['actual_qty'].isdigit() else r['actual_qty']
            r['_id'] = r['out_id']
            rows.append(r)

    if q_dept:
        rows = [r for r in rows if r.get('dept_id') == q_dept]
    if q_user:
        rows = [r for r in rows if r.get('user_id') == q_user]
    if q_from:
        rows = [r for r in rows if r['_date'] >= q_from]
    if q_to:
        rows = [r for r in rows if r['_date'] <= q_to]
    if q_name:
        rows = [r for r in rows if q_name in r.get('material_name', '')]

    rows.sort(key=lambda r: (r['_date'], r['_id']), reverse=True)
    for r in rows:
        r['dept_name'] = perms.get_dept_name(r['dept_id'])
        r['user_name'] = perms.get_user_name(r['user_id'])

    users = sorted({(r['user_id'], r.get('user_name', '')) for r in rows},
                   key=lambda x: x[1])
    return resp_tpl('transactions.html', user=u, menu=perms.menu(u),
                           rows=rows, depts=dept_pairs(), users=users,
                           q_type=q_type, q_dept=q_dept, q_user=q_user,
                           q_from=q_from, q_to=q_to, q_name=q_name,
                           bid_visible=perms.can_see_bid_price(u))


# ================= 盘点 =================
@app.route('/stocktake', methods=['GET'])
@auth.need_stocktake
def stocktake():
    u = auth.current_user()
    return resp_tpl('stocktake.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), today=today())


@app.route('/stocktake', methods=['POST'])
@auth.need_stocktake
def stocktake_do():
    u = auth.current_user()
    f = request.form
    stock_id = f.get('stock_id', '').strip()
    actual_qty = (f.get('actual_qty') or '').strip()
    take_date = f.get('take_date') or today()
    remark = (f.get('remark') or '').strip()

    errs = []
    if not (stock_id and actual_qty):
        errs.append('请先选择物料并填写实际盘点数量')
    if not actual_qty.isdigit() or int(actual_qty) < 0:
        errs.append('实际数量必须是 0 或正整数')

    target = next((s for s in db.read('stock.csv') if s['stock_id'] == stock_id), None)
    if target is None:
        errs.append('所选库存记录不存在')

    if errs:
        return resp_tpl('stocktake.html', user=u, menu=perms.menu(u),
                               depts=dept_pairs(), today=today(), errors=errs, form=f)

    book = int(target['quantity'])
    act = int(actual_qty)
    diff = act - book
    atype = '盘盈' if diff > 0 else ('盘亏' if diff < 0 else '账实相符')

    if diff != 0:
        def _upd(r):
            if r['stock_id'] == stock_id:
                r['quantity'] = str(act)
            return r
        db.update_rows('stock.csv', lambda r: r['stock_id'] == stock_id,
                       _upd, db.FIELDS['stock.csv'])

    rows = db.read('stock_take.csv')
    tid = db.next_id(rows, 't', field='take_id')
    db.append('stock_take.csv', dict(take_id=tid, take_date=take_date,
                                     stock_id=stock_id, material_name=target['material_name'],
                                     dept_id=target['dept_id'], user_id=target['user_id'],
                                     book_qty=str(book), actual_qty=str(act),
                                     diff=str(diff), adjust_type=atype,
                                     operator_name=u['user_name'], remark=remark),
              db.FIELDS['stock_take.csv'])

    auth.log_action(u, '盘点', f'{target["material_name"]} 账面{book} 实盘{act} {atype}')
    return resp_tpl('stocktake.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs(), today=today(),
                           success=f'盘点完成：{target["material_name"]} 账面 {book}、'
                                   f'实盘 {act}，{atype}')


@app.route('/api/stocktake_rows')
@auth.login_required
def api_stocktake_rows():
    """盘点记录查询（按权限过滤）"""
    u = auth.current_user()
    rows = perms.filter_rows(db.read('stock_take.csv'), u)
    rows.sort(key=lambda r: (r.get('take_date', ''), r.get('take_id', '')), reverse=True)
    for r in rows:
        r['dept_name'] = perms.get_dept_name(r['dept_id'])
        r['user_name'] = perms.get_user_name(r['user_id'])
    return jsonify(rows[:200])


# ================= 报表导出 =================
@app.route('/reports', methods=['GET'])
@auth.need_query
def reports():
    u = auth.current_user()
    return resp_tpl('reports.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs())


@app.route('/reports/export', methods=['POST'])
@auth.need_query
def reports_export():
    u = auth.current_user()
    f = request.form
    kind = f.get('kind', 'stock')
    fmt = f.get('fmt', 'csv')
    q_from = f.get('from_date', '')
    q_to = f.get('to_date', '')
    q_dept = f.get('dept_id', '')

    if kind == 'stock':
        rows = perms.filter_rows(db.read('stock.csv'), u)
        title = '库存汇总'
        header = ['部门', '人员', '大类', '物料名称', '供应商', '单位', '库存数量',
                  '安全库存阈值', '最后入库日期']
        data = []
        for r in rows:
            if q_dept and r['dept_id'] != q_dept:
                continue
            data.append([perms.get_dept_name(r['dept_id']), perms.get_user_name(r['user_id']),
                         r['category_name'], r['material_name'], r['supplier_name'],
                         r['unit_name'], r['quantity'], r['safety_threshold'],
                         r['last_in_date']])
    elif kind == 'in':
        rows = perms.filter_rows(db.read('stock_in.csv'), u)
        title = '入库明细'
        header = ['入库日期', '部门', '人员', '大类', '物料名称', '供应商', '单位',
                  '数量', '操作类型', '操作人']
        if perms.can_see_bid_price(u):
            header += ['中标时间', '中标价格']
        data = []
        for r in rows:
            if q_dept and r['dept_id'] != q_dept:
                continue
            if q_from and r['in_date'] < q_from:
                continue
            if q_to and r['in_date'] > q_to:
                continue
            line = [r['in_date'], perms.get_dept_name(r['dept_id']),
                    perms.get_user_name(r['user_id']), r['category_name'],
                    r['material_name'], r['supplier_name'], r['unit_name'],
                    r['quantity'], '新品入库' if r['operation_type'] == 'new' else '续作入库',
                    r['operator_name']]
            if perms.can_see_bid_price(u):
                line += [r.get('bid_date', ''), r.get('bid_price', '')]
            data.append(line)
    else:
        rows = perms.filter_rows(db.read('stock_out.csv'), u)
        title = '出库明细'
        header = ['出库日期', '发出部门', '发出人员', '大类', '物料名称', '单位',
                  '实际领用数量', '领用部门', '领用人', '申请单号', '申请数量',
                  '用途', '备注', '操作人']
        data = []
        for r in rows:
            if q_dept and r['dept_id'] != q_dept:
                continue
            if q_from and r['out_date'] < q_from:
                continue
            if q_to and r['out_date'] > q_to:
                continue
            data.append([r['out_date'], perms.get_dept_name(r['dept_id']),
                         perms.get_user_name(r['user_id']), r['category_name'],
                         r['material_name'], r['unit_name'], r['actual_qty'],
                         r['recv_dept_id'], r['recv_person'], r['apply_no'],
                         r['apply_qty'], r.get('purpose', ''), r.get('remark', ''),
                         r['operator_name']])

    fname = f'{title}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    if fmt == 'xlsx':
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = title
        ws.append(header)
        for line in data:
            ws.append(line)
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        return Response(buf.getvalue(),
                        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename="{fname}.xlsx"'})

    import csv as _csv
    import io as _io
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(header)
    for line in data:
        w.writerow(line)
    return Response(('﻿' + buf.getvalue()).encode('utf-8-sig'),
                    mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="{fname}.csv"'})


# ================= 表单维护（仅系统管理员） =================
FORM_TABLES = {
    'category': ('categories.csv', 'category_id', 'category_name', '大类', 'c'),
    'unit': ('units.csv', 'unit_id', 'unit_name', '计量单位', 'u'),
    'supplier': ('suppliers.csv', 'supplier_id', 'supplier_name', '供应商', 's'),
    'dept': ('departments.csv', 'dept_id', 'dept_name', '部门', 'dept_'),
}


@app.route('/forms', methods=['GET'])
@auth.need_forms_admin
def forms():
    u = auth.current_user()
    tab = request.args.get('tab', 'category')
    return resp_tpl('forms.html', user=u, menu=perms.menu(u), tab=tab)


@app.route('/api/forms/<kind>', methods=['GET'])
@auth.need_forms_admin
def api_forms_list(kind):
    if kind not in FORM_TABLES:
        abort(404)
    fname, idf, namef, label, _p = FORM_TABLES[kind]
    return jsonify(db.read(fname))


@app.route('/api/forms/<kind>', methods=['POST'])
@auth.need_forms_admin
def api_forms_add(kind):
    u = auth.current_user()
    if kind not in FORM_TABLES:
        abort(404)
    fname, idf, namef, label, prefix = FORM_TABLES[kind]
    name = (request.json.get('name') or '').strip()
    if not name:
        return jsonify(ok=False, msg=f'{label}名称不能为空')
    rows = db.read(fname)
    if any(r[namef] == name for r in rows):
        return jsonify(ok=False, msg=f'{label}「{name}」已存在')
    nid = db.next_id(rows, prefix, field=idf)
    db.append(fname, dict(**{idf: nid, namef: name}), db.FIELDS[fname])
    auth.log_action(u, '表单维护', f'新增{label}：{name}')
    return jsonify(ok=True)


@app.route('/api/forms/<kind>/<rid>', methods=['POST'])
@auth.need_forms_admin
def api_forms_edit(kind, rid):
    u = auth.current_user()
    if kind not in FORM_TABLES:
        abort(404)
    fname, idf, namef, label, _p = FORM_TABLES[kind]
    name = (request.json.get('name') or '').strip()
    if not name:
        return jsonify(ok=False, msg=f'{label}名称不能为空')
    rows = db.read(fname)
    if any(r[namef] == name and r[idf] != rid for r in rows):
        return jsonify(ok=False, msg=f'{label}「{name}」已存在')

    def _upd(r):
        if r[idf] == rid:
            r[namef] = name
        return r

    db.update_rows(fname, lambda r: r[idf] == rid, _upd, db.FIELDS[fname])
    auth.log_action(u, '表单维护', f'修改{label}：{rid} → {name}')
    return jsonify(ok=True)


@app.route('/api/forms/<kind>/<rid>/check_delete')
@auth.need_forms_admin
def api_forms_check_delete(kind, rid):
    """删除前校验是否被引用"""
    if kind not in FORM_TABLES:
        abort(404)
    fname, idf, namef, label, _p = FORM_TABLES[kind]
    row = next((r for r in db.read(fname) if r[idf] == rid), None)
    if row is None:
        return jsonify(ok=False, msg='记录不存在')
    name = row[namef]
    refs = []
    if kind == 'category':
        refs = [m['material_name'] for m in db.read('materials.csv') if m['category_id'] == rid]
    elif kind == 'unit':
        refs = [m['material_name'] for m in db.read('materials.csv') if m['unit_id'] == rid]
    elif kind == 'supplier':
        refs = [s['material_name'] for s in db.read('stock.csv') if s['supplier_name'] == name]
    elif kind == 'dept':
        refs = [f"{perms.get_user_name(x['user_id'])}" for x in db.read('stock.csv')
                if x['dept_id'] == rid]
        users = [x['user_name'] for x in db.read('users.csv') if rid in x['dept_ids'].split(';')]
        refs = (refs + users)[:20]
    if refs:
        return jsonify(ok=False,
                       msg=f'「{name}」已被 {len(refs)} 处引用（如：{refs[0]}），不能删除')
    return jsonify(ok=True)


@app.route('/api/forms/<kind>/<rid>/delete', methods=['POST'])
@auth.need_forms_admin
def api_forms_delete(kind, rid):
    u = auth.current_user()
    if kind not in FORM_TABLES:
        abort(404)
    fname, idf, namef, label, _p = FORM_TABLES[kind]
    db.update_rows(fname, lambda r: r[idf] == rid, lambda r: None, db.FIELDS[fname])
    auth.log_action(u, '表单维护', f'删除{label}：{rid}')
    return jsonify(ok=True)


# ================= 用户管理（仅系统管理员） =================
@app.route('/users', methods=['GET'])
@auth.need_user_admin
def users():
    u = auth.current_user()
    return resp_tpl('users.html', user=u, menu=perms.menu(u),
                           depts=dept_pairs())


@app.route('/api/users', methods=['GET'])
@auth.need_user_admin
def api_users_list():
    rows = db.read('users.csv')
    for r in rows:
        r['dept_names'] = '、'.join(perms.get_dept_name(d) for d in r['dept_ids'].split(';') if d)
        r['role_name'] = perms.ROLE_NAMES.get(r['role'], r['role'])
        r['managed_depts'] = sorted(perms.get_manager_depts(r['user_id']))
    return jsonify(rows)


@app.route('/api/users', methods=['POST'])
@auth.need_user_admin
def api_users_add():
    u = auth.current_user()
    j = request.json
    name = (j.get('user_name') or '').strip()
    role = j.get('role', 'member')
    dept_ids = j.get('dept_ids') or []
    if not name:
        return jsonify(ok=False, msg='用户名不能为空')
    if perms.get_user_by_name(name):
        return jsonify(ok=False, msg=f'用户名「{name}」已存在')
    if role not in perms.ROLE_NAMES:
        return jsonify(ok=False, msg='角色非法')

    # 按角色派生默认权限
    cin = '1' if role in ('sys_admin', 'brand') else '0'
    cout = '1' if role in ('sys_admin', 'warehouse') else '0'

    rows = db.read('users.csv')
    uid = db.next_id(rows, 'u', field='user_id')
    db.append('users.csv', dict(user_id=uid, user_name=name, password='123456',
                                role=role, dept_ids=';'.join(dept_ids),
                                can_inbound=cin, can_outbound=cout, can_query='1',
                                force_change_password='1'),
              db.FIELDS['users.csv'])
    auth.log_action(u, '新增用户', f'{name}（{perms.ROLE_NAMES[role]}）')
    return jsonify(ok=True)


@app.route('/api/users/<uid>', methods=['POST'])
@auth.need_user_admin
def api_users_edit(uid):
    u = auth.current_user()
    j = request.json
    target = perms.get_user_by_id(uid)
    if target is None:
        return jsonify(ok=False, msg='用户不存在')
    if target['role'] == 'sys_admin':
        return jsonify(ok=False, msg='系统管理员不可被修改')

    role = j.get('role') or target['role']
    dept_ids = j.get('dept_ids')
    cin = j.get('can_inbound')
    cout = j.get('can_outbound')

    def _upd(r):
        if r['user_id'] == uid:
            if role and role in perms.ROLE_NAMES:
                r['role'] = role
            if isinstance(dept_ids, list):
                r['dept_ids'] = ';'.join(dept_ids)
            if cin in ('0', '1'):
                r['can_inbound'] = cin
            if cout in ('0', '1'):
                r['can_outbound'] = cout
        return r

    db.update_rows('users.csv', lambda r: r['user_id'] == uid,
                   _upd, db.FIELDS['users.csv'])
    auth.log_action(u, '修改用户', f'{target["user_name"]}')
    return jsonify(ok=True)


@app.route('/api/users/<uid>/reset_pwd', methods=['POST'])
@auth.need_user_admin
def api_users_reset_pwd(uid):
    u = auth.current_user()
    target = perms.get_user_by_id(uid)
    if target is None:
        return jsonify(ok=False, msg='用户不存在')
    if target['role'] == 'sys_admin':
        return jsonify(ok=False, msg='系统管理员密码不可被重置')

    def _upd(r):
        if r['user_id'] == uid:
            r['password'] = '123456'
            r['force_change_password'] = '1'
        return r

    db.update_rows('users.csv', lambda r: r['user_id'] == uid,
                   _upd, db.FIELDS['users.csv'])
    auth.log_action(u, '重置密码', target['user_name'])
    return jsonify(ok=True, msg='已重置为 123456，该用户下次登录需强制改密')


@app.route('/api/users/<uid>/delete', methods=['POST'])
@auth.need_user_admin
def api_users_delete(uid):
    u = auth.current_user()
    target = perms.get_user_by_id(uid)
    if target is None:
        return jsonify(ok=False, msg='用户不存在')
    if target['role'] == 'sys_admin':
        return jsonify(ok=False, msg='系统管理员不可被删除')
    has_stock = any(s['user_id'] == uid for s in db.read('stock.csv'))
    if has_stock:
        return jsonify(ok=False, msg=f'{target["user_name"]} 名下仍有库存记录，不能删除')

    db.update_rows('users.csv', lambda r: r['user_id'] == uid,
                   lambda r: None, db.FIELDS['users.csv'])
    db.update_rows('dept_managers.csv', lambda r: r['manager_user_id'] == uid,
                   lambda r: None, db.FIELDS['dept_managers.csv'])
    auth.log_action(u, '删除用户', target['user_name'])
    return jsonify(ok=True)


@app.route('/api/users/<uid>/managed_depts', methods=['POST'])
@auth.need_user_admin
def api_users_managed_depts(uid):
    u = auth.current_user()
    target = perms.get_user_by_id(uid)
    if target is None:
        return jsonify(ok=False, msg='用户不存在')
    if target['role'] != 'manager':
        return jsonify(ok=False, msg='仅部长角色需要配置分管部门')
    depts = request.json.get('dept_ids') or []

    db.update_rows('dept_managers.csv', lambda r: r['manager_user_id'] == uid,
                   lambda r: None, db.FIELDS['dept_managers.csv'])
    for d in depts:
        db.append('dept_managers.csv', dict(manager_user_id=uid, dept_id=d),
                  db.FIELDS['dept_managers.csv'], do_backup=False)
    auth.log_action(u, '配置分管部门',
                    f'{target["user_name"]} → {"、".join(perms.get_dept_name(d) for d in depts)}')
    return jsonify(ok=True)


# ================= 操作日志 =================
@app.route('/logs')
@auth.login_required
def logs():
    u = auth.current_user()
    rows = db.read('operation_logs.csv')
    rows.sort(key=lambda r: r.get('log_time', ''), reverse=True)
    return resp_tpl('logs.html', user=u, menu=perms.menu(u),
                           rows=rows[:500])


# ================= 手机版路由（/m 前缀，页面与逻辑完全复用 PC 版处理器） =================
@app.route('/m/')
def m_index():
    return index()


@app.route('/m/login', methods=['GET', 'POST'])
def m_login():
    return login_page()


@app.route('/m/change_password', methods=['GET', 'POST'])
def m_change_password():
    return change_password()


@app.route('/m/inbound')
def m_inbound():
    return inbound()


@app.route('/m/outbound')
def m_outbound():
    return outbound()


@app.route('/m/inventory')
def m_inventory():
    return inventory()


@app.route('/m/transactions')
def m_transactions():
    return transactions()


@app.route('/m/stocktake', methods=['GET'])
def m_stocktake():
    return stocktake()


@app.route('/m/reports')
def m_reports():
    return reports_page()


@app.route('/m/forms')
def m_forms():
    return forms()


@app.route('/m/users')
def m_users():
    return users()


@app.route('/m/logs')
def m_logs():
    return logs()


@app.route('/m/profile')
@auth.login_required
def m_profile():
    u = auth.current_user()
    return render_template('mobile/profile.html', user=u, menu=perms.menu(u))


# ================= 错误处理 =================
@app.errorhandler(403)
def forbidden(e):
    return resp_tpl('error.html', code=403, user=auth.current_user(),
                   msg='你没有该功能的操作权限'), 403


@app.errorhandler(404)
def not_found(e):
    return resp_tpl('error.html', code=404, user=auth.current_user(),
                   msg='页面不存在'), 404

if __name__ == '__main__':
    app.run(host=HOST, port=PORT, debug=DEBUG, threaded=True)

