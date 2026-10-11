# Futures Ranking

基于 WT8 信号明细的期货策略收益排序平台。当前已接入 **1 小时 K 线涨幅（Buy & Hold）**、**1 小时 SAR 多头**、**1 小时 MACD 多头**三种策略，分别从 `data/小时Buy_And_Hold/`、`data/小时SAR多头/`、`data/小时MACD多头/` 读取逐合约 CSV。

## 当前规则

每个 WT8 文件代表一个品种在对应策略下的逐小时权益序列。用户选择策略和时间点后，系统对每个品种取该时间点或此前最近的一条记录，计算：

`收益金额 = 权益 - 500000`

`收益率 = (权益 - 500000) / 500000 × 100%`

最后按收益率从高到低排序，并标记 Top K。只取此前记录可以避免把未来数据用于当前排名。WT8 的汇总行、空时间行会被过滤；编码兼容 GB18030、GBK 和 UTF-8。

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

`GET /api/health`、`GET /api/strategies`、`GET /api/periods?strategy=sar_long`、`GET /api/rankings?strategy=sar_long&timestamp=2026-10-09T10:00:00&top_k=10`、`GET /api/contracts`、`GET /api/contracts/{品种}/series`。

`/api/portfolio/status` 已预留“进入收益前 10 开一手、跌出收益前 10 平仓”的组合规则。`/api/auth/login` 已保留接口，接入用户表后再启用 JWT；当前排名接口匿名可用。

## 后续接入 MySQL

将 CSV 标准化为按 `instrument、timestamp、contract、equity、price、signal、position` 存储的明细表，实现 `backend/repositories/mysql_repository.py` 中的仓储方法，再在 `backend/routes/api.py` 把仓储实例替换为 MySQL 实现，前端接口不需要修改。
