# InsecLab Thesis Template

## Notes

- Nhớ dùng `\bigbreak\noindent` giữa các đoạn văn :v

## Tối ưu

[Overleaf đã thay đổi về thời gian compile của free plan](https://www.overleaf.com/blog/changes-to-free-compile-timeouts-and-servers), để có thể tránh gặp phải trường hợp timeout, sau đây là một số tip:

- Tối ưu dung lượng ảnh sử dụng các website như [Squoosh](https://squoosh.app) hay [image-compress](https://www.webutils.app/image-compress) (Latex chỉ cho phép các dạng ảnh như jpg hoặc png, lưu ý khi chuyển đổi định dạng).
- Chỉ thêm các cite cần thiết vào trong file `references.bib`.
- Mua bản pro :D hoặc compile offline.

## Build LaTeX locally

```powershell
.\build.ps1            # dịch ra build\main.pdf
.\build.ps1 -Clean     # xoá build/ rồi dịch lại từ đầu
.\build.ps1 -Open      # dịch xong thì mở PDF
```

Đo thật 2026-08-26 trên máy dev (MiKTeX 25.12): **72 trang, 60 mục tham khảo**.
Lần chạy đầu lâu hơn hẳn vì MiKTeX tự tải gói và dựng cache font — chưa thấy log
không có nghĩa là treo.

Hai điều cần biết trước khi nghi ngờ file `.tex`:

- **`latexmk` của MiKTeX là script Perl.** Máy không cài Perl thì nó thoát 1 kèm
  *"could not find the script engine 'perl'"*, và `build/main.log` ra **0 byte**.
  `build.ps1` **thử chạy** `latexmk -v` chứ không chỉ kiểm tra tệp có tồn tại, nên
  nó tự rơi về `pdflatex + biber`. Muốn dùng latexmk thì cài Strawberry Perl;
  không cài cũng không sao.
- **`report/kiem_tra_tex.py` KHÔNG dịch tài liệu**, nó chỉ lint (ref/cite/gói/ký tự
  điều khiển/số cũ). Lint xanh không có nghĩa là bản dịch chạy được — phải chạy cả hai.
