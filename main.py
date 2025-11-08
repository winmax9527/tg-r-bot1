import os
import logging
import requests 
import json 
import random 
import string 
import asyncio
from urllib.parse import urlparse, urlunparse 
from telegram import Update 
from telegram.ext import Application, MessageHandler, filters
from playwright.async_api import async_playwright
# 导入 Playwright 异常，以便精确捕获
from playwright.sync_api import Error as PlaywrightError
from fastapi import FastAPI, Request 
import uvicorn 

# --- 1. 日志配置 ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. 辅助函数：生成随机二级域名 ---
def generate_random_subdomain(min_len=3, max_len=8):
    """生成 3 到 8 位的随机字母和数字组合"""
    length = random.randint(min_len, max_len)
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))

# --- 3. 核心功能函数 (API 获取 A + Playwright 追踪 B + 随机化) ---
async def get_final_url(update: Update, context) -> None:
    # 从 context.application.bot_data 中获取当前机器人的 API URL
    API_URL = context.application.bot_data.get('API_URL')
    
    if not API_URL:
        await update.message.reply_text("❌ 机器人配置错误，未找到 API URL。")
        logger.error("API_URL not found in application.bot_data.")
        return
        
    # 立即发送回复，防止 Playwright 启动慢导致 Telegram 重试
    await update.message.reply_text("正在为您获取最新下载链接，请稍候...")
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    domain_a = None
    final_url_b = None
    
    # ⭐️ 最终优化：最精简的 Chromium 启动参数，只保留必需的
    CHROMIUM_ARGS = [
        '--no-sandbox', 
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage', # 解决 /dev/shm 内存不足问题
        '--single-process', # 强制单进程模式，减少资源消耗
        '--disable-gpu', # 禁用 GPU 加速
        '--disable-software-rasterizer', # 禁用软件光栅化
        '--disable-extensions', # 禁用扩展
        '--mute-audio', # 禁用音频
        '--window-size=1280,1024' # 设定固定窗口大小
    ]
    
    # ⭐️ 最终优化：直接使用 Render 容器中 Playwright 依赖的路径
    # 这比使用环境变量更直接
    PLAYWRIGHT_EXECUTABLE_PATH = "/usr/bin/chromium" 
    
    try:
        # ----------------------------------------------
        # 第一步: Requests 请求 API 获取 A 域名
        # ----------------------------------------------
        logger.info(f"Step 1: Requesting API URL: {API_URL}")
        # 保持 5 秒超时不变
        api_response = requests.get(API_URL, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        data = api_response.json()
        # A 域名直接位于顶级键 "data" 之下
        domain_a = data.get('data') 
        
        if not domain_a or not isinstance(domain_a, str):
            await update.message.reply_text(f"❌ 链接获取失败：API 响应中未找到 A 域名或格式错误。")
            logger.error(f"API response format incorrect. Data retrieved: {domain_a}")
            return

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}")
        
        # ----------------------------------------------
        # 第二步: Playwright 追踪 A 域名到 B 域名 (异步)
        # ----------------------------------------------
        async with async_playwright() as p:
            logger.info("Step 3: Attempting to launch Chromium with minimal args...")
            
            launch_options = {
                'headless': True, 
                # 保持启动超时时间 20 秒
                'timeout': 20000,
                'args': CHROMIUM_ARGS,
                # ⭐️ 关键修改：强制设置执行路径
                'executable_path': PLAYWRIGHT_EXECUTABLE_PATH
            }
            
            logger.info(f"Using executable path: {PLAYWRIGHT_EXECUTABLE_PATH}")
            
            browser = await p.chromium.launch(**launch_options)
            page = await browser.new_page()

            # 🚀 最终优化：将 goto 超时增加到 60 秒，以应对慢速启动或跳转
            await page.goto(domain_a, wait_until="domcontentloaded", timeout=60000) 

            final_url_b = page.url
            
            await browser.close() 
            logger.info("Step 4: Browser closed.")

            if final_url_b and final_url_b != domain_a:
                
                # --- 第三步: 核心新增逻辑：修改二级域名 (Subdomain) ---
                parsed_url = urlparse(final_url_b)
                netloc_parts = parsed_url.netloc.split('.')
                
                if len(netloc_parts) >= 2: 
                    new_subdomain = generate_random_subdomain(3, 8)
                    # 替换第一个部分（通常是二级域名）
                    netloc_parts[0] = new_subdomain 
                    new_netloc = '.'.join(netloc_parts)
                    modified_url_b = urlunparse(parsed_url._replace(netloc=new_netloc))

                    await update.message.reply_text(f"✅ 本次最新下载链接是：\n{modified_url_b}")
                    logger.info(f"Success! Final URL B (modified): {modified_url_b}")
                else:
                    await update.message.reply_text(f"✅ 本次最新下载链接是：\n{final_url_b}")
                    logger.warning(f"URL structure not suitable for subdomain replacement. Returning original URL.")
            else:
                await update.message.reply_text(f"⚠️ Playwright 未检测到跳转。当前URL: {final_url_b}")
                logger.warning(f"Playwright finished, but no redirect detected. Final URL: {final_url_b}")

    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ API 请求失败，出现网络错误或超时。")
        logger.error(f"API Request Error: {e}")
    except json.JSONDecodeError:
        await update.message.reply_text(f"❌ API 返回的不是有效的 JSON 格式。请检查 API 接口。")
        logger.error(f"JSON Decode Error in API response.")
    # ⭐️ 关键修改：捕获 Playwright 相关的异常并转换为字符串
    except PlaywrightError as e:
        error_message = str(e)
        # 确保回复给用户的消息包含关键错误信息，以便诊断
        await update.message.reply_text(f"❌ 浏览器组件错误。请联系管理员，错误详情：{error_message[:100]}...")
        logger.error(f"Playwright Runtime Error: {error_message}")
    except Exception as e:
        # 捕获所有其他意外错误
        await update.message.reply_text(f"❌ 发生了意外错误。请联系管理员。")
        logger.error(f"Unexpected Runtime Error: {e}")


