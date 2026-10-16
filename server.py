import os, time
from collections import defaultdict, deque
import requests
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")

KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
SYSTEM = os.environ.get(
    "SYSTEM_PROMPT",
    "أنت مساعد ذكي ودود. رد بنفس لغة المستخدم وبأسلوب واضح ومختصر.",
)

# حماية بسيطة: حد أقصى 15 رسالة بالدقيقة لكل شخص
hits = defaultdict(deque)


def limited(ip):
    now = time.time()
    q = hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 15:
        return True
    q.append(now)
    return False


@app.get("/")
def home():
    return send_from_directory("static", "index.html")


@app.post("/chat")
def chat():
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "x").split(",")[0].strip()
    if limited(ip):
        return jsonify(error="رسائل كثيرة بسرعة، استنى شوي وجرّب."), 429
    if not KEY:
        return jsonify(error="الخادم غير مهيّأ (ناقص المفتاح)."), 500

    msgs = (request.get_json(silent=True) or {}).get("messages", [])[-20:]
    contents = []
    for m in msgs:
        text = str(m.get("content", ""))[:2000]
        if not text.strip():
            continue
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": text}]})
    if not contents or contents[-1]["role"] != "user":
        return jsonify(error="رسالة غير صالحة."), 400

    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            headers={"x-goog-api-key": KEY, "Content-Type": "application/json"},
            json={"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": contents},
            timeout=60,
        )
    except requests.RequestException:
        return jsonify(error="تعذّر الوصول للذكاء الاصطناعي، جرّب مرة ثانية."), 502
    if r.status_code == 429:
        return jsonify(error="وصلنا للحد المجاني اليوم، جرّب لاحقاً."), 429
    if r.status_code != 200:
        return jsonify(error="صار خطأ من مزوّد الذكاء الاصطناعي."), 502
    try:
        reply = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, ValueError):
        return jsonify(error="ما قدرت أجاوب على هالسؤال، جرّب صياغة ثانية."), 502
    return jsonify(reply=reply)
