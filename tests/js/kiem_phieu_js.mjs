// Kiểm logic JS của phiếu bằng một DOM giả tối thiểu — không cần trình duyệt.
// Chỉ kiểm đúng thứ quyết định: nút Tải có THẬT SỰ bị chặn khi chưa xem ảnh không.
import fs from "node:fs";
import vm from "node:vm";

const html = fs.readFileSync(
  process.env.PHIEU || "document/review/image_questions/phieu.html",
  "utf8");

// rút phần <script> ra
const js = html.match(/<script>([\s\S]*?)<\/script>/)[1];

// DOM giả: 3 ô
function taoO(id) {
  const o = {
    dataset: {}, classList: { _s: new Set(["chua-xem"]),
      add(x) { this._s.add(x); }, remove(x) { this._s.delete(x); },
      contains(x) { return this._s.has(x); } },
    _f: { ".chk": { checked: false }, ".q": { value: "" }, ".a": { value: "" },
          ".ldb": { value: "" } },
    querySelector(sel) { return this._f[sel]; },
    closest() { return o; },
  };
  o.dataset.id = id;
  return o;
}
const os = [taoO("A"), taoO("B"), taoO("C")];
const nutTai = { disabled: false, title: "" };
const demEl = { textContent: "" };

globalThis.document = {
  querySelectorAll: () => os,
  getElementById: (id) => (id === "nut-tai" ? nutTai : demEl),
  addEventListener: () => {},
  createElement: () => ({ click() {}, set href(_) {}, set download(_) {} }),
};
globalThis.Blob = class { constructor(p) { this.p = p; } async text() { return this.p[0]; } };
globalThis.URL = { createObjectURL: () => "blob:x" };

// Chạy trong context riêng, đúng như trình duyệt nạp <script>:
// `eval` trong ESM không đưa hàm khai báo ra scope ngoài.
const ctx = vm.createContext(globalThis);
vm.runInContext(js, ctx);
const { dem, daXem, xuat } = ctx;

const ket = [];
function ktra(ten, dieu_kien) {
  ket.push([ten, dieu_kien]);
  console.log(`${dieu_kien ? "OK  " : "SAI "} ${ten}`);
}

// 1. Ban đầu: chưa ô nào xem -> nút bị chặn
dem();
ktra("ban đầu nút Tải BỊ CHẶN", nutTai.disabled === true);
ktra("đếm 0/3", demEl.textContent === "0/3 ô đã xong");

// 2. Điền đủ chữ nhưng CHƯA bấm 'đã xem ảnh' -> vẫn chặn
os.forEach(o => { o._f[".q"].value = "hỏi"; o._f[".a"].value = "đáp"; });
dem();
ktra("điền đủ chữ mà chưa xem ảnh -> VẪN CHẶN", nutTai.disabled === true);
ktra("vẫn đếm 0/3", demEl.textContent === "0/3 ô đã xong");

// 3. Bấm 'đã xem ảnh' 2/3 ô -> vẫn chặn
daXem({ closest: () => os[0], textContent: "", classList: { add() {} } });
daXem({ closest: () => os[1], textContent: "", classList: { add() {} } });
ktra("xem 2/3 ô -> vẫn chặn", nutTai.disabled === true);
ktra("đếm 2/3", demEl.textContent === "2/3 ô đã xong");

// 4. Ô thứ 3 tick 'Bỏ' -> tính là xong dù chưa xem
os[2]._f[".chk"].checked = true;
dem();
ktra("ô tick Bỏ tính là xong -> nút MỞ", nutTai.disabled === false);
ktra("đếm 3/3", demEl.textContent === "3/3 ô đã xong");

// 5. Xuất ra JSON đúng cấu trúc
let captured = null;
globalThis.Blob = class { constructor(p) { captured = p[0]; } };
globalThis.URL = { createObjectURL: () => "blob:x" };
xuat();
const d = JSON.parse(captured);
ktra("JSON có 3 ô", Object.keys(d.traloi).length === 3);
ktra("JSON có _bat_dau/_ket_thuc", !!d._bat_dau && !!d._ket_thuc);
ktra("ô bỏ được đánh dấu", d.traloi["C"].bo === true);

const sai = ket.filter(([, ok]) => !ok);
console.log(`\n${ket.length - sai.length}/${ket.length} kiểm tra đạt`);
process.exit(sai.length ? 1 : 0);
