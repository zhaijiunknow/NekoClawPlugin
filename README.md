# N.E.K.O 插件制作指南

本文基于当前 `https://github.com/Project-N-E-K-O/N.E.K.O` 仓库里的真实实现整理，目标是让你按现有 SDK 和项目约定编写可运行的 N.E.K.O 插件。

## 1. 先认识当前插件体系

N.E.K.O 对外导出的插件能力集中在 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/__init__.py:7-125`，这里已经把插件作者最常用的对象和装饰器暴露出来了。开发插件时，优先围绕这些名字理解系统：

- `NekoPluginBase`
- `@neko_plugin`
- `@plugin_entry`
- `@lifecycle`
- `message`
- `timer_interval`
- `SystemInfo`
- `MemoryClient`

如果你只是想先写一个最小插件，真正必须掌握的只有四个：

- `NekoPluginBase`
- `@neko_plugin`
- `@plugin_entry`
- `@lifecycle`

---

## 2. 一个插件最少要有什么文件

一个插件目录至少要有：

```text
plugin/plugins/your_plugin/
├─ __init__.py
└─ plugin.toml
```

现成例子：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/plugin.toml:1-25`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/plugin.toml:1-25`
- 以及本仓库的数个

`plugin.toml` 负责声明插件元数据、运行时行为和你自己的配置段；`__init__.py` 里放插件类实现。

---

## 3. plugin.toml 怎么写

### 3.1 最小字段结构

当前仓库中的插件普遍使用这些段：

```toml
[plugin]
name = "示例插件"
description = "示例说明"
version = "0.1.0"
id = "example_plugin"
entry = "plugin.plugins.example_plugin:ExamplePlugin"

[plugin.author]
name = "Your Name"

[plugin.sdk]
recommended = ">=0.1.0,<0.2.0"
supported = ">=0.1.0,<0.3.0"

[plugin_runtime]
enabled = true
auto_start = true

[plugin.store]
enabled = false

[example_plugin]
foo = "bar"
```

### 3.2 各字段作用

#### `[plugin]`

常用字段参考 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/_types/models.py:92-107` 以及各插件 `plugin.toml` 示例。
- `id`：插件唯一 ID
- `name`：展示名
- `description`：描述
- `version`：插件版本
- `entry`：插件类路径，格式是 `模块路径:类名`
- `type`：可选，`qq_auto_reply` 使用了 `type = "plugin"`，见 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/qq_auto_reply/plugin.toml:1-8`

其中最关键的是：

```toml
entry = "plugin.plugins.example_plugin:ExamplePlugin"
```

这必须和你在 `__init__.py` 中定义的类完全对应。

#### `[plugin.author]`

至少通常会写 `name`。

#### `[plugin.sdk]`

用于声明推荐/支持的 SDK 版本范围。现有插件都保留这两项：

- `recommended`
- `supported`

#### `[plugin_runtime]`

- `enabled`：插件是否启用
- `auto_start`：是否随系统自动启动

#### `[plugin.store]`

- `enabled`：是否启用持久化存储

如果你的插件不需要持久化，通常设为 `false`；如果要像备忘录那样长期保存数据，则设为 `true`。

#### `[your_plugin_id]`

这是你自己的业务配置段。比如：

- `web_search` 用 `[search]`，见 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/plugin.toml:22-25`
- `memo_reminder` 用 `[memo]`，见 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/plugin.toml:22-25`

建议配置段名和插件 ID 保持一致，或至少让人一眼能看懂。

---

## 4. 插件类怎么写

### 4.1 必须继承 `NekoPluginBase`

插件基类在 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/base.py:23-83`。最基础的写法是：

```python
from plugin.sdk.plugin import NekoPluginBase, neko_plugin


@neko_plugin
class ExamplePlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
```

### 4.2 基类已经给你的能力

