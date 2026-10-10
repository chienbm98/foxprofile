"""Page signals the heuristic judge looks for. Phrases are matched case-insensitively against the
accessibility snapshot; URL parts against the page URL."""

CHECKPOINT_URLS = ("/checkpoint", "/account/access")
CAPTCHA_PHRASES = ("captcha", "security check", "kiểm tra bảo mật")
LOGIN_URLS = ("/login",)
LOGIN_PHRASES = ("log in", "đăng nhập")
# A login form, not just a "Log in" link: the page also shows a password box.
PASSWORD_PHRASES = ('textbox "password', 'textbox "mật khẩu')

PLATFORMS = {
    "facebook": {
        "max_chars": 5000,
        "published": ("your post is now published", "bài viết của bạn đã được đăng"),
        # The composer is an unnamed dialog holding a form named after the post.
        "composer": ('form "bài viết"', 'form "post"', "text: tạo bài viết", "text: create post"),
        "ready": ("what's on your mind", "what’s on your mind", "bạn đang nghĩ gì"),
    },
    "tiktok": {
        "max_chars": 2200,
        "published": ("your video has been uploaded", "video của bạn đã được đăng"),
        "composer": ('button "post"', 'button "đăng"'),
        "ready": ("select video", "chọn video", "upload"),
    },
    "x": {
        "max_chars": 280,
        "weighted": True,  # X counts most non-Latin characters, Vietnamese accents included, as 2
        "published": ("your post was sent", "bài đăng của bạn đã được gửi"),
        "composer": ('textbox "đăng văn bản"', 'textbox "post text"'),
        "ready": ('link "trang chủ"', 'link "home"'),
    },
}
