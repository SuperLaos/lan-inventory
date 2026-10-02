# -*- coding: utf-8 -*-
"""CSV 数据访问层：文件锁 + 原子写 + 写前自动备份"""
import csv
import io
import os
import shutil
import glob
import configparser
from datetime import datetime
from filelock import FileLock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUP_DIR = os.path.join(BASE_DIR, 'backups')
LOCK_DIR = os.path.join(BASE_DIR, 'data', '.locks')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOCK_DIR, exist_ok=True)

# 读取配置
_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(BASE_DIR, 'config.ini'), encoding='utf-8')
KEEP_DAYS = int(_cfg.get('backup', 'keep_days', fallback='30'))


def _lock_path(name):
    return os.path.join(LOCK_DIR, name + '.lock')


def csv_path(name):
    return os.path.join(DATA_DIR, name)


def _backup(name):
    """写操作前备份；清理过期备份"""
    src = csv_path(name)
    if not os.path.exists(src):
        return
    day = datetime.now().strftime('%Y%m%d')
    ts = datetime.now().strftime('%H%M%S')
    bdir = os.path.join(BACKUP_DIR, day)
    os.makedirs(bdir, exist_ok=True)
    dst = os.path.join(bdir, f'{ts}_{name}')
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
    # 清理过期备份
    cutoff = datetime.now().timestamp() - KEEP_DAYS * 86400
    for old in glob.glob(os.path.join(BACKUP_DIR, '*', '*')):
        try:
            if os.path.getmtime(old) < cutoff:
                os.remove(old)
                # 顺手清空目录
                d = os.path.dirname(old)
                if os.path.isdir(d) and not os.listdir(d):
                    os.rmdir(d)
        except OSError:
            pass


def read(name):
    """读取 CSV -> list[dict]。文件不存在返回 []"""
    path = csv_path(name)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows, fieldnames=None, do_backup=True):
    """整表写入（文件锁 + 原子写）。rows: list[dict]"""
    with FileLock(_lock_path(name)):
        if do_backup:
            _backup(name)
        if fieldnames is None:
            fieldnames = list(rows[0].keys()) if rows else []
        tmp = csv_path(name) + '.tmp'
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow(r)
        with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(buf.getvalue())
        os.replace(tmp, csv_path(name))


def append(name, row, fieldnames, do_backup=True):
    """追加一行"""
    with FileLock(_lock_path(name)):
        if do_backup:
            _backup(name)
        tmp = csv_path(name) + '.tmp'
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        if os.path.exists(csv_path(name)):
            with open(csv_path(name), 'r', encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    w.writerow(r)
        w.writerow(row)
        with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(buf.getvalue())
        os.replace(tmp, csv_path(name))


def update_rows(name, match, mutator, fieldnames, do_backup=True):
    """匹配行并修改。match: fn(row)->bool；mutator: fn(row)->row（返回 None 表示删除该行）"""
    with FileLock(_lock_path(name)):
        if do_backup:
            _backup(name)
        rows = read(name)
        out = []
        for r in rows:
            if match(r):
                nr = mutator(r)
                if nr is not None:
                    out.append(nr)
            else:
                out.append(r)
        tmp = csv_path(name) + '.tmp'
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
        w.writeheader()
        for r in out:
            w.writerow(r)
        with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
            f.write(buf.getvalue())
        os.replace(tmp, csv_path(name))


def next_id(rows, prefix, field='id'):
    """生成自增 ID：prefix + 4 位补零"""
    max_n = 0
    for r in rows:
        v = r.get(field, '') or ''
        if v.startswith(prefix):
            try:
                max_n = max(max_n, int(v[len(prefix):]))
            except ValueError:
                pass
    return f'{prefix}{max_n + 1:04d}'


# 各表的字段定义（统一管理，避免表头错乱）
FIELDS = {
    'departments.csv': ['dept_id', 'dept_name'],
    'company_depts.csv': ['dept_id', 'dept_name'],
    'users.csv': ['user_id', 'user_name', 'password', 'role', 'dept_ids',
                  'can_inbound', 'can_outbound', 'can_query', 'force_change_password'],
    'dept_managers.csv': ['manager_user_id', 'dept_id'],
    'categories.csv': ['category_id', 'category_name'],
    'units.csv': ['unit_id', 'unit_name'],
    'suppliers.csv': ['supplier_id', 'supplier_name'],
    'materials.csv': ['material_id', 'category_id', 'material_name', 'unit_id'],
    'stock.csv': ['stock_id', 'material_id', 'category_name', 'material_name', 'supplier_name',
                  'unit_name', 'dept_id', 'user_id', 'quantity', 'safety_threshold', 'last_in_date'],
    'stock_in.csv': ['in_id', 'in_date', 'stock_id', 'material_id', 'material_name', 'category_name',
                     'supplier_name', 'unit_name', 'dept_id', 'user_id', 'quantity', 'safety_threshold',
                     'operation_type', 'bid_date', 'bid_price', 'operator_name'],
    'stock_out.csv': ['out_id', 'out_date', 'stock_id', 'material_id', 'material_name', 'category_name',
                      'supplier_name', 'unit_name', 'dept_id', 'user_id', 'recv_dept_id', 'recv_person',
                      'apply_no', 'apply_qty', 'actual_qty', 'purpose', 'remark', 'operator_name'],
    'stock_take.csv': ['take_id', 'take_date', 'stock_id', 'material_name', 'dept_id', 'user_id',
                       'book_qty', 'actual_qty', 'diff', 'adjust_type', 'operator_name', 'remark'],
    'operation_logs.csv': ['log_id', 'log_time', 'user_name', 'action', 'detail', 'ip'],
}