根据 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/base.py:37-83`，插件里可以直接使用这些能力：

- `self.plugin_id`：当前插件 ID
- `self.config_dir`：当前插件配置目录
- `self.data_path(...)`：插件数据目录拼接
- `self.plugins`：插件相关运行时接口
- `self.memory`：记忆能力客户端
- `self.system_info`：系统信息客户端
- `self.push_message(...)`：向宿主推送消息

如果只做工具型入口，通常先用到的还是 `plugin_id`、`config`、`store`、日志。

### 4.3 推荐在 `__init__` 里做什么

看两个现有插件：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:131-139`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:247-253`

当前项目的常见模式是：

1. `super().__init__(ctx)`
2. 配置文件日志
3. 初始化插件内部状态

例如：

```python
@neko_plugin
class ExamplePlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg = {}
```

---

## 5. 装饰器怎么用

### 5.1 `@neko_plugin`

定义位置：`https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/decorators.py:52-53`

作用：标记这是一个 N.E.K.O 插件类。

用法：

```python
@neko_plugin
class ExamplePlugin(NekoPluginBase):
    ...
```

这一步不要省略。

### 5.2 `@plugin_entry`

定义位置：`https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/decorators.py:87-121`

它用于声明插件可调用入口。常见参数：

- `id`
- `name`
- `description`
- `input_schema`
- `timeout`
- `llm_result_fields`
- `kind`
- `auto_start`

真实例子见：
`https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:316-417`

示例：

```python
@plugin_entry(
    id="echo",
    name="回显",
    description="返回传入的文本",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "要回显的文本"},
        },
        "required": ["text"],
    },
)
async def echo(self, text: str, **_):
    return Ok({"text": text})
```

### 5.3 `@lifecycle`

定义位置：`https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/decorators.py:124-131`

当前支持的生命周期 ID：

- `startup`
- `shutdown`
- `reload`
- `freeze`
- `unfreeze`
- `config_change`

最常见的是 `startup` 和 `shutdown`。

真实例子：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:189-232`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:255-274`

示例：

```python
@lifecycle(id="startup")
async def startup(self, **_):
    return Ok({"status": "running"})


@lifecycle(id="shutdown")
async def shutdown(self, **_):
    return Ok({"status": "shutdown"})
```

### 5.4 还有哪些装饰器

`plugin.__init__` 也导出了这些能力：

- `message`
- `timer_interval`
- `on_event`

此外 `decorators.py` 里还能看到 hook 相关装饰器，例如：

- `hook`
- `before_entry`
- `after_entry`
- `around_entry`
- `replace_entry`

这些属于更进阶的能力。第一版插件先把 `@plugin_entry` 和 `@lifecycle` 用熟即可。

---

## 6. 配置怎么读取

```python
cfg = await self.config.dump(timeout=5.0)
cfg = cfg if isinstance(cfg, dict) else {}
```

参考：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:189-223`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:255-269`

然后从自己的配置段中取值，例如：

```python
search_cfg = cfg.get("search") if isinstance(cfg.get("search"), dict) else {}
self._cfg = search_cfg
```

或者：

```python
memo_cfg = cfg.get("memo") if isinstance(cfg.get("memo"), dict) else {}
```

推荐原则：

1. 先整体 `dump`
2. 确保结果是 `dict`
3. 再拿自己的配置段
4. 对每个字段自己做类型和默认值处理

---

## 7. 返回值、错误处理该怎么写

### 7.1 用 `Ok` / `Err`

当前项目用的是显式 Result 风格。定义见：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/_types/result.py:37-177`

语义：

- `Ok(value)`：成功
- `Err(error)`：失败

现有插件里的错误写法是：

```python
return Err(SdkError("错误说明"))
```

真实例子见 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:345-417`。

### 7.2 推荐写法

```python
from plugin.sdk.plugin import Ok, Err, SdkError

@plugin_entry(...)
async def echo(self, text: str, **_):
    if not text.strip():
        return Err(SdkError("text 不能为空"))
    return Ok({"text": text})
```

### 7.3 为什么不要直接乱抛异常

入口函数更推荐把用户可理解的失败包装成 `Err(SdkError(...))` 返回，这样错误语义更稳定，也更符合项目已有模式。

---

## 8. 生命周期里通常做什么

### `startup`

常见职责：

- 读取配置
- 初始化内部状态
- 启动后台线程/任务
- 检查依赖是否可用
- 记录启动日志

`memo_reminder` 在 `startup` 里做了这些事：

- 读取配置
- 确保 store 可用
- 解析时区
- 启动 checker 线程
- 返回运行状态

见 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:189-223`。

