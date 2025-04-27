import random
import string

def gen_otp(k: int = 6) -> str:
    return "".join(random.choices(string.digits, k=k))

def mail_otp(to_email: str, otp: str):
    # Swap this with SendGrid / SES / SMTP later
    print(f"[DEV] sending OTP {otp} to {to_email}")

def mail_reset_link(to_email: str, url: str):
    print(f"[DEV] sending RESET LINK {url} to {to_email}")