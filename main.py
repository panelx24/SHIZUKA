import os
import time
import requests
from flask import Flask
from threading import Thread
from playwright.sync_api import sync_playwright

# ==========================================
# ⚠️ কনফিগারেশন 
# ==========================================
MY_WEBSITE_URL = os.environ.get('MY_WEBSITE_URL', 'https://yourdomain.com') 
SCRAPER_TOKEN = os.environ.get('SCRAPER_TOKEN', 'panenx24') # এখানে panenx24 সেট করা হলো
CHECK_INTERVAL = 4 

# ==========================================
# Render.com-এ সার্ভার ঘুমিয়ে পড়া ঠেকানোর জন্য Flask সার্ভার
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "SHIZUKA SCRAPER IS RUNNING!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# স্ক্র্যাপার মেইন ফাংশন
# ==========================================
def run_scraper():
    print("🚀 SCRAPER STARTING...")
    
    try:
        print("Fetching config from website...")
        res = requests.get(
            f"{MY_WEBSITE_URL}/api/webhook/scraper-config.php", 
            headers={"X-Scraper-Token": SCRAPER_TOKEN},
            timeout=15
        )
        config = res.json()['data']
        
        if not config['login_url'] or not config['email']:
            print("❌ TARGET CONFIG NOT FOUND IN ADMIN PANEL. RETRYING IN 10S...")
            time.sleep(10)
            return run_scraper()
            
        print("✅ CONFIG LOADED. LAUNCHING BROWSER...")
        
    except Exception as e:
        print(f"❌ ERROR FETCHING CONFIG: {e}")
        time.sleep(10)
        return run_scraper()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        
        context = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        
        try:
            print("🔐 LOGGING IN TO TARGET SITE...")
            page.goto(config['login_url'], wait_until="networkidle")
            
            # এখানে config['password'] অটোমেটিক আপনার ডাটাবেস থেকে আসবে
            page.fill('input[type="email"]', config['email']) 
            page.fill('input[type="password"]', config['password'])
            page.click('button[type="submit"]')
            
            page.wait_for_load_state("networkidle")
            print("✅ LOGIN SUCCESSFUL!")

            print(f"Navigating to: {config['target_url']}")
            page.goto(config['target_url'], wait_until="networkidle")
            print("🔄 STARTING SCRAPE LOOP...")

            last_sent_sms = ""

            while True:
                try:
                    page.get_by_text("Refresh").click()
                    page.wait_for_timeout(2000) 

                    otp_data = page.evaluate('''() => {
                        const allRows = Array.from(document.querySelectorAll('div')).filter(div => {
                            return div.textContent.includes('SUCCESS') && /9967\\d{7}/.test(div.textContent);
                        });

                        if (allRows.length > 0) {
                            const targetBox = allRows[0]; 
                            
                            const numberMatch = targetBox.textContent.match(/9967\\d{7}/);
                            const number = numberMatch ? numberMatch[0] : 'UNKNOWN';

                            const textWithoutNumber = targetBox.textContent.replace(number, '');
                            const otpMatch = textWithoutNumber.match(/\\b\\d{4,8}\\b/);
                            const otp_code = otpMatch ? otpMatch[0] : '';

                            const buttons = Array.from(targetBox.querySelectorAll('button, a, svg'));
                            if (buttons.length > 0) {
                                buttons[buttons.length - 1].click();
                            }
                            
                            return { number: number, otp: otp_code };
                        }
                        return null;
                    }''')

                    if otp_data and otp_data['number'] != 'UNKNOWN':
                        page.wait_for_timeout(500) 
                        
                        full_sms = page.evaluate("navigator.clipboard.readText()")

                        if full_sms and full_sms != last_sent_sms:
                            print(f"🔍 NEW OTP DETECTED: {otp_data['number']} | OTP: {otp_data['otp']}")
                            
                            post_res = requests.post(
                                f"{MY_WEBSITE_URL}/api/webhook/scraper-receive.php",
                                json={
                                    "number": otp_data['number'], 
                                    "otp": otp_data['otp'], 
                                    "message": full_sms
                                },
                                headers={"X-Scraper-Token": SCRAPER_TOKEN},
                                timeout=10
                            )
                            print(f"✅ DATA SENT: {post_res.json().get('status')}")
                            
                            last_sent_sms = full_sms
                        else:
                            print("⏳ WAITING FOR NEW OTP...")

                    time.sleep(CHECK_INTERVAL)
                    
                except Exception as e:
                    print(f"⚠️ SCRAPE LOOP ERROR (Retrying): {e}")
                    time.sleep(CHECK_INTERVAL)
                    
        except Exception as e:
            print(f"❌ BROWSER ERROR: {e}")
            browser.close()
            time.sleep(5)
            return run_scraper()

if __name__ == '__main__':
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    run_scraper()
