from datetime import datetime

from flask import Blueprint, jsonify, request

from config import settings
from backend.repositories.csv_repository import CsvRankingRepository


api_bp = Blueprint("api", __name__)
STRATEGIES = {
    "buy_hold": {
        "name": "1小时 K线涨幅（Buy & Hold）收益",
        "description": "按小时 K 线价格涨幅计算的逐合约收益排序",
        "folder": "小时Buy_And_Hold",
    },
    "sar_long": {
        "name": "1小时 SAR 多头收益",
        "description": "WT8 小时 SAR 多头策略逐合约权益收益排序",
        "folder": "小时SAR多头",
    },
    "macd_long": {
        "name": "1小时 MACD 多头收益",
        "description": "WT8 小时 MACD 多头策略逐合约权益收益排序",
        "folder": "小时MACD多头",
    },
}
repositories = {
    strategy_id: CsvRankingRepository(
        settings.data_dir / config["folder"], settings.initial_capital,
        strategy_id=strategy_id, strategy_name=config["name"],
    )
    for strategy_id, config in STRATEGIES.items()
}

# Parse the CSV files while the WSGI worker starts. This makes the first
# browser request return immediately instead of spending the request timeout
# scanning dozens of WT8 exports.


def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _repository(strategy: str):
    repository = repositories.get(strategy)
    if repository is None:
        return None, _error(f"不支持的策略：{strategy}", 404)
    return repository, None


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "data_source": "csv", "strategy_count": len(STRATEGIES)})


@api_bp.get("/strategies")
def strategies():
    return jsonify({"items": [
        {"id": strategy_id, "name": config["name"], "description": config["description"], "available": True}
        for strategy_id, config in STRATEGIES.items()
    ]})


@api_bp.get("/periods")
def periods():
    strategy = request.args.get("strategy", "sar_long")
    repository, error = _repository(strategy)
    if error:
        return error
    try:
        limit = min(max(int(request.args.get("limit", 10000)), 1), 20000)
    except ValueError:
        return _error("limit 必须是整数")
    return jsonify(repository.periods(limit=limit))


@api_bp.get("/contracts")
def contracts():
    strategy = request.args.get("strategy", "sar_long")
    repository, error = _repository(strategy)
    if error:
        return error
    return jsonify({"items": repository.contracts()})


@api_bp.get("/rankings")
def rankings():
    strategy = request.args.get("strategy", "sar_long")
    repository, error = _repository(strategy)
    if error:
        return error
    timestamp = request.args.get("timestamp")
    if not timestamp:
        return _error("缺少 timestamp，例如 2026-10-09T10:00:00")
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return _error("timestamp 格式错误")
    try:
        top_k = min(max(int(request.args.get("top_k", 10)), 1), 100)
    except ValueError:
        return _error("top_k 必须是整数")
    try:
        return jsonify(repository.ranking(timestamp, top_k=top_k))
    except ValueError as exc:
        return _error(str(exc))


@api_bp.get("/contracts/<path:instrument>/series")
def contract_series(instrument: str):
    strategy = request.args.get("strategy", "sar_long")
    repository, error = _repository(strategy)
    if error:
        return error
    repository.contracts()
    if instrument not in repository.contract_names:
        return _error("合约不存在", 404)
    return jsonify({"instrument": instrument, "items": repository.series(instrument)})


@api_bp.post("/auth/login")
def login():
    # JWT authentication is reserved for the MySQL/user module. Keep the
    # endpoint stable now so the frontend does not need to change later.
    return _error("认证模块尚未启用，当前数据接口允许匿名访问", 501)


@api_bp.get("/portfolio/status")
def portfolio_status():
    return jsonify({
        "status": "reserved",
        "rule": "进入收益前10开一手，跌出收益前10平仓",
        "max_position_per_instrument": 1,
        "initial_capital": settings.initial_capital,
    })
