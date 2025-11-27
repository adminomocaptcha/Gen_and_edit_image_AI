import os
import time
import datetime
from typing import Optional
from io import BytesIO

import requests
import streamlit as st
from PIL import Image

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")


def call_generate(user_id: str, prompt: str, mode: Optional[str]) -> Optional[str]:
    """Gọi POST /generate -> trả về job_id"""
    payload = {"user_id": user_id, "prompt": prompt}
    if mode and mode != "AUTO":
        payload["mode"] = mode

    resp = requests.post(f"{BACKEND_URL}/generate", json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("job_id")


def poll_result(job_id: str, timeout_sec: float = 120.0, poll_interval: float = 1.0):
    """Poll GET /result/{job_id} cho đến khi done/error"""
    start = time.time()
    while True:
        resp = requests.get(f"{BACKEND_URL}/result/{job_id}", timeout=10)
        if resp.status_code == 404:
            return None

        data = resp.json()
        status = data.get("status")

        if status in ("done", "error"):
            return data

        if time.time() - start > timeout_sec:
            return None

        time.sleep(poll_interval)


def download_image(image_url: str):
    """Download ảnh từ URL và convert sang PIL Image"""
    try:
        resp = requests.get(image_url, timeout=30)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        return img, resp.content
    except Exception as e:
        st.error(f"Không thể tải ảnh: {e}")
        return None, None


# ==========================
# Cấu hình
# ==========================
st.set_page_config(
    page_title="Qwen Image AI", 
    page_icon="🎨",
    layout="wide"
)

st.title("🎨 Qwen Image AI Chatbot")
st.caption("Tạo và chỉnh sửa ảnh với AI 🖼️")

# ==========================
# State
# ==========================
if "messages" not in st.session_state:
    st.session_state["messages"] = []
    st.session_state["messages"].append({
        "role": "assistant",
        "content": "Xin chào! Tôi có thể giúp bạn tạo hoặc chỉnh sửa ảnh. Hãy mô tả ảnh bạn muốn! 💬",
    })

if "user_id" not in st.session_state:
    st.session_state["user_id"] = f"user_{int(time.time())}"

# ==========================
# Sidebar
# ==========================
with st.sidebar:
    st.header("⚙️ Cài đặt")
    
    # User ID
    user_id = st.text_input(
        "👤 User ID",
        value=st.session_state["user_id"],
        help="Mỗi user có lịch sử ảnh riêng"
    )
    st.session_state["user_id"] = user_id
    
    st.markdown("---")
    
    # Mode selection
    mode_option = st.radio(
        "🎯 Chế độ",
        ["🤖 Auto (AI tự nhận diện)", "✨ Tạo ảnh mới", "✏️ Chỉnh sửa ảnh gần nhất"],
        help="Auto: AI phân tích prompt\nTạo mới: Luôn gen ảnh mới\nEdit: Chỉnh sửa ảnh trước đó"
    )
    
    if mode_option == "🤖 Auto (AI tự nhận diện)":
        mode = None
    elif mode_option == "✨ Tạo ảnh mới":
        mode = "NEW"
    else:
        mode = "EDIT"
    
    st.markdown("---")
    
    # Clear chat
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state["messages"] = []
        st.session_state["messages"].append({
            "role": "assistant",
            "content": "Lịch sử đã được xóa. Bắt đầu lại nào! 💬",
        })
        st.rerun()
    
    # Statistics
    num_messages = len([m for m in st.session_state["messages"] if m["role"] == "user"])
    num_images = len([m for m in st.session_state["messages"] if "image" in m])
    st.markdown(f"**💬 Tin nhắn:** {num_messages}")
    st.markdown(f"**🖼️ Ảnh đã tạo:** {num_images}")
    
    st.markdown("---")
    st.markdown("### 💡 Ví dụ")
    st.code("a realistic photo of a cat")
    st.code("make her wear a red dress")
    st.code("remove the background")
    
    st.markdown("---")
    st.write("🔗 Backend:", BACKEND_URL)

# ==========================
# Hiển thị lịch sử chat
# ==========================
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        
        if "image" in msg:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(msg["image"], use_container_width=True)
        
        if "image_url" in msg and msg["image_url"]:
            st.markdown(f"🔗 [Mở ảnh gốc]({msg['image_url']})")
        
        if "download_data" in msg and msg["download_data"]:
            ts = msg.get("timestamp", datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            st.download_button(
                "⬇️ Tải ảnh",
                data=msg["download_data"],
                file_name=f"qwen_image_{ts}.png",
                mime="image/png",
                key=f"download_{ts}"
            )

# ==========================
# Ô nhập prompt
# ==========================
user_prompt = st.chat_input("💭 Nhập mô tả ảnh hoặc yêu cầu chỉnh sửa...")

if user_prompt:
    # Add user message
    st.session_state["messages"].append({
        "role": "user",
        "content": user_prompt
    })
    
    # Show assistant thinking
    with st.chat_message("assistant"):
        st.markdown("⏳ Đang xử lý...")
        
        status_container = st.empty()
        status_container.info(f"🎯 Chế độ: **{mode_option}**")
        
        try:
            # Call backend
            job_id = call_generate(user_id=user_id, prompt=user_prompt, mode=mode)
            status_container.success(f"✅ Job ID: `{job_id}`")
            
            # Poll result
            with st.spinner("🎨 AI đang tạo ảnh của bạn..."):
                result = poll_result(job_id, timeout_sec=120.0, poll_interval=1.0)
            
            if not result:
                st.error("⏱️ Hết thời gian chờ. Vui lòng thử lại!")
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": "❌ Timeout - vui lòng thử lại."
                })
            
            elif result.get("status") == "error":
                error_msg = result.get("error_message", "Lỗi không xác định")
                st.error(f"❌ Lỗi: {error_msg}")
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": f"❌ Lỗi: {error_msg}"
                })
            
            elif result.get("status") == "done" and result.get("image_url"):
                image_url = result["image_url"]
                st.success("✅ Hoàn thành!")
                
                # Download và hiển thị ảnh
                image, img_bytes = download_image(image_url)
                
                if image:
                    col1, col2, col3 = st.columns([1, 2, 1])
                    with col2:
                        st.image(image, caption="✨ Kết quả", use_container_width=True)
                    
                    # Download button
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    st.download_button(
                        "⬇️ Tải ảnh",
                        data=img_bytes,
                        file_name=f"qwen_image_{ts}.png",
                        mime="image/png"
                    )
                    
                    st.markdown(f"🔗 [Mở ảnh gốc]({image_url})")
                    
                    # Save to history
                    st.session_state["messages"].append({
                        "role": "assistant",
                        "content": "✨ Đây là ảnh của bạn!",
                        "image": image,
                        "image_url": image_url,
                        "download_data": img_bytes,
                        "timestamp": ts
                    })
                else:
                    st.warning("⚠️ Không thể tải ảnh từ URL")
            
            else:
                st.warning("⚠️ Phản hồi không hợp lệ từ server")
                st.session_state["messages"].append({
                    "role": "assistant",
                    "content": "⚠️ Có lỗi xảy ra, vui lòng thử lại."
                })
        
        except Exception as e:
            st.error(f"❌ Lỗi: {e}")
            st.session_state["messages"].append({
                "role": "assistant",
                "content": f"❌ Lỗi: {str(e)}"
            })
    
    st.rerun()
