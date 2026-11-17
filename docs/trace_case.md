# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Mẫu điền (Case C-002: Lỗi tin lời khách hàng đè dữ liệu DB)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID: `seeded_regression-C-002-11` |
| Triệu chứng | Grader Lab 8 báo FAIL (`status resolved != denied`). Sổ cái ghi nhận hoàn 20.000đ (`refund_vnd=20000`) trong khi đơn hàng chỉ giao trễ 2 ngày (không đủ điều kiện hoàn phí ship theo chính sách, nhãn mong đợi là `denied`, `refund_vnd=0`). |
| Bước sai đầu tiên | **Event số 3 (`model_override`):** Payload `{"delay_days": 5}`. Agent tự ý đè số ngày trễ 5 ngày theo lời khách hàng thay vì số ngày trễ 2 ngày truy vấn từ cơ sở dữ liệu. |
| Vì sao là bước *đầu tiên* | Trước đó, Event 1 (`handoff`) và Event 2 (`investigator`) hoàn toàn đúng: investigator đã tra cứu chính xác đơn hàng O-202 có `delay_days: 2`. Sai phạm chỉ bắt đầu xuất hiện khi agent thực hiện override dữ liệu ở Event 3, kéo theo quote ở Event 4 tính ra 20.000đ và thực hiện lệnh hoàn tiền sai ở sổ cái. |
| Failure mode | `FM-03` (ticket_trust — tin ticket hơn DB) |
| Đối chứng | Cùng trên claim C-002 và seed 11, shape `fixed` không xuất hiện event `model_override`. Event 3 của `fixed` chuyển thẳng sang `quote` với `amount_vnd: 0` (`reason: no_entitlement`) và đưa ra kết luận từ chối (`denied`) chuẩn xác theo chính sách. |
| Regression test | Grader `db_fact_kept` (kiểm tra không có event `model_override`) và grader `refund_amount_correct` (kiểm tra số tiền hoàn = 0). Đã kiểm chứng: fail trên `seeded_regression` và pass trên `fixed`. |
| Chưa chắc chắn | Trace chỉ ghi nhận hành vi đè dữ liệu, không giải thích được vì sao mô hình suy luận lựa chọn tin lời khách hàng (do prompt nhạy cảm với ngữ cảnh phàn nàn của khách). |

## Quy tắc
- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: kiểm tra bằng `python -m pytest -q -m student -o addopts= -k graders`.