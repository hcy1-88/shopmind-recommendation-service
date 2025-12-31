"""
@File       : main.py
@Description:

@Time       : 2025/12/31 22:48
@Author     : hcy18
"""
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import Request
from starlette import status
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.config.nacos_client import init_nacos, get_nacos_client
from app.config.settings import get_settings
from app.middleware.trace_middleware import TraceIDMiddleware
from app.schemas.result_context import ResultContext
from app.services.embedding_service import init_embedding_service
from app.store.milvus_client import init_milvus, MilvusClient
from app.utils.logger import setup_logging, app_logger as logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    try:
        # Get settings first
        settings = get_settings()

        # Setup logging (必须在记录日志之前配置)
        log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
        setup_logging(log_level=log_level)  # 使用关键字参数确保正确传递 level

        logger.info("正在启动 Shopmind AI service...")

        # nacos 初始化
        await init_nacos(settings)


        # 初始化 Embedding 服务
        init_embedding_service()

        # 初始化 Milvus
        init_milvus()

        logger.info("Shopmind Recommendation service 启动成功！")

        # ===== 新增：打印服务启动 Banner =====
        service_name = "ShopMind Recommendation Service"
        host = settings.service_ip
        port = settings.service_port
        url = f"http://{host}:{port}"

        banner = f"""
        {'=' * 60}
        🚀 {service_name} 已启动！
        🔗 访问地址: {url}
        🌐 Host: {host}
        🚪 Port: {port}
        {'=' * 60}
        """
        print(banner, file=sys.stderr)

    except Exception as e:
        logger.error(f"Failed to start Recommendation service: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down Recommendation service...")

    try:
        # 注销 from Nacos
        nacos_client = get_nacos_client()
        await nacos_client.deregister_service()
        logger.info("Nacos service deregistered")

        # Close Milvus
        milvus_client = MilvusClient.get_instance()
        await milvus_client.close()
        logger.info("Milvus closed")

        logger.info("Shopmind Recommendation service 已关闭...")

    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


app = FastAPI(
    title="ShopMind Recommendation Service",
    description="Shopmind 推荐服务",
    version="0.1.0",
    lifespan=lifespan,
)

# Add TraceID middleware (必须在 CORS 之前，以便尽早设置 traceId)
app.add_middleware(TraceIDMiddleware)

# Add CORS middleware 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors."""
    logger.warning(
        "Request validation error",
        extra={
            "path": request.url.path,
            "errors": exc.errors(),
        },
    )
    result = ResultContext.fail(
        message="请求参数验证失败",
        code="VALIDATION_ERROR",
        data={"errors": exc.errors()},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=result.model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "error": str(exc),
        },
        exc_info=True,
    )
    result = ResultContext.fail(
        message=f"内部服务器错误: {str(exc)}",
        code="SYS9999",
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=result.model_dump(),
    )


# Include routers
# app.include_router(ai_product_router.router)


# Root endpoint
@app.get("/", tags=["Root"], response_model=ResultContext[dict])
async def root() -> ResultContext[dict]:
    """Root endpoint."""
    return ResultContext.ok(
        data={
            "service": "shopmind-recommendation-service",
            "version": "0.1.0",
            "status": "running",
        },
        message="服务运行中",
    )


# Health check endpoint
@app.get("/health", tags=["Health"], response_model=ResultContext[dict])
async def health() -> ResultContext[dict]:
    """Health check endpoint."""
    return ResultContext.ok(
        data={
            "status": "healthy",
            "service": "shopmind-recommendation-service",
        },
        message="服务健康",
    )


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.service_ip,
        port=settings.service_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        http="h11"
    )