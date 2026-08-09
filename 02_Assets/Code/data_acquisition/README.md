# Data Acquisition

存放跨项目复用的数据接口客户端与数据提取脚本。

## 当前文件

- `client.py`：管理员提供的通联数据网关客户端。
- `demo.py`：管理员提供的连通性与接口验证脚本。
- 后续通联取数脚本直接放在本目录，以支持 `from client import DataAPI`。

管理员提供的两个 Python 文件仅在本地使用，并由 `.gitignore` 排除；`KEY.txt` 不得复制到仓库。

## 数据存储边界

- 跨项目公共数据写入仓库外的 `~/Desktop/InternData/StockData`，并按 `raw`、`interim` 或 `processed` 分层。
- 数据脚本默认使用 `~/Desktop/InternData/StockData`；如需临时改址，可设置环境变量 `STOCK_DATA_ROOT`。
- 单一项目专属数据写入 `~/Desktop/InternData/<项目数据目录>`，不要写入本代码目录或 Git 仓库。
- 网关地址与密钥通过环境变量提供，不写入代码、说明文档或 Git。

## 运行方式

在仓库根目录启用本地虚拟环境：

```bash
source .venv/bin/activate
```

配置网关环境变量后，在仓库根目录运行验证脚本：

```bash
python 02_Assets/Code/data_acquisition/demo.py
```
