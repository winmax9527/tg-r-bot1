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
from fastapi import FastAPI, Request # <-- 新增导入
import uvicorn # <-- 新增导入

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
    # 从 context.bot_data 中获取当前机器人的 API URL
    API_URL = context.application.bot_data.get('API_URL') # 在 FastAPI 架构中，使用 application 属性获取
    
    if not API_URL:
        await update.message.reply_text("❌ 机器人配置错误，未找到 API URL。")
        logger.error("API_URL not found in application.bot_data.")
        return
        
    await update.message.reply_text("正在为您获取最新下载链接，请稍候...")
    
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
    }
    
    domain_a = None
    final_url_b = None
    
    try:
        # ----------------------------------------------
        # 第一步: Requests 请求 API 获取 A 域名 (已修正解析逻辑)
        # ----------------------------------------------
        logger.info(f"Step 1: Requesting API URL: {API_URL}")
        api_response = requests.get(API_URL, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        data = api_response.json()
        domain_a = data.get('data') # A 域名直接位于顶级键 "data" 之下
        
        if not domain_a or not isinstance(domain_a, str):
             await update.message.reply_text(f"❌ 链接获取失败：API 响应中未找到 A 域名或格式错误。")
             logger.error(f"API response format incorrect. Data retrieved: {domain_a}")
             return

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}")
        
        # ----------------------------------------------
        # 第二步: Playwright 追踪 A 域名到 B 域名
        # ----------------------------------------------
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, timeout=15000)
            page = await browser.new_page()

            await page.goto(domain_a, wait_until="networkidle", timeout=30000) 

            final_url_b = page.url
            
            await browser.close() 

            if final_url_b and final_url_b != domain_a:
                
                # --- 核心新增逻辑：修改二级域名 (Subdomain) ---
                parsed_url = urlparse(final_url_b)
                netloc_parts = parsed_url.netloc.split('.')
                
                if len(netloc_parts) >= 2: 
                    new_subdomain = generate_random_subdomain(3, 8)
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
    except Exception as e:
        await update.message.reply_text(f"❌ 浏览器错误。请等待几分钟或联系管理员。")
        logger.error(f"Playwright Runtime Error: {e}")


# -------------------------------------------------------------
# ⭐️ 核心路由和启动逻辑 (使用 FastAPI)
# -------------------------------------------------------------

# 机器人配置列表
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

# main.py 文件中

# ... (保持 BOT_CONFIGS 列表不变) ...

# main.py 文件中

# 🚨 确保这里添加了 'async' 关键字
async def initialize_bots(): 
    """初始化并启动所有 Bot 的后台线程"""
    for config in BOT_CONFIGS:
        token = config['token']
        # 键名已修复为 'api_url'
        api_url = config['api_url'] 
        path = config['path']

        if token and api_url:
            application = Application.builder().token(token).build()
            application.bot_data['API_URL'] = api_url
            
            # 注册 handler (保持不变)
            # ... (CommandHandler 和 MessageHandler 的注册代码保持不变) ...

            # ⭐️ 关键修改 1: 必须在启动前执行异步初始化
            await application.initialize() 
            
            # ⭐️ 关键修改 2: 启动后台任务
            # 我们只需要 application.start()，不需要 run_polling
            asyncio.create_task(application.start()) 
            
            # 存储 Application 实例
            APPLICATIONS[path] = application
            logger.info(f"Initialized bot on path /{path}")
        else:
            logger.warning(f"Skipping bot with path /{path}: TOKEN or API_URL not set.")

# --- FastAPI 初始化 ---
app = FastAPI()

# ⭐️ 核心修改：使用 FastAPI 的生命周期事件来启动异步任务
# main.py 文件中

# main.py 文件中 (startup_event 函数的定义)

@app.on_event("startup")
async def startup_event():
    # ⭐️ 必须 await：等待 initialize_bots 完成所有初始化
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
        
        # 将 Update 对象放入 Application 的更新队列中
        await application.update_queue.put(update)
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing update for /{path_suffix}: {e}")
        return {"status": "error", "message": str(e)}

# ----------------------------------------------
# 启动脚本
# ----------------------------------------------
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    # Render 会执行这个 uvicorn 命令来启动服务
    uvicorn.run(app, host="0.0.0.0", port=PORT)
