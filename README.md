# ShopMind Recommendation Service

基于向量检索的电商推荐与搜索服务，提供个性化推荐、相似商品推荐和语义搜索重排序功能。

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| 语言 | Python 3.12+ |
| 向量数据库 | Milvus |
| 缓存 | Redis |
| 配置中心 | Nacos |
| Embedding | 阿里云百炼 (dashscope) |
| 依赖管理 | uv |
| 异步客户端 | httpx |

## 核心功能

### 1. 个性化推荐
基于用户行为数据、兴趣标签和搜索关键词生成个性化商品推荐。

- **行为向量**：根据用户浏览、点赞、收藏、加购、购买等行为，按权重加权计算
- **兴趣向量**：基于用户兴趣标签生成向量
- **搜索向量**：基于用户搜索关键词生成向量

### 2. 相似商品推荐
根据当前商品向量，推荐相似度最高的相关商品。

适用于商品详情页"看了又看"、"相关推荐"等场景。

### 3. 语义搜索重排序
对关键词搜索结果进行语义相似度重排序，提升搜索相关性。

## 推荐策略

```
用户请求
    │
    ├─► 有缓存向量？ ──是──► 使用缓存推荐
    │
    └─► 无缓存
          │
          ├─► 行为数 ≥ 3 或有兴趣/搜索 ──► 个性化推荐
          │
          └─► 无足够数据 ──► 热门商品（冷启动）
```

- **行为权重**：购买(3.0) > 加购物车(2.5) > 点赞(2.0) > 分享(1.5) > 浏览(1.0)
- **向量融合**：行为向量(0.6) + 兴趣向量(0.4)

## API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/recommend` | GET | 个性化商品推荐 |
| `/recommend/products/recommendations` | GET | 相似商品推荐 |
| `/recommend/search/semantic` | POST | 语义搜索重排序 |
| `/health` | GET | 健康检查 |

### 个性化推荐示例

```bash
curl "http://localhost:8086/recommend?userId=1&limit=10"
```

### 相似商品推荐示例

```bash
curl "http://localhost:8086/recommend/products/recommendations?productId=123&limit=10"
```

### 语义搜索示例

```bash
curl -X POST "http://localhost:8086/recommend/search/semantic" \
  -H "Content-Type: application/json" \
  -d '{
    "keyword": "夏季连衣裙",
    "limit": 10,
    "productIds": [1, 2, 3]
  }'
```

## 项目结构

```
src/app/
├── api/                    # API 路由
│   ├── recommendation_router.py
│   └── search_router.py
├── clients/                 # 外部服务客户端
│   ├── user_service_client.py
│   ├── product_service_client.py
│   └── redis_client.py
├── services/               # 核心业务逻辑
│   ├── recommendation_service.py
│   ├── search_service.py
│   └── embedding_service.py
├── store/                  # Milvus 向量存储
├── provider/               # Embedding 提供商
├── config/                 # 配置（Nacos）
├── middleware/             # 中间件（TraceID）
└── utils/                  # 工具类
```

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并修改配置：

```bash
cp .env.example .env
```

主要配置项：
- `NACOS_SERVER_ADDR`: Nacos 服务地址
- `SERVICE_PORT`: 服务端口

### 3. 启动服务

```bash
uv run uvicorn app.main:app --reload
```

服务启动后访问 `http://localhost:8086/docs` 查看 API 文档。

## 依赖服务

- **Milvus**: 商品向量存储
- **Redis**: 用户向量缓存
- **Nacos**: 配置中心和服务发现
- **用户服务**: 获取用户行为和兴趣
- **商品服务**: 获取商品信息