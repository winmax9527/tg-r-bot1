# main.py (Simplified Check - 仅检查 TOKEN)

import os
# ... 其他导入 ...
# ... 其他函数 ...

def main() -> None:
    # --- 仅检查 TOKEN，信任 Render 会设置 RENDER_EXTERNAL_URL 和 PORT ---
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
    if not TOKEN:
        # 如果用户没有设置 Token，则这是主要的错误
        logger.error("TELEGRAM_TOKEN is not set. Exiting.")
        return

    # Render 会自动为 Web Services 设置这些变量
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    PORT = int(os.environ.get("PORT", 8080))
    
    # 如果 WEBHOOK_URL 缺失，给出一个警告，而不是直接退出
    if not WEBHOOK_URL:
        logger.warning("RENDER_EXTERNAL_URL is not yet available, service will likely fail setting webhook for now.")
        # 如果 WEBHOOK_URL 此时缺失，启动 run_webhook 可能会出错，
        # 但至少我们已经排除了 TOKEN 缺失的问题。
        # 我们可以让程序继续尝试运行 run_webhook，让 Render 的机制来处理。
        # 注意：此处需要保证 run_webhook 即使 WEBHOOK_URL 缺失也不会导致致命错误。
        # 鉴于 Render 环境的特殊性，我们继续执行，让 Render 在 Live 后自动重试。
        pass 
        
    # ... 后续 run_webhook 逻辑保持不变 ...
    if WEBHOOK_URL:
        full_webhook_url = f"{WEBHOOK_URL}/telegram"
        logger.info(f"Attempting to set webhook to: {full_webhook_url}")
        
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start_check", get_final_url))
        
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/telegram",
            webhook_url=full_webhook_url,
        )
        logger.info(f"Webhook process started.")
    else:
        logger.error("Could not get RENDER_EXTERNAL_URL. Deployment might be in a temporary state.")

if __name__ == "__main__":
    main()