`web_search` 在 `startup` 里做得更轻量：

- 读取配置
- 检测国家
- 设置搜索后端

见 `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:255-269`。

### `shutdown`

常见职责：

- 停止线程或后台任务
- 清理资源
- 记录关闭日志

参考：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:225-232`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:271-274`

---

## 9. 持久化存储怎么做

如果插件需要保存长期状态，先在 `plugin.toml` 中打开：

```toml
[plugin.store]
enabled = true
```

示例见：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/plugin.toml:19-25`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/qq_auto_reply/plugin.toml:16-22`

当前仓库里最完整的 store 使用范例是 `memo_reminder`：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:140-175`
- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:195-204`

它使用了：

- `self.store.enabled`
- `self.store._read_value(...)`
- `self.store._write_value(...)`

例如它自己封装了同步读写：

```python
def _store_get_sync(self, key: str, default=None):
    return self.store._read_value(key, default)

def _store_set_sync(self, key: str, value):
    self.store._write_value(key, value)
```

注意：

 `_read_value/_write_value` 偏底层接口。写文档和写插件时，建议把它理解为“现有实践”，而不是假设它是未来永远不变的唯一官方接口。

---

## 10. 动态入口怎么做

如果你的插件需要在运行时按条件注册入口，而不是在类定义时全部写死，可以使用动态入口能力。

SDK 实现在：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/base.py:177-223`

可用方法：

- `self.register_dynamic_entry(...)`
- `self.unregister_dynamic_entry(...)`

最小实际例子在：

- `https://github.com/Project-N-E-K-O/N.E.K.O/plugin_test_dynamic_entry_fixture.py:8-29`

示例模式：

```python
@lifecycle(id="startup")
async def on_startup(self) -> None:
    async def _late_entry(**_: object) -> dict[str, object]:
        return {"ok": True, "source": "dynamic"}

    self.register_dynamic_entry(
        "late_entry",
        _late_entry,
        name="Late Entry",
        timeout=1.0,
    )
```

适合场景：

- 运行后才知道有哪些能力可以暴露
- 外部服务连接成功后再注册入口
- 按配置切换功能集合

---

## 11. 最小可运行插件模板

下面这个模板尽量贴近当前仓库真实风格。

### 11.1 `plugin.toml`

```toml
[plugin]
name = "示例插件"
description = "一个最小可运行的 N.E.K.O 插件"
version = "0.1.0"
id = "example_plugin"
entry = "plugin.plugins.example_plugin:ExamplePlugin"

[plugin.author]
name = "Your Name"

[plugin.sdk]
recommended = ">=0.1.0,<0.2.0"
supported = ">=0.1.0,<0.3.0"

[plugin_runtime]
enabled = true
auto_start = true

[plugin.store]
enabled = false

[example_plugin]
default_text = "hello"
```

### 11.2 `__init__.py`

```python
from __future__ import annotations

from typing import Any, Dict

from plugin.sdk.plugin import (
    NekoPluginBase,
    neko_plugin,
    plugin_entry,
    lifecycle,
    Ok,
    Err,
    SdkError,
)


@neko_plugin
class ExamplePlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg: Dict[str, Any] = {}

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump(timeout=5.0)
        cfg = cfg if isinstance(cfg, dict) else {}
        self._cfg = cfg.get("example_plugin") if isinstance(cfg.get("example_plugin"), dict) else {}
        self.logger.info("ExamplePlugin started")
        return Ok({"status": "running"})

    @lifecycle(id="shutdown")
    async def shutdown(self, **_):
        self.logger.info("ExamplePlugin shutdown")
        return Ok({"status": "shutdown"})

    @plugin_entry(
        id="echo",
        name="回显",
        description="返回传入文本",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要回显的文本"},
            },
            "required": ["text"],
        },
    )
    async def echo(self, text: str, **_):
        if not text or not text.strip():
            return Err(SdkError("text 不能为空"))

        return Ok({
            "text": text,
            "plugin_id": self.plugin_id,
        })
```

---

## 12. 进阶模板：配置 + 日志 + store

