# Copyright (c) 20260731 XUAN LI. All rights reserved.

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Tuple, Optional, Literal, Callable, Union, Text, TypeVar, Dict, Iterable, List, Sequence

import io
import os
import json
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

try:
    import pyarrow.parquet as pq

    HAS_PYARROW: bool = True
except Exception:
    # 不止 ImportError: pyarrow 装得上但 DLL 被安全策略拦掉时抛的也是 ImportError 的变体,
    # Windows 智能应用控制(SAC)拦 _parquet DLL 即为此(20260803 实发)。这里一律降级到
    # npz 通道而不是让 import 失败 —— 客户端连不上和跑不起来对使用者是同一件事
    pq = None
    HAS_PYARROW = False

DEFAULT_TIMEOUT: int = 300
ENV_URL: str = 'ANEMOI_GATEWAY_URL'
ENV_KEY: str = 'ANEMOI_GATEWAY_KEY'
DTYPE_METADATA_KEY: bytes = b'anemoi_dtypes'
ACCEPT_FORMAT_HEADER: str = 'X-Accept-Format'
FORMAT_HEADER: str = 'X-Anemoi-Format'
FORMAT_PARQUET: str = 'parquet'
FORMAT_NPZ: str = 'npz'


def buildOpener() -> urllib.request.OpenerDirector:
    r"""
    造一个绕过系统代理的 opener

    Returns:
        opener 实例, 对任何地址都不走代理

    Notes:
        urllib 的默认 opener 会读系统代理设置与 http_proxy 环境变量, 而网关地址是
        tailnet 内网地址, 一旦被 Clash 等代理软件截走就会返回 502 或直接连不上。
        网关永远位于隧道内, 不存在需要经代理才能到达的部署, 故这里无条件禁用代理,
        使用者开不开 VPN 都不影响调用
    """
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def restoreDtypes(frame: pd.DataFrame, dtypes: Dict[str, str]) -> pd.DataFrame:
    r"""
    按服务端给的原始 dtype 逐列还原

    Args:
        frame: 已还原出数据的 DataFrame
        dtypes: 列名到 dtype 字符串的映射

    Returns:
        dtype 与服务端看到的一致的 DataFrame

    Notes:
        个别列还原失败不影响其余列, 只保留原样 —— 宁可一列 dtype 有出入,
        也不要整次取数失败
    """
    for col, dtype in dtypes.items():
        if col in frame.columns and str(frame[col].dtype) != dtype:
            try:
                frame[col] = frame[col].astype(dtype)
            except (TypeError, ValueError):
                continue

    return frame


def deserializeFrameNpz(body: bytes) -> pd.DataFrame:
    r"""
    还原服务端用 npz 传回的 DataFrame

    Args:
        body: npz 字节流

    Returns:
        列顺序与 dtype 均与服务端一致的 DataFrame

    Notes:
        与服务端 serializeFrameNpz 对称。数值列取 numpy 原始字节故逐位无损, 字符串列
        在 meta 的 json 里, 因此 np.load 可以 allow_pickle=False —— 不给远端任何
        反序列化执行的机会, 即便网关被冒充也只能塞进数据而不是代码
    """
    with np.load(io.BytesIO(body), allow_pickle=False) as bundle:
        meta = json.loads(bundle['meta'].tobytes().decode('utf-8'))
        columns: Dict[str, Any] = {}
        for name in meta['columns']:
            if name in meta['numeric']:
                columns[name] = bundle[meta['numeric'][name]]
            else:
                columns[name] = pd.Series(meta['text'][name], dtype='object')

    frame = pd.DataFrame(columns, columns=meta['columns'])

    return restoreDtypes(frame, meta['dtypes'])


