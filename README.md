# Futures Ranking

基于 WT8 信号明细的期货排序平台。当前已接入 **纯价格涨跌幅**、**1 小时 K 线涨幅（Long & Hold）**、**1 小时 SAR 多头**、**1 小时 MACD 多头**，分别从 `data/小时Buy_And_Hold/`、`data/小时SAR多头/`、`data/小时MACD多头/` 读取逐合约 CSV。

## 当前规则

每个 WT8 文件代表一个品种在对应策略下的逐小时权益序列。用户选择策略、起始时点和结束时点后，系统对每个品种分别取两个时点或此前最近的一条记录，计算：

`区间收益金额 = 结束权益 - 起始权益`

`区间收益率 = 区间收益金额 / 起始权益 × 100%`

榜单按单个期货合约的一手区间收益金额从高到低排序，收益率作为参考字段显示，并标记 Top K。只取所选时点之前最近的记录可以避免把未来数据用于排名；若起始时点早于该品种第一条记录，则起始权益按 500,000 计算。WT8 的汇总行、空时间行会被过滤；编码兼容 GB18030、GBK 和 UTF-8。

## 启动

在 `D:\Anaconda3\envs\future-ranking` 环境中安装依赖：

```text
pip install -r requirements.txt
```

启动：

```text
python app.py
```

打开 `http://127.0.0.1:5000/`。旧项目的 8899 端口不受影响。

将新的策略 CSV 放入对应数据目录后，下一次接口请求会根据文件大小和修改时间自动重新读取。

## 目录

```text
Futures_Ranking/
├─ app.py                 Flask 启动入口
├─ config.py              环境配置（资金、端口、MySQL、JWT）
├─ backend/
│  ├─ routes/             REST API
│  ├─ repositories/       CSV 仓储；预留 MySQL 仓储
│  └─ services/           后续组合/交易业务
├─ front/                 原生 HTML、CSS、JavaScript
├─ data/小时Buy_And_Hold/  WT8 小时 K 线涨幅 CSV
├─ data/小时SAR多头/       WT8 SAR CSV
├─ data/小时MACD多头/      WT8 MACD CSV
└─ requirements.txt
```

## API

`GET /api/health`、`GET /api/strategies`、`GET /api/periods?strategy=sar_long`、`GET /api/rankings?strategy=sar_long&start_timestamp=2026-01-01T20:00:00&timestamp=2026-10-01T20:00:00&top_k=10`、`GET /api/contracts`、`GET /api/contracts/{品种}/series`。

排名接口传入 `start_timestamp` 和 `timestamp` 后，会对每个品种取起始、结束时点之前最近的权益，按区间收益金额排序：`区间收益 = 结束权益 - 起始权益`，`区间收益率 = 区间收益 / 起始权益 × 100%`。

点击榜单中的品种名称可展开该区间的 WT8 买卖信号明细，包含时间、买卖/开平操作、合约、成交价格、手数、成交额、手续费、平仓盈亏和当时权益。CSV 模式从原始信号明细读取；MySQL 模式使用各策略表中的成交字段。已有 MySQL 安装可运行 `python scripts/migrate_trade_details.py` 增加并同步这些字段，该脚本只更新已有行，不清空策略表。

## 本地 MySQL 数据库

项目保留了完整的本地数据库初始化和导入流程。先启动本机 MySQL 服务，然后安装依赖并设置本地 `.env`（该文件已被 Git 忽略）：

```text
STORAGE_BACKEND=mysql
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=你的本机MySQL密码
MYSQL_DATABASE=futures_ranking
INITIAL_CAPITAL=500000
```

创建数据库、表并导入三种 WT8 策略：

```text
python scripts/import_mysql.py
```

也可以单独运行 `python scripts/create_database.py` 创建数据库和表。当前采用每种策略独立一张表：`ranking_buyhold`、`ranking_sar`、`ranking_macd`。导入脚本读取对应 WT8 目录，按 2,000 行分批写入；重复运行会先清空该策略表再从明细 CSV 完整导入。建表 SQL 保存在 `db/schema.sql`，后续新增策略时，在 `scripts/import_mysql.py`、`scripts/create_database.py` 和 `backend/repositories/mysql_repository.py` 的策略表映射中增加映射。

当前本地代码默认仍可使用 CSV；完成导入后将 `.env` 的 `STORAGE_BACKEND` 设为 `mysql`，重启 `python app.py` 即切换到数据库查询，前端接口无需改变。

`/api/portfolio/status` 已预留“进入收益前 10 开一手、跌出收益前 10 平仓”的组合规则。`/api/auth/login` 已保留接口，接入用户表后再启用 JWT；当前排名接口匿名可用。

## 后续接入 MySQL

将 CSV 标准化为按 `instrument、timestamp、contract、equity、price、signal、position` 存储的明细表，实现 `backend/repositories/mysql_repository.py` 中的仓储方法，再在 `backend/routes/api.py` 把仓储实例替换为 MySQL 实现，前端接口不需要修改。