# -------------------------------------------------------------
# ⭐️ Bot 配置和初始化 (此部分未修改)
# -------------------------------------------------------------

# 机器人配置列表 (使用环境变量)
BOT_CONFIGS = [
    {
        "token": os.environ.get("BOT_1_TOKEN"),
        "api_url": os.environ.get("BOT_1_API"),
        "path": "bot1_webhook"
    },
    {
        "token": os.environ.get("BOT_4_TOKEN"),
        "api_url": os.environ.get("BOT_4_API"),
        "path": "bot4_webhook"
    },
    {
        "token": os.environ.get("BOT_6_TOKEN"),
        "api_url": os.environ.get("BOT_6_API"),
        "path": "bot6_webhook"
    },
    {
        "token": os.environ.get("BOT_9_TOKEN"),
        "api_url": os.environ.get("BOT_9_API"),
        "path": "bot9_webhook"
    }
    # 根据需要添加更多机器人
]

# 全局存储应用实例，便于 FastAPI 路由查找
APPLICATIONS = {}

# 核心初始化函数，必须是 async 且在 startup_event 中 await
async def initialize_bots(): 
    """初始化并启动所有 Bot 的后台线程"""
    for config in BOT_CONFIGS:
        token = config['token']
        # 修正的键名
        api_url = config['api_url'] 
        path = config['path']

        if token and api_url:
            application = Application.builder().token(token).build()
            application.bot_data['API_URL'] = api_url
            
            # 注册 handler
            COMMAND_PATTERN = r"^(地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
            application.add_handler(
                MessageHandler(
                    filters.TEXT & filters.Regex(COMMAND_PATTERN), 
                    get_final_url
                )
            )

            # 关键：在启动前执行异步初始化
            await application.initialize() 
            
            # 关键：在后台任务中启动，不进行 Polling，只处理队列
            asyncio.create_task(application.start()) 
            
            # 存储 Application 实例
            APPLICATIONS[path] = application
            logger.info(f"Initialized bot on path /{path}")
        else:
            logger.warning(f"Skipping bot with path /{path}: TOKEN or API_URL not set.")

# --- FastAPI 初始化 ---
app = FastAPI()

# ⭐️ 关键修复：添加根路径健康检查路由
@app.get("/")
async def root():
    """Render Health Check endpoint."""
    return {"status": "ok", "message": "Bot service is running"}

# ⭐️ 核心修复：使用 FastAPI 的生命周期事件来启动异步任务
@app.on_event("startup")
async def startup_event():
    # 必须 await initialize_bots，确保 Bot 初始化在 Uvicorn 循环内完成
    await initialize_bots()

# ----------------------------------------------
# ⭐️ Webhook 路由函数 (处理所有 POST 请求)
# ----------------------------------------------
@app.post("/{path_suffix}")
async def telegram_webhook(path_suffix: str, request: Request):
    
    # 查找对应路径的 Application 实例
    application = APPLICATIONS.get(path_suffix)
    if not application:
        logger.warning(f"Webhook received for unknown path: /{path_suffix}")
        return {"status": "error", "message": "Unknown path"}

    # 解析请求体并将其放入 Bot 的更新队列
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        
        # 将 Update 对象放入 Application 的更新队列中，由后台 task 处理
        await application.update_queue.put(update)
        
        # 立即返回 200 OK，告诉 Telegram 消息已接收
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update for /{path_suffix}: {e}")
        # 返回 200，但带有错误信息，防止 Telegram 重试
        return {"status": "error", "message": str(e)} 

# ----------------------------------------------
# 启动脚本
# ----------------------------------------------
if __name__ == "__main__":
    # 此块仅用于本地测试或兼容性，Render 应当使用 uvicorn main:app 启动
    PORT = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=PORT)