def deserializeFrame(body: bytes) -> pd.DataFrame:
    r"""
    把网关返回的 parquet 还原成与上游逐列同 dtype 的 DataFrame

    Args:
        body: parquet 字节流

    Returns:
        DataFrame, 各列 dtype 与服务端看到的上游返回一致

    Notes:
        pandas 3 的 infer_string 会把 object 字符串列读成 StringDtype, 导致经网关
        与直连的结果 dtype 不同, 下游一切依赖 dtype 的逻辑都会悄悄分叉。故按服务端
        写入的 anemoi_dtypes 逐列还原; 个别列还原失败不影响其余列, 只保留原样
    """
    assert HAS_PYARROW, '本机没有可用的 pyarrow, 无法解析 parquet 响应'
    table = pq.read_table(io.BytesIO(body))
    frame = table.to_pandas()
    metadata = table.schema.metadata or {}
    if DTYPE_METADATA_KEY not in metadata:
        return frame

    return restoreDtypes(frame, json.loads(metadata[DTYPE_METADATA_KEY].decode('utf-8')))


class GatewayError(RuntimeError):
    r"""
    网关侧返回的错误, 与本地网络异常区分开
    """


class DataAPIProxy:
    r"""
    通联 DataAPI 的远端代理, 调用签名与官方逐字一致

    Notes:
        用法与官方完全相同, 只需把 from uqer import DataAPI 换成
        from Boreas.gateway.client import DataAPI, 其余代码一行不动;
        本地不需要安装 uqer, 也不持有任何令牌
    """

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        r"""
        Args:
            url: 网关地址, 缺省读环境变量 ANEMOI_GATEWAY_URL
            key: 访问 key, 缺省读环境变量 ANEMOI_GATEWAY_KEY
            timeout: 单次请求超时秒数, 大表拉取较慢故缺省给到 300
        """
        self.url = (url or os.environ.get(ENV_URL, '')).rstrip('/')
        self.key = key or os.environ.get(ENV_KEY, '')
        self.timeout = timeout
        self.opener = buildOpener()
        self.schema: Optional[Dict[str, List[str]]] = None
        assert self.url, '未配置网关地址, 请设环境变量 {} 或显式传入 url'.format(ENV_URL)
        assert self.key, '未配置访问 key, 请设环境变量 {} 或显式传入 key'.format(ENV_KEY)

    def request(self, path: str, method: str = 'GET', payload: Optional[Dict[str, Any]] = None) -> Tuple[bytes, str]:
        r"""
        向网关发一次请求

        Args:
            path: 端点路径
            method: HTTP 方法
            payload: POST 请求体

        Returns:
            (响应体字节流, 响应头字典), 头的键一律小写

        Notes:
            网关返回的非 2xx 一律转成 GatewayError 并带上服务端给的中文原因;
            走自建 opener 而非 urlopen, 以绕开系统代理, 详见 buildOpener;
            返回整个响应头而非只给 Content-Type, 是因为序列化格式也经头传回
        """
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header('X-Api-Key', self.key)
        # 本机没有可用的 pyarrow 时声明只收 npz, 服务端据此换一条不依赖它的序列化路径
        req.add_header(ACCEPT_FORMAT_HEADER, FORMAT_PARQUET if HAS_PYARROW else FORMAT_NPZ)
        if data is not None:
            req.add_header('Content-Type', 'application/json; charset=utf-8')

        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                return resp.read(), {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as e:
            with e:
                body = e.read().decode('utf-8', errors='replace')
            try:
                reason = json.loads(body).get('error', body)
            except json.JSONDecodeError:
                reason = body

            raise GatewayError('网关返回 {}: {}'.format(e.code, reason)) from None
        except urllib.error.URLError as e:
            raise GatewayError('无法连接网关 {}: {}'.format(self.url, e.reason)) from None
        except TimeoutError:
            # socket 超时不是 URLError 的子类, 漏接会让调用方拿到一个没有上下文的裸异常
            raise GatewayError(
                '请求网关超时(>{}s), 数据量过大时可增大 timeout 或缩小查询区间'.format(self.timeout)
            ) from None
        except OSError as e:
            raise GatewayError('与网关通信失败: {}'.format(e)) from None

    def loadSchema(self) -> Dict[str, List[str]]:
        r"""
        拉取并缓存接口签名表

        Returns:
            接口名到参数顺序的映射

        Notes:
            仅用于把位置参数还原成关键字参数, 每个进程只拉一次
        """
        if self.schema is None:
            body, _ = self.request('/schema')
            self.schema = json.loads(body.decode('utf-8'))['schema']

        return self.schema

    def getTraffic(self) -> Dict[str, Any]:
        r"""
        查询通联账号当日流量余量

        Returns:
            含 bytes_limit / bytes_current / bytes_remain / used_pct 的字典

        Notes:
            返回的是账号级全局流量, 全部 key 共用同一个通联账号, 不是本 key 的独占额度;
            每日 0 点重置。取数前先看一眼可以避免拉到一半撞上限额
        """
        body, _ = self.request('/traffic')

        return json.loads(body.decode('utf-8'))

    def call(self, api_name: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> pd.DataFrame:
        r"""
        转发一次接口调用

        Args:
            api_name: 接口名
            args: 位置参数
            kwargs: 关键字参数

        Returns:
            与官方接口一致的 DataFrame

        Notes:
            位置参数按服务端给出的官方参数顺序就地转成关键字, 因此
            DataAPI.TradeCalGet('XSHG') 与 DataAPI.TradeCalGet(exchangeCD='XSHG') 等价
        """
        if args:
            params = self.loadSchema().get(api_name, [])
            if len(args) > len(params):
                raise TypeError('{} 最多接受 {} 个位置参数, 收到 {} 个'.format(api_name, len(params), len(args)))

            duplicated = [p for p in params[:len(args)] if p in kwargs]
            if duplicated:
                raise TypeError('{} 的参数 {} 同时以位置和关键字传入'.format(api_name, ', '.join(duplicated)))

            kwargs = {**dict(zip(params, args)), **kwargs}

        body, headers = self.request('/api', method='POST', payload={'api': api_name, 'kwargs': kwargs})
        content_type = headers.get('content-type', '')
        if 'application/octet-stream' not in content_type:
            raise GatewayError('网关返回了非预期的内容类型 {}'.format(content_type))

        fmt = headers.get(FORMAT_HEADER.lower(), FORMAT_PARQUET)

        return deserializeFrameNpz(body) if fmt == FORMAT_NPZ else deserializeFrame(body)

    def __getattr__(self, api_name: str) -> Callable[..., pd.DataFrame]:
        r"""
        把任意 XxxGet 属性访问动态映射成一次远端调用

        Args:
            api_name: 接口名

        Returns:
            可调用对象, 签名等价于官方接口

        Notes:
            以双下划线开头的属性不拦截, 否则会破坏 copy 与 pickle 等协议
        """
        if api_name.startswith('__'):
            raise AttributeError(api_name)

        def caller(*args: Any, **kwargs: Any) -> pd.DataFrame:
            return self.call(api_name, args, kwargs)

        caller.__name__ = api_name

        return caller


class LazyDataAPI:
    r"""
    模块级 DataAPI 入口, 首次真正调用时才按环境变量建连接

    Notes:
        不能在导入时就实例化 —— 环境变量未配好时导入会直接抛错, 使用者连
        import 都过不去; 也不能置为 None, 那样调用时只会得到一句
        NoneType object has no attribute XXXGet, 完全看不出是没配环境变量
    """

    def __init__(self) -> None:
        self.proxy: Optional[DataAPIProxy] = None

    def getProxy(self) -> DataAPIProxy:
        r"""
        取底层客户端, 尚未建立则按环境变量建一个

        Returns:
            客户端实例

        Notes:
            环境变量缺失时给出可照做的中文指引而非裸异常
        """
        if self.proxy is None:
            missing = [k for k in (ENV_URL, ENV_KEY) if not os.environ.get(k)]
            if missing:
                raise GatewayError(
                    '尚未配置 {}。请先设置环境变量:\n'
                    '  export {}=网关地址\n'
                    '  export {}=你的 key\n'
                    '或显式构造 DataAPIProxy(url=..., key=...)'.format(' 与 '.join(missing), ENV_URL, ENV_KEY)
                )

            self.proxy = DataAPIProxy()

        return self.proxy

    def __getattr__(self, api_name: str) -> Callable[..., pd.DataFrame]:
        r"""
        把属性访问透传给底层客户端

        Args:
            api_name: 接口名

        Returns:
            可调用对象, 签名等价于官方接口
        """
        if api_name.startswith('__'):
            raise AttributeError(api_name)

        return getattr(self.getProxy(), api_name)


DataAPI = LazyDataAPI()
