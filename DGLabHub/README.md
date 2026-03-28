# dg_lab_hub

N.E.K.O 的 `dg_lab_hub` 插件，用于通过 `DG-Lab-Coyote-Game-Hub` 的 HTTP API 控制 DG-Lab。

支持能力：
- 启动/停止插件目录内附带的 Hub
- 自动获取或手动指定 `client_id`
- 查询 DG-Lab 当前状态
- 调整基础强度和随机强度
- 获取/设置当前波形
- 触发一键开火

## 目录结构

```text
plugin/plugins/dg_lab_hub/
├─ __init__.py
├─ plugin.toml
└─ coyote-game-hub/
   ├─ start.bat
   ├─ server/
   └─ public/
```

插件默认会使用同目录下的 `coyote-game-hub` 作为可选内置 Hub。

## 依赖

- `DG-Lab-Coyote-Game-Hub`
- 默认 Hub 地址：`http://127.0.0.1:8920`

## 配置

文件：`plugin/plugins/dg_lab_hub/plugin.toml`

```toml
[dg_lab_hub]
base_url = "http://127.0.0.1:8920"
client_id = ""
timeout_seconds = 10
allow_broadcast_all = false
auto_start_hub = false
hub_dir = "coyote-game-hub"
startup_timeout_seconds = 20
show_hub_window = true
```

### 配置项说明

- `base_url`：Hub HTTP 地址
- `client_id`：默认目标客户端 ID；留空时插件会自动获取
- `timeout_seconds`：HTTP 请求超时
- `allow_broadcast_all`：是否允许将 `client_id` 设为 `all`
- `auto_start_hub`：是否自动启动插件目录内的 Hub
- `hub_dir`：Hub 相对目录名
- `startup_timeout_seconds`：等待 Hub 启动超时
- `show_hub_window`：Windows 下是否显示 Hub 窗口

## client_id 获取机制

插件现在支持三种 `client_id` 来源，优先级如下：

1. **调用时显式传入** `client_id`
2. **配置文件中的** `client_id`
3. **自动获取**

当调用接口时既没有传入 `client_id`，配置中也为空，插件会请求：

```text
GET /api/client/connect
```

由 Hub 返回一个可用的 `clientId`，并缓存到当前插件进程内，供后续请求复用。

注意：
- 这个自动获取只缓存到当前插件进程，不会回写 `plugin.toml`
- 如果 Hub 未启动或不可达，会返回明确错误
- `all` 仍然受 `allow_broadcast_all` 控制

## 插件入口

### 1. 启动 Hub

- `start_hub`

输入：

```json
{
  "show_window": true
}
```

说明：
- 启动插件目录中的 `coyote-game-hub`
- 如果 Hub 已经在线，则直接复用

---

### 2. 停止 Hub

- `stop_hub`

说明：
- 仅停止由当前插件启动的 Hub
- 不会杀掉外部手动启动的 Hub

---

### 3. 获取/确保 client_id

- `ensure_client_id`

输入：

```json
{
  "client_id": "optional-client-id"
}
```

返回示例：

```json
{
  "status": "ready",
  "base_url": "http://127.0.0.1:8920",
  "client_id": "3ab0773d-69d0-41af-b74b-9c6ce6507f65",
  "source": "auto"
}
```

`source` 可能为：
- `input`
- `config`
- `auto`

---

### 4. 获取 DG-Lab 状态

- `get_game_info`

输入：

```json
{
  "client_id": "optional-client-id"
}
```

对应 Hub 接口：

```text
GET /api/v2/game/{clientId}
```

返回内容通常包括：
- `strengthConfig`
- `gameConfig`
- `clientStrength`
- `currentPulseId`

---

### 5. 设置强度

- `set_strength`

输入示例：

```json
{
  "client_id": "optional-client-id",
  "strength_add": 1,
  "random_strength_set": 5
}
```

支持参数：
- `strength_add`
- `strength_sub`
- `strength_set`
- `random_strength_add`
- `random_strength_sub`
- `random_strength_set`

对应 Hub 接口：

```text
POST /api/v2/game/{clientId}/strength
```

---

### 6. 获取当前波形

- `get_pulse`

输入：

```json
{
  "client_id": "optional-client-id"
}
```

对应 Hub 接口：

```text
GET /api/v2/game/{clientId}/pulse
```

---

### 7. 设置波形

- `set_pulse`

输入示例：

```json
{
  "client_id": "optional-client-id",
  "pulse_id": "d6f83af0"
}
```

或：

```json
{
  "client_id": "optional-client-id",
  "pulse_id": ["d6f83af0", "7eae1e5f"]
}
```

对应 Hub 接口：

```text
POST /api/v2/game/{clientId}/pulse
```

---

### 8. 一键开火

- `fire`

输入示例：

```json
{
  "client_id": "optional-client-id",
  "strength": 20,
  "time": 5000,
  "override": false,
  "pulse_id": "d6f83af0"
}
```

对应 Hub 接口：

```text
POST /api/v2/game/{clientId}/action/fire
```

## 使用建议

### 场景 1：手动指定固定 client_id

适合你已经知道要控制哪个客户端的情况。

- 在 `plugin.toml` 中填写 `client_id`
- 或每次调用时显式传入 `client_id`

### 场景 2：让插件自动获取 client_id

适合本地单机使用。

- 保持 `client_id = ""`
- 确保 Hub 已启动
- 先调用一次 `ensure_client_id`，或直接调用 `get_game_info` / `fire`

### 场景 3：广播到所有客户端

- 需要设置：

```toml
allow_broadcast_all = true
```

然后调用时传：

```json
{
  "client_id": "all"
}
```

## 常见问题

### 1. 提示“未指定 client_id”

如果你看到这个错误，通常是：
- 旧版本插件还没有自动获取能力
- 或 Hub 当前不可达，自动获取失败

建议：
- 检查 `base_url`
- 确认 Hub 已启动
- 先调用 `ensure_client_id`

### 2. 自动获取失败

可能原因：
- Hub 未启动
- `base_url` 配置错误
- `/api/client/connect` 不可用
- 网络/端口被占用

### 3. `all` 不可用

默认禁止广播到全部客户端。

如需启用：

```toml
allow_broadcast_all = true
```

## 对应的 Hub API

本插件主要封装了以下接口：

- `GET /api/client/connect`
- `GET /api/v2/game/{clientId}`
- `POST /api/v2/game/{clientId}/strength`
- `GET /api/v2/game/{clientId}/pulse`
- `POST /api/v2/game/{clientId}/pulse`
- `POST /api/v2/game/{clientId}/action/fire`

## 说明

- 插件使用 `httpx.AsyncClient` 与 Hub 通信
- 自动获取的 `client_id` 仅在当前插件进程内缓存
- 插件不会自动修改 Hub 配置
- 插件不会自动持久化回写 `plugin.toml`
