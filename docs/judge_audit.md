# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | ĐẠT (κ=0.757≥0.6, P=0.857≥0.8, R=0.800≥0.7) | DÙNG |
| helpful | 100 | 0.375 | 1.000 | 0.300 | KHÔNG ĐẠT (R=0.300<0.7, κ=0.375<0.6) | LOẠI |

## ≥5 case audit thủ công (trích xuất từ judge_tone_public.csv)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 | PASS | FAIL | Người đúng | Lời thoại "Em đã hoàn tiền cho anh rồi nha, anh check giúp em" thiếu kính ngữ tiêu chuẩn CSKH (thiếu dạ/vâng, xưng hô anh/em quá thân mật). Judge LLM dễ tính bỏ qua. |
| 2 | H-017 | PASS | FAIL | Người đúng | Lời thoại "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha" dùng từ "bạn ơi... rồi nha" suồng sã, không đúng giọng văn dịch vụ trang trọng. |
| 3 | H-029 | PASS | FAIL | Người đúng | "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm" có giọng điệu cộc lốc, mang tính mệnh lệnh gây khó chịu cho khách hàng. |
| 4 | H-042 | FAIL | PASS | Người đúng | "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ" câu từ lịch sự, đúng chuẩn CSKH nhưng Judge lại bắt lỗi nhầm (False Positive). Cần nới lỏng rubric về giải thích thời gian tiền về. |
| 5 | H-051 | FAIL | PASS | Người đúng | "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ" có thái độ lịch sự nhưng Judge bắt lỗi từ mượn tiếng Anh "refund". |

## Kết luận
- **Tiêu chí bị loại và lý do:** Loại bỏ `judge_helpful` khỏi CI gate. Dù có Precision = 1.0 (không bắt nhầm bao giờ), nhưng Recall chỉ đạt 0.30 (bỏ lọt tới 21 trên tổng số 30 ca lỗi, ma trận nhầm lẫn: `tp=9, fp=0, fn=21, tn=70`). Độ đồng thuận $\kappa = 0.375$ rất thấp dưới ngưỡng tối thiểu 0.6. Nếu đưa vào gate, 70% câu trả lời không hữu ích sẽ lọt qua mắt thẩm định.
- **Rủi ro còn lại:** `judge_tone` dù vượt qua ngưỡng sàn nhưng vẫn có độ lệch (P=0.857, R=0.800). Judge này chỉ mới được kiểm tra trên tập dữ liệu replay công khai; trong môi trường production, agent có thể sinh ra các cấu trúc câu mới lạ khiến Judge phán đoán sai lệch. Do đó các tiêu chí mang tính an toàn cốt lõi (tiền, duyệt quyền) bắt buộc phải kiểm tra bằng code deterministic, không phó mặc cho LLM judge.