# Điều tra: múi giờ / ngôn ngữ so với vị trí IP (2026-10-08)

Trạng thái: đề xuất 1 và 2 **đã làm**; 3 và 4 chưa làm (4 được phủ một phần bởi cảnh báo `ip_differs` của Kiểm tra IP).

## Câu hỏi

Một lần test profile Windows chạy trên VPS cho thấy Google xác định IP ở **Đức** (footer "Allemagne"), trong khi profile báo `fr-FR` và `Europe/Paris`. Có phải FoxProfile đặt sai múi giờ không, và đó có phải lý do Cloudflare hiện checkbox?

## Kết quả đo

### Các nguồn GeoIP nói gì về IP của VPS (157.173.115.27, Contabo)

| Nguồn | Kết quả |
| --- | --- |
| Cloudflare (`/cdn-cgi/trace`) | `loc=FR`, `colo=FRA` |
| ipinfo.io | FR, Lauterbourg, Europe/Paris, AS51167 Contabo GmbH |
| ip-api.com | FR, Lauterbourg, Europe/Paris, `hosting: true` |
| Google | Germany |

Lauterbourg là thị trấn Pháp sát biên giới Đức; Contabo là công ty Đức. Các cơ sở dữ liệu không thống nhất, nên **không cấu hình nào khớp với mọi nguồn**. Cloudflare thấy FR, khớp với profile, nên lệch Pháp/Đức **không phải** nguyên nhân Cloudflare hiện checkbox; nhãn datacenter (`hosting: true`) là nghi phạm chính.

### Múi giờ có theo IP của proxy không? Có.

Cùng profile Windows, chạy trên máy Windows ở Việt Nam:

| | Không proxy | Qua proxy HTTP trên VPS Pháp |
| --- | --- | --- |
| `Intl...timeZone` | Asia/Bangkok | Europe/Paris |
| `navigator.languages` | vi-VN, vi | fr-FR, fr |
| Cloudflare thấy | VN | FR |
| Google thấy | Vietnam | Germany |

Camoufox (`geoip=True`, FoxProfile luôn bật) gửi request **qua proxy** tới api.ipify.org để lấy IP ra, rồi đặt timezone, locale, toạ độ geolocation và IP WebRTC theo IP đó ở **mỗi lần mở**. Xem `camoufox/utils.py` (`if geoip:` → `public_ip(proxy)` → `get_geolocation`). Lưu ý timezone/locale được đặt bằng `setdefault`.

### Cloudflare challenge theo môi trường

| Môi trường | Kết quả trên scrapingcourse.com/cloudflare-challenge |
| --- | --- |
| Windows, IP nhà mạng VN, headless | Vượt qua |
| Windows, IP nhà mạng VN, có cửa sổ | Vượt qua |
| VPS Linux (Contabo), `headless=True` | Kẹt ở "Performing security verification" |
| VPS Linux (Contabo), `headless="virtual"` (Xvfb) | Kẹt, hiện checkbox Turnstile; click theo toạ độ không qua |

Chưa loại trừ hoàn toàn khác biệt Linux/Windows, nhưng IP datacenter là nguyên nhân khả dĩ nhất.

## Vấn đề phát hiện thêm

1. **VN → `Asia/Bangkok`.** DB GeoIP của Camoufox trả timezone Thái Lan cho IP Việt Nam. Máy thật ở VN báo `Asia/Ho_Chi_Minh` (hoặc alias `Asia/Saigon`). Cùng UTC+7 nên giờ đúng, nhưng tên timezone không khớp quốc gia của IP.
2. **IPv4/IPv6.** Qua proxy dual-stack, Camoufox tra GeoIP theo IPv4 (ipify ưu tiên IPv4) nhưng trình duyệt ra ngoài bằng IPv6 (Cloudflare thấy `2a02:c207:...`). Lần này cả hai đều FR; với proxy có IPv4/IPv6 ở hai nước khác nhau, timezone sẽ khớp một IP còn site thấy IP kia.
3. **Locale tự động là ngẫu nhiên ở mỗi lần mở.** Camoufox chọn ngôn ngữ theo tỷ lệ dân số nói ngôn ngữ đó ở quốc gia của IP (`StatisticalLocaleSelector.from_region`, dùng `np.random.choice`), và mỗi lần mở là một tiến trình mới. Đo 300 lần: FR ra fr-FR ~62%, en-FR ~20%, es-FR ~11%, de/oc/it-FR; US ra en-US ~86%, es-US ~10%; VN gần như luôn vi-VN. Cùng một profile vì vậy có thể đổi ngôn ngữ giữa các phiên.

## Đề xuất

1. (Đã làm) Override timezone/locale theo từng profile (mặc định vẫn auto theo IP). Truyền `config={"timezone": ..., "locale:language": ...}` hoặc `locale=` cho Camoufox; vì geoip dùng `setdefault` nên giá trị override sẽ thắng.
2. (Đã làm) Nút "Kiểm tra IP" cho profile: lấy IP ra qua proxy của profile, tra Cloudflare trace + ipinfo + ip-api, so với timezone đang dùng, cảnh báo khi lệch hoặc khi IP bị gắn `hosting`.
3. Map timezone "mượn" về timezone chuẩn của quốc gia (VN: `Asia/Ho_Chi_Minh`).
4. Phát hiện proxy dual-stack: so IP từ ipify (IPv4) với IP mà Cloudflare trace thấy; cảnh báo nếu khác quốc gia.

## Cách tái hiện

- `tests/e2e/detection_e2e.py headless headed` (so headless/có cửa sổ trên máy hiện tại)
- `curl https://www.cloudflare.com/cdn-cgi/trace` qua proxy để xem Cloudflare đặt IP ở đâu
