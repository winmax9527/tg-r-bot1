import os
import logging
# import requests # Playwright 方案不再需要 requests 库
# ----------------------------------------------------
# 确保所有 Telegram 相关的导入都在这里
from telegram import Update 
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters # <-- 新增 MessageHandler 和 filters
# ----------------------------------------------------
from playwright.async_api import async_playwright

# --- 1. 日志配置 ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 2. 核心功能函数 (使用 Playwright) ---
async def get_final_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # !!! 替换为您的【会发生跳转的原始域名 A】！！！
    DOMAIN_A = "https://owzmz.ivqrrox.com/37mC45B/mdgxmzlkzt" 
    
    await update.message.reply_text("正在为您获取最新的苹果下载链接，请稍候...")
    
    final_url_b = None
    
    try:
        # 使用 async_playwright 异步启动 Playwright
        async with async_playwright() as p:
            # 使用 Chromium 浏览器，设置为无头 (headless=True)
            # 必须使用 headless=True
            browser = await p.chromium.launch(headless=True, timeout=15000) # 启动超时设置为15秒
            page = await browser.new_page()

            # 导航到初始域名 A
            # wait_until="networkidle" 确保页面在网络空闲时才加载完毕，以等待 JS 跳转完成
            await page.goto(DOMAIN_A, wait_until="networkidle", timeout=30000) # 页面跳转超时设置为30秒

            # 获取当前页面的 URL，这已经是 JS 重定向后的最终 URL
            final_url_b = page.url
            
            await browser.close() # 关闭浏览器实例

            if final_url_b and final_url_b != DOMAIN_A:
                await update.message.reply_text(f"✅ 本次最新苹果下载链接是：\n{final_url_b}")
            else:
                await update.message.reply_text(f"⚠️ 未检测到有效跳转。可能链接是静态的，或加载超时。当前URL: {final_url_b}")
                logger.warning(f"Playwright finished, but no redirect detected. Final URL: {final_url_b}")

    except Exception as e:
        # 捕获所有 Playwright 启动和运行时错误，通常是资源不足导致
        await update.message.reply_text(f"❌ 链接获取失败，浏览器错误。请等待几分钟或联系管理员。")
        logger.error(f"Playwright Runtime Error: {e}")
        
# --- 3. Webhook 主函数 ---
def main() -> None:
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN is not set. Exiting.")
        return

    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", 8080))

    if not WEBHOOK_URL:
        logger.warning("RENDER_EXTERNAL_URL is not yet available. Proceeding...")

    full_webhook_url = f"{WEBHOOK_URL}/telegram" if WEBHOOK_URL else None
    
    application = Application.builder().token(TOKEN).build()
    
    # -----------------------------------------------------------------
    # ⭐️ 核心修改：使用 Regex 匹配多个中文命令和 /start_check
    # r"^(...)$" 确保用户输入的文本必须完全匹配其中一个命令
    COMMAND_PATTERN = r"^(苹果链接|ios链接|最新苹果链接|/start_check)$"
    
    application.add_handler(
        MessageHandler(
            # 匹配纯文本消息 并且 消息内容符合我们的正则表达式
            filters.TEXT & filters.Regex(COMMAND_PATTERN), 
            get_final_url
        )
    )
    # -----------------------------------------------------------------
    
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
