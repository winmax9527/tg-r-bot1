import os
import logging
import requests # 用于请求 API
import json # 用于解析 API 响应
from telegram import Update 
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from playwright.async_api import async_playwright # 用于处理 JS 跳转

# --- 1. 日志配置 ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. 核心功能函数 (API 获取 A + Playwright 追踪 B) ---
async def get_final_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ⭐️ 步骤一：不变的 API 接口 (获取会变的 A 域名)
    API_URL = "https://ndbjz.dbgck.com/mapi/alink/zdm3nwuyym"
    
    await update.message.reply_text("正在为您获取最新的链接，请稍候...")
    
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
        logger.info(f"Step 1: Requesting API URL: {API_URL}")
        api_response = requests.get(API_URL, headers=HEADERS, timeout=5)
        api_response.raise_for_status() 
        
        data = api_response.json()
        
        # !!! 重要：这里需要根据实际 API 响应结构来修改 !!!
        # 假设 A 域名位于 'data' 键下的 'url' 键
        domain_a = data.get('data', {}).get('url') 
        
        if not domain_a:
             await update.message.reply_text(f"❌ 链接获取失败：API 响应中未找到 A 域名。")
             logger.error(f"API response missing A domain: {data}")
             return

        logger.info(f"Step 2: Successfully retrieved Domain A: {domain_a}")
        
        # ----------------------------------------------
        # 第二步: Playwright 追踪 A 域名到 B 域名
        # ----------------------------------------------
        async with async_playwright() as p:
            # Playwright 启动逻辑，必须保留
            browser = await p.chromium.launch(headless=True, timeout=15000)
            page = await browser.new_page()

            # 导航到动态获取的 A 域名
            await page.goto(domain_a, wait_until="networkidle", timeout=30000) 

            # 获取最终的 B 域名
            final_url_b = page.url
            
            await browser.close() 

            if final_url_b and final_url_b != domain_a:
                await update.message.reply_text(f"✅ 本次最新的下载链接是：\n{final_url_b}")
                logger.info(f"Success! Final URL B: {final_url_b}")
            else:
                await update.message.reply_text(f"⚠️ Playwright 未检测到跳转。可能 A 域名返回静态页。当前URL: {final_url_b}")
                logger.warning(f"Playwright finished, but no redirect detected. Final URL: {final_url_b}")

    except requests.exceptions.RequestException as e:
        await update.message.reply_text(f"❌ API 请求失败，出现网络错误或超时。")
        logger.error(f"API Request Error: {e}")
    except json.JSONDecodeError:
        await update.message.reply_text(f"❌ API 返回的不是有效的 JSON 格式。")
        logger.error(f"JSON Decode Error in API response.")
    except Exception as e:
        # 捕获所有 Playwright 启动和运行时错误
        await update.message.reply_text(f"❌ Playwright 浏览器错误。请等待几分钟或联系管理员。")
        logger.error(f"Playwright Runtime Error: {e}")

# --- 3. Webhook 主函数 (多命令逻辑) ---
def main() -> None:
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN is not set. Exiting.")
        return

    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", 8080))

    if not WEBHOOK_URL:
        logger.warning("RENDER_EXTERNAL_URL is not yet available. Proceeding...")

    # main.py 中正确的行
    full_webhook_url = f"{WEBHOOK_URL}/telegram" if WEBHOOK_URL else None
    
    application = Application.builder().token(TOKEN).build()
    
    # ⭐️ 使用 Regex 匹配多个中文命令和 /start_check
    COMMAND_PATTERN = r"^(地址|最新地址|安卓地址|苹果地址|安卓下载地址|苹果下载地址|链接|最新链接|安卓链接|安卓下载链接|最新安卓链接|苹果链接|苹果下载链接|ios链接|最新苹果链接|/start_check)$"
    
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(COMMAND_PATTERN), 
            get_final_url
        )
    )
    
    if full_webhook_url:
        logger.info(f"Attempting to set webhook on port {PORT} to: {full_webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/telegram",
            webhook_url=full_webhook_url,
        )
        logger.info(f"Webhook process started.")
    else:
        logger.error("Could not determine full webhook URL. Deployment might be stuck.")

if __name__ == "__main__":
    main()
