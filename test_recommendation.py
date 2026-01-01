"""
测试推荐服务的示例脚本

使用方法：
    python test_recommendation.py
"""
import asyncio
import httpx


async def test_recommendation_api():
    """测试推荐接口"""
    base_url = "http://localhost:8000"
    
    print("=" * 60)
    print("ShopMind 推荐服务测试")
    print("=" * 60)
    
    # 测试参数
    user_id = 123
    limit = 10
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. 测试健康检查
            print("\n1️⃣ 测试健康检查...")
            response = await client.get(f"{base_url}/health")
            print(f"   状态码: {response.status_code}")
            print(f"   响应: {response.json()}")
            
            # 2. 测试完整推荐接口
            print("\n2️⃣ 测试完整推荐接口 (GET /recommend)...")
            response = await client.get(
                f"{base_url}/recommend",
                params={"userId": user_id, "limit": limit}
            )
            print(f"   状态码: {response.status_code}")
            result = response.json()
            print(f"   成功: {result.get('success')}")
            print(f"   消息: {result.get('message')}")
            
            if result.get('data'):
                data = result['data']
                print(f"   推荐策略: {data.get('strategy')}")
                print(f"   商品数量: {data.get('total')}")
                
                products = data.get('products', [])
                if products:
                    print(f"\n   前 3 个推荐商品:")
                    for i, product in enumerate(products[:3], 1):
                        print(f"     {i}. {product.get('name')} (ID: {product.get('id')}, 价格: ¥{product.get('price')})")
            
            # 3. 测试简化推荐接口
            print("\n3️⃣ 测试简化推荐接口 (GET /recommend/products)...")
            response = await client.get(
                f"{base_url}/recommend/products",
                params={"userId": user_id, "limit": limit}
            )
            print(f"   状态码: {response.status_code}")
            result = response.json()
            print(f"   成功: {result.get('success')}")
            print(f"   消息: {result.get('message')}")
            
            if result.get('data'):
                products = result['data']
                print(f"   商品数量: {len(products)}")
            
            print("\n✅ 测试完成！")
            
    except httpx.ConnectError:
        print("\n❌ 连接失败: 请确保推荐服务已启动 (http://localhost:8000)")
    except httpx.TimeoutException:
        print("\n❌ 请求超时: 服务响应时间过长")
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")


async def test_internal_service():
    """测试内部推荐服务（不通过 HTTP）"""
    print("\n" + "=" * 60)
    print("测试内部推荐服务")
    print("=" * 60)
    
    try:
        # 导入推荐服务
        from app.services.recommendation_service import get_recommendation_service
        
        service = get_recommendation_service()
        user_id = 123
        limit = 10
        
        print(f"\n调用推荐服务: user_id={user_id}, limit={limit}")
        products, strategy = await service.recommend(user_id=user_id, limit=limit)
        
        print(f"推荐策略: {strategy}")
        print(f"商品数量: {len(products)}")
        
        if products:
            print(f"\n前 3 个推荐商品:")
            for i, product in enumerate(products[:3], 1):
                print(f"  {i}. {product.name} (ID: {product.id}, 价格: ¥{product.price})")
        
        print("\n✅ 内部服务测试完成！")
        
    except ImportError as e:
        print(f"\n⚠️ 无法导入模块: {str(e)}")
        print("请确保在项目根目录运行此脚本")
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")


def main():
    """主函数"""
    print("\n选择测试方式:")
    print("1. 测试 HTTP API 接口（推荐）")
    print("2. 测试内部服务")
    print("3. 同时测试两种方式")
    
    choice = input("\n请选择 (1/2/3，默认 1): ").strip() or "1"
    
    if choice == "1":
        asyncio.run(test_recommendation_api())
    elif choice == "2":
        asyncio.run(test_internal_service())
    elif choice == "3":
        asyncio.run(test_recommendation_api())
        asyncio.run(test_internal_service())
    else:
        print("无效选择")


if __name__ == "__main__":
    main()

