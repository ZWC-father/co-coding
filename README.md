# Co-coding
一个简单的LLM合作开发系统，使用简化的提示词和工作流程模拟
### Features
- 使用三个LLM分别作为需求分析、开发、测试
- 全自动开发非图形化的 python 脚本
- 自动补全依赖，运行测试
- 自动追问，以明确需求
- 防止提示词注入
- 支持OpenAI及其兼容的API平台（如deepseek）
### Limitations
- 提示词有待优化（可以考虑结合提示词工程相关理论优化或者使用自动提示工程师）
- 对于复杂的开发任务无法实现全自动（环境准备、依赖不易自动处理，且涉及到安全性问题）
- 受LLM上下文长度和**自我错误强化**的影响，开发过程可能会“跑偏”
### Tests
以下简单的开发需求都能在四次“开发-测试-修改”回合内完成(使用deepseek-chat或者deepseek-reasoner)
```
开发一个排序程序，对输入（使用空格分隔）内容排序
```
```
“Two Sum”问题要求在给定整数数组中找到两个元素，使其和等于指定目标值，并返回它们的索引。该题考察模型在数组遍历、哈希映射（Hash Map）构建及边界条件处理方面的实现能力，同时可验证时间复杂度和空间复杂度的优化
题目描述
输入：一个整数数组 nums 和一个整数 target
输出：返回数组中两个数之和等于 target 的 一对索引（任意顺序皆可），假设恰有一个合法解，且同一元素不能重复使用
```
```
帮我写脚本爬取这个网址的名言： http://quotes.toscrape.com/
目标字段：作者、名言文本、标签。
技术点：requests 获取 HTML，BeautifulSoup 定位 .quote 容器，提取 .text、.author、.tags 列表。
注意输出格式为json，只能用requests和beautifulsoup4这两个第三方库
```
```
输入：字符串 s 和模式串 p，其中 p 仅包含小写字母、. 和 *。
规则：
. 匹配任意单个字符。
* 匹配它之前的元素 0 次或多次。
匹配必须覆盖整个字符串（不允许部分匹配）。 
输出：返回布尔值，表示模式 p 是否能完全匹配字符串 s。
```
```
任务描述
请编写一个 Python 装饰器 @redis_cache(ttl)，用于缓存任意函数的调用结果到 Redis，并满足以下功能：
连接 Redis：使用 redis-py 客户端连接到本地或远程 Redis 实例。

生成缓存键：根据被装饰函数的名称及其位置参数和关键字参数，生成唯一的缓存键。
设置过期时间：在写入 Redis 时，为键设置可配置的 TTL（通过 SET 命令的 EX 参数或 SETEX 命令）。

缓存逻辑：
命中：若 Redis 中存在对应键，则直接反序列化并返回缓存值。
未命中：调用原函数获取结果，将结果序列化后写入 Redis，并返回该结果。

手动失效：提供一个辅助函数 invalidate_cache(func, *args, **kwargs)，用于删除指定函数调用对应的缓存键。
```
```
题目：FastAPI + HTTP Basic Auth 简易 API 服务器
功能描述:
用户注册
接口：POST /register
请求参数：username、password（明文）
实现要求：将用户名与 bcrypt 哈希后的密码存入内存字典（或 SQLite），拒绝重复注册

受保护资源:
接口：GET /items/ 和 POST /items/
认证方式：使用 FastAPI 内置的 HTTPBasic 方案，从请求头中解析 Authorization: Basic ... 并校验用户名/密码

功能：
GET /items/：返回当前用户的所有“待办事项”列表（内存存储）。
POST /items/：接收 JSON { "item": "..." }，将其追加到当前用户的待办列表中，并返回最新列表

密码校验:
使用 passlib.hash.bcrypt 对注册密码进行哈希，并在每次认证时使用 bcrypt.verify 校验

错误处理:
认证失败或未提供 Basic 认证头时，返回 HTTP 401 并包含 WWW-Authenticate: Basic，提示客户端使用 Basic Auth

重复注册返回 HTTP 400；访问不存在的资源返回 HTTP 404。
```
