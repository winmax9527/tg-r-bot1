import os
import logging
import json 
import random 
import string 
import asyncio
import re
from urllib.parse import urlparse, urlunparse 

# 导入 Playwright
# ⭐️ 关键修改：导入同步和异步 run 方法
from playwright.async_api import async_playwright, run as playwright_run
import requests 

from telegram import Update 
# ⭐️ 修复：我们只在初始化时需要 Application，但在主流程中不需要它，但保留 Update 和 MessageHandler
from telegram.ext import Application, MessageHandler, filters
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

# -------------------------------------------------------------
# ⭐️ 核心功能函数 (使用 Playwright 获取 B 域名)
# -------------------------------------------------------------

# ⭐️ 修复方法：将 Playwright 逻辑封装在一个同步函数中，并使用 playwright_run 启动异步部分
def resolve_url_sync(api_url):
    """同步启动 Playwright 异步环境来解决 URL"""
    return playwright_run(resolve_url_async(api_url))

async def resolve_url_async(api_url):
    """Playwright 的异步逻辑部分"""
    domain_a = None
    final_url_b = None
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    try:
        # 第一步: Requests 请求 API 获取 A 域名
        api_response = requests.get(api_url, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        data = api_response.json()
        domain_a = data.get('data') 
        
        if not domain_a or not isinstance(domain_a, str):
            logger.error(f"API response format incorrect. Data retrieved: {domain_a}")
            return None, "❌ 链接获取失败：API 响应中未找到 A 域名或格式错误。"

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}. Starting dynamic parsing (Playwright).")
        
        # 第二步: 使用 Playwright 动态解析跳转链接
        async with async_playwright() as p:
            # ⭐️ 关键：禁用沙盒以确保 Render 上的兼容性
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox']) 
            page = await browser.new_page()
            
            await page.goto(domain_a, wait_until="networkidle", timeout=15000)
            
            final_url_b = page.url
            
            await browser.close()
            
        logger.info(f"Playwright navigated to final URL: {final_url_b}")
        
        # 第三步: 随机化二级域名 (与之前逻辑相同)
        if final_url_b.startswith("http"): 
            parsed_url = urlparse(final_url_b)
            netloc_parts = parsed_url.netloc.split('.')
            
            if final_url_b != domain_a and len(netloc_parts) >= 2: 
                new_subdomain = generate_random_subdomain(3, 8)
                netloc_parts[0] = new_subdomain 
                modified_url_b = urlunparse(parsed_url._replace(netloc=new_netloc))

                return modified_url_b, f"✅ 本次最新下载链接是：\n{modified_url_b}"
            else:
                return final_url_b, f"✅ 本次最新下载链接是：\n{final_url_b}"
        else:
            return domain_a, f"⚠️ Playwright 解析失败，返回原始链接：\n{domain_a}"


    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request Error: {req_err}")
        return None, f"❌ 网络请求或 API 失败，请检查 API 接口。"
    except Exception as e:
        logger.error(f"Playwright Runtime Error: {e}")
        # ⭐️ 优化错误信息
        return None, f"❌ Playwright 浏览器组件错误。请联系管理员。错误详情: {e.__class__.__name__}"


async def get_final_url(update: Update, context) -> None:
    # 直接使用单机器人的 API_URL
    API_URL = context.application.bot_data.get('API_URL')
    
    if not API_URL:
        await update.message.reply_text("❌ 机器人配置错误，未找到 API URL。")
        logger.error("API_URL not found in application.bot_data.")
        return
        
    # 立即发送回复，这是防止 Telegram 超时的关键
    await update.message.reply_text("正在为您获取最新下载链接，请稍候...")
    
    # ⭐️ 关键调用：使用 asyncio.to_thread 在后台运行同步 Playwright 逻辑
    final_url, reply_message = await asyncio.to_thread(resolve_url_sync, API_URL)
    
    # 发送最终结果
    await update.message.reply_text(reply_message)


