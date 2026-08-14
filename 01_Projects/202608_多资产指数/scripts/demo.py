# Copyright (c) 20260731 XUAN LI. All rights reserved.

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Tuple, Optional, Literal, Callable, Union, Text, TypeVar, Dict, Iterable, List, Sequence

r"""
通联数据网关的使用示例, 直接运行即可: python demo.py

前置: 已装 pandas 与 pyarrow, 已设好环境变量 ANEMOI_GATEWAY_URL 与 ANEMOI_GATEWAY_KEY
本文件与 client.py 放在同一目录下即可运行, 不需要安装 uqer, 也不需要 Anemoi 仓库
"""

import os
import sys

import pandas as pd

try:
    from client import DataAPI, DataAPIProxy, GatewayError, ENV_URL, ENV_KEY
except ImportError:
    # 也支持从 Anemoi 仓库内直接运行
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )))))
    from Notus.modules.server.private.client import DataAPI, DataAPIProxy, GatewayError, ENV_URL, ENV_KEY


def showFrame(title: str, data: pd.DataFrame, n_head: int = 3) -> None:
    r"""
    统一格式打印一张结果表

    Args:
        title: 小节标题
        data: 结果表
        n_head: 打印前几行
    """
    print('  形状: {} 行 x {} 列'.format(*data.shape))
    if data.empty:
        print('  (该区间无数据, 这不是错误)')

        return

    print('  列名: {}'.format(', '.join(map(str, data.columns[:8])) + (' ...' if len(data.columns) > 8 else '')))
    print(data.head(n_head).to_string(index=False, max_colwidth=18))


def checkEnvironment() -> bool:
    r"""
    检查环境变量与网关连通性

    Returns:
        全部就绪返回 True
    """
    print('[1/5] 检查配置与连通性')
    missing = [k for k in (ENV_URL, ENV_KEY) if not os.environ.get(k)]
    if missing:
        print('  未设置: {}'.format(' 与 '.join(missing)))
        print('  请按 INTERN_GUIDE.md 第一节设置环境变量后重开终端')

        return False

    print('  网关地址: {}'.format(os.environ[ENV_URL]))
    print('  key: {}...(已隐藏)'.format(os.environ[ENV_KEY][:14]))
    try:
        api = DataAPIProxy()
        body, _ = api.request('/health')
        print('  连通性: 正常')
    except GatewayError as e:
        print('  连不上网关: {}'.format(e))

        return False

    # 流量查询失败不影响取数, 故只提示不返回 False: 老版本网关没有 /traffic 端点会 404,
    # 真到了额度上限也是取数时才报错, 这里查不到不构成"环境没装好"
    try:
        traffic = api.getTraffic()
        limit, remain = int(traffic.get('bytes_limit') or 0), int(traffic.get('bytes_remain') or 0)
        if limit > 0:
            print('  账号流量: 剩余 {:.1f} GiB / 上限 {:.1f} GiB(全账号共用, 已用 {}%)'.format(
                remain / 2 ** 30, limit / 2 ** 30, traffic.get('used_pct')))
        else:
            print('  账号流量: 上游未返回额度信息, 不影响取数')
    except GatewayError as e:
        print('  账号流量: 查询失败({}), 不影响取数'.format(e))

    return True


def demoIndexDaily() -> None:
    r"""
    示例一: 取沪深300指数日行情
    """
    print()
    print('[2/5] 取沪深300指数日行情 MktIdxdGet')
    data = DataAPI.MktIdxdGet(
        indexID=u"000300.ZICN",
        ticker=u"",
        tradeDate=u"",
        beginDate=u"20260701",
        endDate=u"20260731",
        exchangeCD=u"",
        field=u"tradeDate,indexID,secShortName,closeIndex,CHGPct,turnoverVol",
        pandas="1",
    )
    showFrame('指数日行情', data)


def demoEquityDaily() -> None:
    r"""
    示例二: 取多只股票的日行情

    Notes:
        secID 传逗号分隔的多只股票比循环单只快得多, 也更省配额
    """
    print()
    print('[3/5] 取股票日行情 MktEqudGet')
    data = DataAPI.MktEqudGet(
        secID=u"000001.XSHE,600000.XSHG",
        ticker=u"",
        tradeDate=u"",
        beginDate=u"20260701",
        endDate=u"20260710",
        isOpen="",
        field=u"tradeDate,secID,secShortName,openPrice,closePrice,turnoverVol",
        pandas="1",
    )
    showFrame('股票日行情', data)


def demoTradeCalendar() -> None:
    r"""
    示例三: 取交易日历, 演示位置参数写法
    """
    print()
    print('[4/5] 取交易日历 TradeCalGet(演示位置参数)')
    data = DataAPI.TradeCalGet('XSHG', beginDate=u"20260701", endDate=u"20260710", field=u"calendarDate,isOpen")
    showFrame('交易日历', data)


def demoErrorHandling() -> None:
    r"""
    示例四: 错误处理

    Notes:
        网关侧的错误统一是 GatewayError, 消息里会写明原因
    """
    print()
    print('[5/5] 错误处理演示')
    try:
        DataAPI.ThisApiDoesNotExistGet(foo='bar')
        print('  预期应当报错但没有报错')
    except GatewayError as e:
        print('  按预期捕获到错误: {}'.format(e))

    print()
    print('  建议写法:')
    print('    try:')
    print('        data = DataAPI.MktEqudGet(...)')
    print('    except GatewayError as e:')
    print('        print("取数失败:", e)')


def main() -> int:
    r"""
    依次跑完全部示例

    Returns:
        进程退出码, 0 表示全部通过
    """
    print('=' * 60)
    print('通联数据网关 使用示例')
    print('=' * 60)
    if not checkEnvironment():
        return 1

    try:
        demoIndexDaily()
        demoEquityDaily()
        demoTradeCalendar()
        demoErrorHandling()
    except GatewayError as e:
        print()
        print('取数过程出错: {}'.format(e))
        print('常见原因见 INTERN_GUIDE.md 第五节')

        return 1

    print()
    print('=' * 60)
    print('全部检查通过, 可以开始使用了')
    print('把 from uqer import DataAPI 换成 from client import DataAPI, 其余代码不用改')
    print('=' * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
