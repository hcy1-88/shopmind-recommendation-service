"""
商品搜索功能测试脚本

使用方法：
    python test_search.py
"""
import asyncio
import httpx


async def test_product_search():
    """测试商品搜索接口"""
    base_url = "http://localhost:8000"
    
    print("=" * 60)
    print("商品语义搜索测试")
    print("=" * 60)
    
    # 测试场景
    test_cases = [
        {
            "keyword": "女士连衣裙",
            "page_number": 1,
            "page_size": 5,
            "description": "测试服饰搜索"
        },
        {
            "keyword": "iPhone手机",
            "page_number": 1,
            "page_size": 10,
            "description": "测试数码产品搜索"
        },
        {
            "keyword": "运动鞋",
            "page_number": 2,
            "page_size": 5,
            "description": "测试分页（第2页）"
        }
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i, test_case in enumerate(test_cases, 1):
                print(f"\n{'=' * 60}")
                print(f"测试用例 {i}: {test_case['description']}")
                print(f"{'=' * 60}")
                
                # 发送搜索请求
                response = await client.get(
                    f"{base_url}/recommend/products/search",
                    params={
                        "keyword": test_case["keyword"],
                        "pageNumber": test_case["page_number"],
                        "pageSize": test_case["page_size"]
                    },
                    headers={
                        "X-Trace-ID": f"test-search-{i}"
                    }
                )
                
                print(f"状态码: {response.status_code}")
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"成功: {result.get('success')}")
                    print(f"消息: {result.get('message')}")
                    
                    if result.get('data'):
                        page_result = result['data']
                        print(f"\n分页信息:")
                        print(f"  - 总记录数: {page_result.get('total')}")
                        print(f"  - 当前页码: {page_result.get('pageNumber')}")
                        print(f"  - 每页大小: {page_result.get('pageSize')}")
                        print(f"  - 当前页商品数: {len(page_result.get('data', []))}")
                        
                        products = page_result.get('data', [])
                        if products:
                            print(f"\n前 3 个商品:")
                            for j, product in enumerate(products[:3], 1):
                                print(f"    {j}. {product.get('name')} (ID: {product.get('id')}, 价格: ¥{product.get('price')})")
                else:
                    print(f"请求失败: {response.text}")
            
            print(f"\n{'=' * 60}")
            print("✅ 所有测试完成！")
            
    except httpx.ConnectError:
        print("\n❌ 连接失败: 请确保推荐服务已启动 (http://localhost:8000)")
    except httpx.TimeoutException:
        print("\n❌ 请求超时: 服务响应时间过长")
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")


async def test_search_edge_cases():
    """测试边界情况"""
    base_url = "http://localhost:8000"
    
    print("\n" + "=" * 60)
    print("边界情况测试")
    print("=" * 60)
    
    edge_cases = [
        {
            "keyword": "不存在的商品xyz123",
            "description": "搜索不存在的商品"
        },
        {
            "keyword": "手机",
            "page_number": 100,
            "description": "超出范围的页码"
        }
    ]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for i, test_case in enumerate(edge_cases, 1):
                print(f"\n边界测试 {i}: {test_case['description']}")
                
                response = await client.get(
                    f"{base_url}/recommend/products/search",
                    params={
                        "keyword": test_case["keyword"],
                        "pageNumber": test_case.get("page_number", 1),
                        "pageSize": 10
                    }
                )
                
                result = response.json()
                print(f"状态码: {response.status_code}")
                print(f"成功: {result.get('success')}")
                
                if result.get('data'):
                    page_result = result['data']
                    print(f"返回商品数: {len(page_result.get('data', []))}")
                    print(f"总记录数: {page_result.get('total')}")
    
    except Exception as e:
        print(f"边界测试异常: {str(e)}")


def main():
    """主函数"""
    print("\n选择测试方式:")
    print("1. 基础功能测试")
    print("2. 边界情况测试")
    print("3. 全部测试")
    
    choice = input("\n请选择 (1/2/3，默认 1): ").strip() or "1"
    
    if choice == "1":
        asyncio.run(test_product_search())
    elif choice == "2":
        asyncio.run(test_search_edge_cases())
    elif choice == "3":
        asyncio.run(test_product_search())
        asyncio.run(test_search_edge_cases())
    else:
        print("无效选择")


if __name__ == "__main__":
    main()