# -------------------------------------------------------------
# ⭐️ 单 Bot 配置和初始化 (使用 BOT_2 环境变量)
# -------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_2_TOKEN") 
API_URL = os.environ.get("BOT_2_API")     
WEBHOOK_PATH = "webhook"                  # 简化的 webhook 路径

# 单机器人实例
application = None

async def initialize_single_bot(): 
    """初始化并启动单个 Bot"""
    global application

    if BOT_TOKEN and API_URL:
        # 使用 Application 提供的 builder
        application = Application.builder().token(BOT_TOKEN).build()
        application.bot_data['API_URL'] = API_URL
        
        COMMAND_PATTERN = r"^(地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
        application.add_handler(
            MessageHandler(
                filters.TEXT & filters.Regex(COMMAND_PATTERN), 
                get_final_url
            )
        )

        await application.initialize() 
        # ⭐️ 修复：如果使用 FastAPI 处理 Webhook，则不需要 application.start()，只需 application.updater.start_polling() 或设置 Webhook。
        # 由于我们使用 FastAPI 路由 /webhook，这里我们只需要 application.start() 来启动内部调度器。
        asyncio.create_task(application.start()) 
        logger.info(f"Initialized single bot on path /{WEBHOOK_PATH} using BOT_2 config.")
    else:
        logger.error(f"BOT_2_TOKEN or BOT_2_API not set. Cannot run single bot.")

app = FastAPI()

@app.get("/")
async def root():
    """Render Health Check endpoint."""
    if application:
        return {"status": "ok", "message": f"Bot service running on /{WEBHOOK_PATH}"}
    else:
        return {"status": "error", "message": "Bot not initialized due to missing env vars"}


@app.on_event("startup")
async def startup_event():
    # ⭐️ 启动时初始化 Bot
    await initialize_single_bot()