如果你要做的是稍复杂的插件，可以在最小模板基础上增加配置和持久化。

```python
from __future__ import annotations

from typing import Any, Dict

from plugin.sdk.plugin import (
    NekoPluginBase,
    neko_plugin,
    plugin_entry,
    lifecycle,
    Ok,
    Err,
    SdkError,
)


@neko_plugin
class AdvancedPlugin(NekoPluginBase):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.file_logger = self.enable_file_logging(log_level="INFO")
        self.logger = self.file_logger
        self._cfg: Dict[str, Any] = {}

    def _store_get(self, key: str, default: Any = None) -> Any:
        if not self.store.enabled:
            return default
        return self.store._read_value(key, default)

    def _store_set(self, key: str, value: Any) -> None:
        if not self.store.enabled:
            raise SdkError("store 未启用")
        self.store._write_value(key, value)

    @lifecycle(id="startup")
    async def startup(self, **_):
        cfg = await self.config.dump(timeout=5.0)
        cfg = cfg if isinstance(cfg, dict) else {}
        self._cfg = cfg.get("advanced_plugin") if isinstance(cfg.get("advanced_plugin"), dict) else {}
        self.logger.info("AdvancedPlugin started with cfg={}", self._cfg)
        return Ok({"status": "running"})

    @plugin_entry(
        id="save_value",
        name="保存值",
        description="保存一个键值对到插件存储",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {},
            },
            "required": ["key", "value"],
        },
    )
    async def save_value(self, key: str, value: Any, **_):
        if not key.strip():
            return Err(SdkError("key 不能为空"))
        self._store_set(key, value)
        return Ok({"saved": True, "key": key})
```

这个模板的思路来自 `memo_reminder`，但做了最小化处理，方便你按需改造。

---

## 13. 编写插件时的实用建议

### 13.1 先抄仓库里已有模式，不要先发明新模式

最稳的做法是先参考现有插件：

- 配置读取：看 `web_search`
- store：看 `memo_reminder`
- HTTP API 插件：看 `dg_lab_hub`
- 大型业务插件：看 `qq_auto_reply`

### 13.2 插件入口尽量统一返回 `Ok/Err`

这样和现有插件行为一致，也方便宿主处理。

### 13.3 `entry` 路径一定要核对

这是最容易写错的地方：

- `plugin.toml` 写的是模块路径 + 类名
- 你的类必须真的存在
- 类必须继承 `NekoPluginBase`
- 类上必须有 `@neko_plugin`

### 13.4 配置段名不要乱取

推荐直接用插件 ID，或者至少保持强关联。例如：

- `memo_reminder` → `[memo]`
- `web_search` → `[search]`

你要是打算长期维护，最好别让配置段名和插件本身毫无关联。

---

## 14. 验证你的插件

至少做这几步检查：

1. 检查 `plugin.toml` 的 `entry` 是否能正确指向类。
2. 检查类是否继承 `NekoPluginBase`，且加了 `@neko_plugin`。
3. 检查所有 `@plugin_entry` 的 `input_schema` 是否和函数参数一致。
4. 检查 `startup` / `shutdown` 是否符合实际初始化、清理需求。
5. 如果插件启用了 store，确认 `[plugin.store].enabled = true`。
6. 检查配置读取的命名空间是否和 `plugin.toml` 一致。

如果只是先做基础语法验证，至少可以对插件文件执行：

```bash
python -m py_compile path/to/your_plugin/__init__.py
```

如果你已经接入了 N.E.K.O 的实际插件加载流程，再做一次真实加载和调用验证会更稳。

---

## 15. 推荐阅读顺序

如果你第一次接触这个项目，建议按这个顺序读源码：

1. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/__init__.py:7-125`
2. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/decorators.py:52-131`
3. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/sdk/plugin/base.py:23-83`
4. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/web_search/__init__.py:244-417`
5. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/plugins/memo_reminder/__init__.py:128-232`
6. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin_test_dynamic_entry_fixture.py:8-29`
7. `https://github.com/Project-N-E-K-O/N.E.K.O/plugin/_types/result.py:37-177`

读完这些，再写你的第一个插件，基本就不会偏离项目现状。
