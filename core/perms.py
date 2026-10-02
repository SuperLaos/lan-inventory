# -*- coding: utf-8 -*-
"""权限矩阵与数据范围计算"""
import core.db as db

# 角色中文名
ROLE_NAMES = {
    'sys_admin': '系统管理员',
    'warehouse': '仓库管理员',
    'brand': '品牌经理',
    'director': '总监',
    'deputy': '副总监',
    'manager': '部长',
    'member': '成员',
}

# 可见中标价的角色
BID_PRICE_ROLES = {'sys_admin', 'director', 'deputy', 'brand'}

# 全局角色（查询全部 7 部门）
GLOBAL_ROLES = {'sys_admin', 'warehouse', 'brand', 'director', 'deputy'}

ROLE_ORDER = ['sys_admin', 'director', 'deputy', 'warehouse', 'brand',
              'manager', 'member']


def get_user_by_name(name):
    for u in db.read('users.csv'):
        if u['user_name'] == name:
            return u
    return None


def get_user_by_id(uid):
    for u in db.read('users.csv'):
        if u['user_id'] == uid:
            return u
    return None


def get_user_name(uid):
    u = get_user_by_id(uid)
    return u['user_name'] if u else ''


def get_dept_name(dept_id):
    for d in db.read('departments.csv'):
        if d['dept_id'] == dept_id:
            return d['dept_name']
    return ''


def get_manager_depts(uid):
    """部长的分管部门集合"""
    return {m['dept_id'] for m in db.read('dept_managers.csv')
            if m['manager_user_id'] == uid}


def my_dept_ids(user):
    return [d for d in (user.get('dept_ids') or '').split(';') if d]


def visible_dept_ids(user):
    """该用户可见的部门集合"""
    role = user['role']
    if role in GLOBAL_ROLES:
        return {d['dept_id'] for d in db.read('departments.csv')}
    if role == 'manager':
        return get_manager_depts(user['user_id']) | set(my_dept_ids(user))
    # 成员：仅本人所属部门
    return set(my_dept_ids(user))


def visible_user_ids(user):
    """该用户可见的人员 ID 集合（None 表示不限）"""
    role = user['role']
    if role in GLOBAL_ROLES:
        return None  # 全部
    if role == 'manager':
        depts = visible_dept_ids(user)
        return {u['user_id'] for u in db.read('users.csv')
                if set(my_dept_ids(u)) & depts}
    return {user['user_id']}


def can_query(user):
    return user.get('can_query') == '1'


def can_inbound(user):
    return user.get('can_inbound') == '1'


def can_outbound(user):
    return user.get('can_outbound') == '1'


def can_see_bid_price(user):
    return user['role'] in BID_PRICE_ROLES


def is_sys_admin(user):
    return user['role'] == 'sys_admin'


def can_manage_users(user):
    return is_sys_admin(user)


def can_manage_forms(user):
    return is_sys_admin(user)


def can_stocktake(user):
    return user['role'] in ('sys_admin', 'warehouse')


def filter_rows(rows, user, dept_field='dept_id', user_field='user_id'):
    """按可见范围过滤库存/流水行"""
    role = user['role']
    if role in GLOBAL_ROLES:
        return rows
    if role == 'manager':
        depts = visible_dept_ids(user['user_id']) if isinstance(user, str) else visible_dept_ids(user)
        return [r for r in rows if r.get(dept_field) in depts]
    return [r for r in rows if r.get(user_field) == user['user_id']]


def menu(user):
    """生成侧边菜单（按权限显隐）"""
    items = [('index', '首页', True),
             ('inbound', '入库', can_inbound(user)),
             ('outbound', '出库', can_outbound(user)),
             ('inventory', '库存查询', can_query(user)),
             ('transactions', '出入库明细', can_query(user)),
             ('stocktake', '盘点', can_stocktake(user)),
             ('reports', '报表导出', can_query(user)),
             ('forms', '表单维护', can_manage_forms(user)),
             ('users', '用户管理', can_manage_users(user)),
             ('logs', '操作日志', is_sys_admin(user))]
    return [it for it in items if it[2]]


# 移动端 UA 特征（含微信内置浏览器、HarmonyOS）
MOBILE_UA_KEYS = ['mobile', 'iphone', 'android', 'ipad', 'windows phone',
                  'micromessenger', 'harmonyos', 'opera mini']


def is_mobile(req):
    """根据 User-Agent 判断是否手机访问"""
    ua = (req.headers.get('User-Agent') or '').lower()
    return any(k in ua for k in MOBILE_UA_KEYS)