@app.post(f"/{WEBHOOK_PATH}")
async def telegram_webhook(request: Request):
    if not application:
        logger.error("Application not initialized.")
        return {"status": "error", "message": "Application not initialized"}

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        # 将 Update 放入队列，让 Bot 的内部调度器处理
        await application.update_queue.put(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return {"status": "error", "message": str(e)} 

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    # ⭐️ 修复：启动 FastAPI 应用，不再直接启动 Bot 
    uvicorn.run(app, host="0.0.0.0", port=PORT)import os
import logging
import json 
import random 
import string 
import asyncio
import re
from urllib.parse import urlparse, urlunparse 

# 导入 Playwright
from playwright.async_api import async_playwright
import requests 

from telegram import Update 
from telegram.ext import Application, MessageHandler, filters
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

# -------------------------------------------------------------
# ⭐️ 核心功能函数 (使用 Playwright 获取 B 域名)
# -------------------------------------------------------------
async def get_final_url(update: Update, context) -> None:
    # 直接使用单机器人的 API_URL
    API_URL = context.application.bot_data.get('API_URL')
    
    if not API_URL:
        await update.message.reply_text("❌ 机器人配置错误，未找到 API URL。")
        logger.error("API_URL not found in application.bot_data.")
        return
        
    # 立即发送回复，这是防止 Telegram 超时的关键
    await update.message.reply_text("正在为您获取最新下载链接，请稍候...")
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    domain_a = None
    final_url_b = None
    
    try:
        # ----------------------------------------------
        # 第一步: Requests 请求 API 获取 A 域名
        # ----------------------------------------------
        api_response = requests.get(API_URL, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        data = api_response.json()
        domain_a = data.get('data') 
        
        if not domain_a or not isinstance(domain_a, str):
            await update.message.reply_text(f"❌ 链接获取失败：API 响应中未找到 A 域名或格式错误。")
            logger.error(f"API response format incorrect. Data retrieved: {domain_a}")
            return

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}. Starting dynamic parsing (Playwright).")
        
        # ----------------------------------------------
        # 第二步: 使用 Playwright 动态解析跳转链接
        # ----------------------------------------------
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True) # 启动无头浏览器
            page = await browser.new_page()
            
            # 设置等待，给 JS 足够的时间运行并完成跳转
            # timeout=15000 确保如果加载太慢也能及时停止
            await page.goto(domain_a, wait_until="networkidle", timeout=15000)
            
            # 获取页面最终跳转到的 URL
            final_url_b = page.url
            
            await browser.close()
            
        logger.info(f"Playwright navigated to final URL: {final_url_b}")
        
        # ----------------------------------------------
        # 第三步: 随机化二级域名 (与之前逻辑相同)
        # ----------------------------------------------
        
        if final_url_b.startswith("http"): 
            parsed_url = urlparse(final_url_b)
            netloc_parts = parsed_url.netloc.split('.')
            
            # 只有找到 B 链接且 B 链接与 A 链接不同时才执行随机化
            if final_url_b != domain_a and len(netloc_parts) >= 2: 
                new_subdomain = generate_random_subdomain(3, 8)
                netloc_parts[0] = new_subdomain 
                new_netloc = '.'.join(netloc_parts)
                modified_url_b = urlunparse(parsed_url._replace(netloc=new_netloc))

                await update.message.reply_text(f"✅ 本次最新下载链接是：\n{modified_url_b}")
                logger.info(f"Success! Final URL B (modified): {modified_url_b}")
            else:
                await update.message.reply_text(f"✅ 本次最新下载链接是：\n{final_url_b}")
                logger.warning(f"URL structure not suitable for subdomain replacement or no redirect detected. Returning original final URL.")
        else:
            await update.message.reply_text(f"⚠️ Playwright 解析失败，返回原始链接：\n{domain_a}")
            logger.warning(f"Playwright returned an invalid URL: {final_url_b}")


    except requests.exceptions.RequestException as req_err:
        await update.message.reply_text(f"❌ 网络请求或 API 失败，请检查 API 接口。")
        logger.error(f"Request Error: {req_err}")
    except Exception as e:
        # 捕获 Playwright 相关的错误，例如启动失败、超时等
        await update.message.reply_text(f"❌ 浏览器组件或超时错误，请联系管理员。")
        logger.error(f"Playwright Runtime Error: {e}")


# -------------------------------------------------------------
# ⭐️ 单 Bot 配置和初始化
# -------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_1_TOKEN") # 仅使用 BOT_1 的 TOKEN
API_URL = os.environ.get("BOT_1_API")     # 仅使用 BOT_1 的 API
WEBHOOK_PATH = "webhook"                  # 简化的 webhook 路径

# 单机器人实例
application = None

async def initialize_single_bot(): 
    """初始化并启动单个 Bot"""
    global application

    if BOT_TOKEN and API_URL:
        application = Application.builder().token(BOT_TOKEN).build()
        application.bot_data['API_URL'] = API_URL
        
        COMMAND_PATTERN = r"^(地址|下载地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
        application.add_handler(
            MessageHandler(
                filters.TEXT & filters.Regex(COMMAND_PATTERN), 
                get_final_url
            )
        )

        await application.initialize() 
        asyncio.create_task(application.start()) 
        logger.info(f"Initialized single bot on path /{WEBHOOK_PATH}")
    else:
        logger.error(f"BOT_1_TOKEN or BOT_1_API not set. Cannot run single bot.")

app = FastAPI()

@app.get("/")
async def root():
    """Render Health Check endpoint."""
    if application:
        return {"status": "ok", "message": f"Bot service running on /{WEBHOOK_PATH}"}
    else:
        return {"status": "error", "message": "Bot not initialized due to missing env vars"}


@app.on_event("startup")
async def startup_event():
    await initialize_single_bot()

@app.post(f"/{WEBHOOK_PATH}")
async def telegram_webhook(request: Request):
    if not application:
        logger.error("Application not initialized.")
        return {"status": "error", "message": "Application not initialized"}

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return {"status": "error", "message": str(e)} 

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=PORT)
