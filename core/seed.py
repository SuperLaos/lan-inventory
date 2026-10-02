# -*- coding: utf-8 -*-
"""种子数据：首次运行初始化全部 CSV"""
import os
import core.db as db

DEPTS = [('dept_a', '部门A'), ('dept_b', '部门B'), ('dept_c', '部门C'),
         ('dept_d', '部门D'), ('dept_e', '部门E'), ('dept_f', '部门F'),
         ('dept_g', '部门G')]

CATEGORIES = ['本册纸品', '家具茶具', '数码电子', '日用家纺', '防护用品',
              '印刷宣传品', '小家电', '书写工具', '杯壶水具']

UNITS = ['个', '套', '包', '张', '支', '箱']

SUPPLIERS = ['供应商A', '供应商B', '供应商C']

# (user_name, role, dept_ids, can_inbound, can_outbound)
USERS = [
    ('系统管理员', 'sys_admin', 'dept_a', 1, 1),
    ('仓库管理员', 'warehouse', 'dept_a', 0, 1),
    ('品牌经理', 'brand', 'dept_a', 1, 0),
    ('总监', 'director', 'dept_a', 0, 0),
    ('副总监', 'deputy', 'dept_g', 0, 0),
    ('部长A', 'manager', 'dept_a', 0, 0),
    ('部长B', 'manager', 'dept_b', 0, 0),
    ('部长C', 'manager', 'dept_c', 0, 0),
    ('部长D', 'manager', 'dept_d', 0, 0),
    ('部长E', 'manager', 'dept_e', 0, 0),
]

# 部长分管部门（部长A→部门A … 部长E→部门E/F，副总监→部门G）
MANAGER_DEPTS = [
    ('u006', 'dept_a'), ('u007', 'dept_b'), ('u008', 'dept_c'),
    ('u009', 'dept_d'), ('u010', 'dept_e'), ('u010', 'dept_f'),
    ('u005', 'dept_g'),
]


def seed():
    if os.path.exists(db.csv_path('users.csv')):
        return False  # 已初始化

    db.write('departments.csv',
             [dict(zip(['dept_id', 'dept_name'], d)) for d in DEPTS],
             db.FIELDS['departments.csv'], do_backup=False)

    # 全公司部门表：7 个部门 + 常见兄弟部门，供「领用部门」下拉选择
    company = [dict(dept_id=d[0], dept_name=d[1]) for d in DEPTS]
    for i, name in enumerate(['销售部', '采购部', '财务部', '人力资源部', '综合办公室']):
        company.append(dict(dept_id=f'ext_{i+1}', dept_name=name))
    db.write('company_depts.csv', company, db.FIELDS['company_depts.csv'], do_backup=False)

    db.write('categories.csv',
             [dict(category_id=f'c{i+1:03d}', category_name=n) for i, n in enumerate(CATEGORIES)],
             db.FIELDS['categories.csv'], do_backup=False)

    db.write('units.csv',
             [dict(unit_id=f'u{i+1:03d}', unit_name=n) for i, n in enumerate(UNITS)],
             db.FIELDS['units.csv'], do_backup=False)

    db.write('suppliers.csv',
             [dict(supplier_id=f's{i+1:03d}', supplier_name=n) for i, n in enumerate(SUPPLIERS)],
             db.FIELDS['suppliers.csv'], do_backup=False)

    users = []
    for i, (name, role, dept, cin, cout) in enumerate(USERS, start=1):
        users.append(dict(
            user_id=f'u{i:03d}', user_name=name, password='123456', role=role,
            dept_ids=dept, can_inbound=cin, can_outbound=cout, can_query=1,
            force_change_password=1))
    db.write('users.csv', users, db.FIELDS['users.csv'], do_backup=False)

    db.write('dept_managers.csv',
             [dict(manager_user_id=m, dept_id=d) for m, d in MANAGER_DEPTS],
             db.FIELDS['dept_managers.csv'], do_backup=False)

    # 其余表建空表（只有表头）
    for name in ['materials.csv', 'stock.csv', 'stock_in.csv', 'stock_out.csv',
                 'stock_take.csv', 'operation_logs.csv']:
        db.write(name, [], db.FIELDS[name], do_backup=False)
    return True


if __name__ == '__main__':
    if seed():
        print('种子数据初始化完成')
    else:
        print('已存在数据，跳过初始化')
    for f in os.listdir(db.DATA_DIR):
        if f.endswith('.csv'):
            print(' -', f, len(db.read(f)), '行')
