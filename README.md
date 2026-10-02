# lan-inventory · 市场管理中心 · 物料仓库进销存系统 | LAN Inventory — Material Warehouse System

[中文](#中文) | [English](#english)

本地化进销存系统：Python Flask + HTML + 本地 CSV 数据源，局域网固定 IP 多人访问，自带手机版（自动识别设备切换界面）。

LAN Inventory — a localized inventory management system: Python Flask + HTML + local CSV data sources, accessed by multiple users over a LAN via fixed IP, with a built-in mobile version (auto device detection and UI switching).

---

## 中文

### 快速启动

1. 双击 `start.bat`（自动启动服务并打开浏览器）
2. 客户端浏览器访问 `http://<服务器IP>:5000`

> 首次启动会自动初始化全部 CSV 数据（仅在数据文件不存在时执行）。

### 服务器配置

所有配置在 `config.ini`，改完重启 `start.bat` 生效：

```ini
[server]
host = 0.0.0.0    # 监听地址，0.0.0.0 = 允许局域网访问
port = 5000       # 端口号

[session]
timeout_minutes = 60   # 会话超时（分钟）

[backup]
keep_days = 30         # 自动备份保留天数
```

**部署到服务器**：把整个文件夹拷到服务器机器 → 确认机器是固定 IP → 修改 `config.ini` 的 port（如需）→ 把 `start.bat` 的快捷方式放到「启动」文件夹实现开机自启 → 客户端浏览器收藏 `http://<IP>:<端口>`。

### 初始账号（测试期）

| 用户名 | 角色 | 初始密码 |
|---|---|---|
| 系统管理员 | 系统管理员（内置锁定） | 123456 |
| 仓库管理员 | 仓库管理员 | 123456 |
| 品牌经理 | 品牌经理 | 123456 |
| 总监 | 总监 | 123456 |
| 副总监 | 副总监（兼部门G） | 123456 |
| 部长A~E | 部长 | 123456 |

**所有账号首次登录强制改密。** 部门暂用「部门A~G」测试名，部长分管：A→部门A、B→部门B、C→部门C、D→部门D、E→部门E+F、副总监→部门G。

### 权限速查

| 角色 | 查询范围 | 入库 | 出库 | 中标价 | 用户/表单管理 |
|---|---|---|---|---|---|
| 系统管理员 | 全部 | ✔ | ✔ | ✔ | ✔（自身锁定不可改） |
| 总监 / 副总监 | 全部 | ✘ | ✘ | ✔ | ✘ |
| 品牌经理 | 全部 | ✔ | ✘ | ✔ | ✘ |
| 仓库管理员 | 全部 | ✘ | ✔ | ✘ | ✘ |
| 部长 | 分管部门∪所属部门 | ✘ | ✘ | ✘ | ✘ |
| 成员 | 仅本人 | ✘ | ✘ | ✘ | ✘ |

### 数据文件（data/）

| 文件 | 内容 |
|---|---|
| departments.csv | 部门（部门A~G） |
| company_depts.csv | 全公司部门（领用部门下拉用，含销售部等） |
| users.csv | 用户（角色、所属部门、权限标记） |
| dept_managers.csv | 部长分管部门映射 |
| categories.csv / units.csv / suppliers.csv | 大类 / 计量单位 / 供应商 |
| materials.csv | 物料字典（新品入库自动积累） |
| stock.csv | 库存主表（唯一键：物料+部门+人员） |
| stock_in.csv / stock_out.csv | 入库 / 出库流水 |
| stock_take.csv | 盘点流水 |
| operation_logs.csv | 操作日志 |

所有 CSV 为 **UTF-8-BOM** 编码，Excel 双击打开中文不乱码。每次写操作前自动备份到 `backups/YYYYMMDD/HHMMSS_文件名`。

⚠️ **业务表（stock / stock_in / stock_out / users）不要直接改 CSV**，必须走系统功能，否则会账实不符。字典表（大类/单位/供应商/部门）可在「表单维护」页维护。

### 安全说明

- 所有页面由 Flask 后端渲染，未登录访问任何 URL 自动跳登录页
- 每个页面的数据都按当前登录人的权限范围过滤
- 会话超时自动登出
- 中标价格列在查询/导出时按角色动态显隐

> ⚠️ **内网设计说明**：密码以明文存储（`users.csv`），面向纯内网、互信环境设计。若部署到公网，请自行改为哈希存储并启用 HTTPS。

### 目录结构

```
进销存/
├── app.py              # 主程序（全部路由与业务逻辑）
├── config.ini          # 配置
├── start.bat           # 启动脚本
├── requirements.txt    # 依赖
├── core/
│   ├── db.py           # CSV 读写 + 文件锁 + 原子写 + 自动备份
│   ├── auth.py         # 登录 / session / 权限装饰器 / 日志
│   ├── perms.py        # 权限矩阵与数据范围计算 + 设备识别
│   └── seed.py         # 初始数据播种
├── data/               # CSV 数据源
├── backups/            # 自动备份
├── templates/          # 14 个 PC 页面 + mobile/ 下 15 个手机页面
└── static/             # 预留
```

### 常见问题

**Q：换台机器怎么迁移？** 拷贝整个文件夹即可（含 venv 和 data）。

**Q：数据想改真实部门名？** 系统管理员登录 → 表单维护 → 部门 → 修改。用户所属部门在「用户管理」里改。

**Q：忘记密码？** 系统管理员在「用户管理」里点「重置密码」，被重置者下次登录强制改密。系统管理员密码忘了只能改 `data/users.csv` 里 u001 那一行的 password 字段。

### 手机版

**访问方式**：手机连公司局域网 WiFi，浏览器输入与 PC 相同的网址 `http://<服务器IP>:5000`，系统**自动识别手机并切换到手机版**（无需输不同网址）。PC 访问手机版地址会自动跳回电脑版。支持 iPhone / Android / iPad / 微信内置浏览器 / HarmonyOS。

**界面结构**：
- **底部标签栏**：首页 / 入库 / 出库 / 查询 / 我的（入库、出库按权限显隐）
- **首页**：今日入库/出库笔数 + 库存预警（飘红卡片）
- **入库**：新品（5 步向导）、续作（3 步向导）
- **出库**：5 步向导（选部门人员 → 选物料 → 领用信息 → 数量 → 确认）
- **查询**：库存查询 + 出入库明细（卡片列表）
- **我的**：修改密码、盘点、报表导出、表单维护、用户管理、操作日志（按权限显隐）

**与 PC 版的关系**：手机版与 PC 版**共用同一套后端**（数据、权限、校验逻辑完全一致），只是界面不同。在手机上的所有操作，PC 版实时可见，反之亦然；所有拦截规则（超库存、超申请量、重复入库、权限隔离、中标价隐藏）在手机端同样生效。表单输入数字时自动调起数字键盘。

**注意事项**：
- **微信内打开**：若报表下载被拦截，点右上角「…」→「在浏览器中打开」
- 手机版不需要单独配置，`config.ini` 里的服务器 IP 同样适用

---

## English

### Quick Start

1. Double-click `start.bat` (starts the server and opens the browser)
2. Open `http://<server-IP>:5000` in any browser on a client machine

> On first launch, all CSV data files are initialized automatically (only if they do not already exist).

### Server Configuration

All settings live in `config.ini`; restart `start.bat` after changing:

```ini
[server]
host = 0.0.0.0    # Listen address; 0.0.0.0 = allow LAN access
port = 5000       # Port number

[session]
timeout_minutes = 60   # Session timeout (minutes)

[backup]
keep_days = 30         # Days to keep automatic backups
```

**Deploying to a server**: copy the whole folder to the server machine → make sure it has a fixed IP → change `port` in `config.ini` if needed → put a shortcut to `start.bat` in the Windows Startup folder for auto-start → bookmark `http://<IP>:<port>` on client browsers.

### Initial Accounts (Test Phase)

| Username | Role | Initial Password |
|---|---|---|
| 系统管理员 (System Admin) | System Admin (built-in, locked) | 123456 |
| 仓库管理员 (Warehouse Admin) | Warehouse Admin | 123456 |
| 品牌经理 (Brand Manager) | Brand Manager | 123456 |
| 总监 (Director) | Director | 123456 |
| 副总监 (Deputy Director) | Deputy Director (also Dept. G) | 123456 |
| 部长A~E (Minister A–E) | Minister | 123456 |

**All accounts are forced to change password on first login.** Departments use test names "部门A~G". Minister assignments: A→Dept A, B→Dept B, C→Dept C, D→Dept D, E→Dept E+F, Deputy Director→Dept G.

### Permission Quick Reference

| Role | Query Scope | Inbound | Outbound | Bid Price | User/Form Admin |
|---|---|---|---|---|---|
| System Admin | All | ✔ | ✔ | ✔ | ✔ (own account locked) |
| Director / Deputy Director | All | ✘ | ✘ | ✔ | ✘ |
| Brand Manager | All | ✔ | ✘ | ✔ | ✘ |
| Warehouse Admin | All | ✘ | ✔ | ✘ | ✘ |
| Minister | Managed + own depts | ✘ | ✘ | ✘ | ✘ |
| Member | Own records only | ✘ | ✘ | ✘ | ✘ |

### Data Files (data/)

| File | Contents |
|---|---|
| departments.csv | Departments (部门A~G) |
| company_depts.csv | Company-wide departments (dropdown for receiving dept., incl. Sales) |
| users.csv | Users (role, department, permission flags) |
| dept_managers.csv | Minister → managed departments mapping |
| categories.csv / units.csv / suppliers.csv | Categories / units of measure / suppliers |
| materials.csv | Material dictionary (grows as new items are inbound) |
| stock.csv | Main stock table (unique key: material + dept + person) |
| stock_in.csv / stock_out.csv | Inbound / outbound transaction logs |
| stock_take.csv | Stocktake logs |
| operation_logs.csv | Operation logs |

All CSV files are **UTF-8-BOM** encoded so Excel opens Chinese text without garbling. Every write is backed up to `backups/YYYYMMDD/HHMMSS_filename` before it is applied.

⚠️ **Never edit business tables (stock / stock_in / stock_out / users) directly in the CSV files** — always use the system's own features, otherwise bookkeeping and physical stock will diverge. Dictionary tables (category / unit / supplier / department) can be maintained via the "Form Maintenance" page.

### Security Notes

- All pages are server-rendered by Flask; any unauthenticated URL access redirects to the login page
- Data on every page is filtered by the logged-in user's permission scope
- Sessions expire and log out automatically
- The bid-price column is shown/hidden dynamically by role in queries and exports

> ⚠️ **Intranet design note**: passwords are stored in plaintext (`users.csv`), intended for a trusted, closed LAN only. If you deploy this on the public internet, switch to hashed password storage and enable HTTPS first.

### Directory Structure

```
inventory/
├── app.py              # Main app (all routes and business logic)
├── config.ini          # Configuration
├── start.bat           # Launcher script
├── requirements.txt    # Dependencies
├── core/
│   ├── db.py           # CSV I/O + file locking + atomic writes + auto backup
│   ├── auth.py         # Login / session / permission decorators / logging
│   ├── perms.py        # Permission matrix, data scoping, device detection
│   └── seed.py         # Initial data seeding
├── data/               # CSV data source
├── backups/            # Automatic backups
├── templates/          # 14 PC pages + mobile/ with 15 mobile pages
└── static/             # Reserved
```

### FAQ

**Q: How do I migrate to another machine?** Just copy the entire folder (venv and data included).

**Q: Can I rename departments to real names?** Log in as System Admin → Form Maintenance → Departments → Edit. A user's department is changed under "User Management".

**Q: What if someone forgets a password?** System Admin clicks "Reset Password" in User Management; the affected user is then forced to change it at next login. If the System Admin password is lost, the only option is to edit the `password` field of row `u001` in `data/users.csv`.

### Mobile Version

**How to access**: connect the phone to the company LAN Wi-Fi, open the same URL `http://<server-IP>:5000` in the browser — the system **auto-detects the phone and switches to the mobile UI** (no separate URL needed). PCs visiting the mobile URL are redirected back to the desktop version. Supports iPhone / Android / iPad / WeChat in-app browser / HarmonyOS.

**UI structure**:
- **Bottom tab bar**: Home / Inbound / Outbound / Query / Profile (Inbound/Outbound tabs are shown per permission)
- **Home**: today's inbound/outbound counts + low-stock warnings (red cards)
- **Inbound**: new-item wizard (5 steps) / restock wizard (3 steps)
- **Outbound**: 5-step wizard (dept+person → material → requisition info → quantity → confirm)
- **Query**: stock inventory + in/out transaction history (card lists)
- **Profile**: change password, stocktake, report export, form maintenance, user management, operation logs (shown per permission)

**Relation to the PC version**: mobile and PC versions **share the same backend** (data, permissions, and validation logic are identical) — only the UI differs. Everything done on a phone is instantly visible on PCs and vice versa; all blocking rules (over-stock, over-requisition, duplicate inbound, permission isolation, bid-price hiding) apply equally on mobile. Numeric fields automatically bring up a numeric keypad.

**Notes**:
- **Opening inside WeChat**: if a report download is blocked, tap "…" at the top right → "Open in browser"
- No separate configuration is needed for the mobile version; the server IP in `config.ini` applies to both
