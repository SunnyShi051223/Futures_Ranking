# Futures Ranking

基于 WT8 信号明细的期货排序平台。当前已接入 **纯价格涨跌幅**、**1 小时 K 线涨幅（Long & Hold）**、**1 小时 SAR 多头**、**1 小时 MACD 多头**，分别从 `data/小时Buy_And_Hold/`、`data/小时SAR多头/`、`data/小时MACD多头/` 读取逐合约 CSV。

## 当前规则

用户只选择一个观察时点。每个品种分别取该观察时点之前第五个有行情的交易日期作为基准日，并使用基准日与观察日同一小时或之前最近的有效记录：

- 策略榜按`（观察时点 WT8 权益 - 五日前 WT8 权益）÷ 五日前一手保证金`从高到低排序；保证金用窗口起点价格、合约乘数和当时已知保证金率估算。
- 纯价格榜按`观察时点价格 ÷ 五日前价格 - 1`从高到低排序，不使用策略权益。
- 少于五个历史交易日期或缺少有效基准权益/价格的品种不参与当次排名。
- 两端数据均不晚于观察时点；页面显示每个品种实际使用的数据时间。

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

`GET /api/health`、`GET /api/strategies`、`GET /api/periods?strategy=sar_long`、`GET /api/rankings?strategy=sar_long&timestamp=2026-10-09T15:00:00&top_k=10`、`GET /api/contracts`、`GET /api/contracts/{品种}/series`。

排名接口只需要一个观察时点 `timestamp`。返回项包含五日前基准时间、当前有效数据时间、收益金额/价格涨跌和收益率。点击策略榜品种可展开实际五日窗口内的 WT8 买卖信号明细。CSV 模式读取原始信号明细；MySQL 模式读取策略表。

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

## 组合回测

`notebooks/top10_portfolio_backtest.ipynb` 回测 Notebook 由 `BACKTEST_CONFIGS` 集中声明策略：当前包括三套前五日保证金收益率 Top 10 榜单，以及 20 个有行情交易日纯价格涨幅 Top 5 多头组合。新增回测通常只需增加配置项，即可自动进入统一引擎、汇总、权益曲线、持仓图和 CSV 导出。WT8 榜单按“窗口内权益变化 ÷ 窗口起点一手保证金”排序；纯价格榜按前 20 个有行情交易日的同一实际合约价格涨幅排序；窗口跨合约时不纳入该时点排名，避免主连价差污染涨幅。进入榜单后在下一条可交易记录买入一手，跌出榜单后平仓。初始资金 500,000 元，WT8 榜单最多持有十个品种，纯价格榜最多持有五个品种。价格盈亏按价格变化 × 合约乘数计算，保证金用于限制资金占用。

运行 Notebook 会生成四组策略汇总、交易明细、持仓快照、权益 CSV，以及比较资金曲线的 `backtest_output/top10_portfolio_equity_curve.png`。当前价格 Top 5 模拟净盈亏约 ¥126,310，期末权益约 ¥626,310，最大回撤约 -68.10%。这仍是基于小时级主连导出数据的近似模拟：手续费和滑点为零，历史合约换月成交、逐日真实保证金及实际强平规则尚未完整建模，不能作为历史真实账户收益。详细口径、限制、结果和文件说明见 `backtest_output/readme.md`。
