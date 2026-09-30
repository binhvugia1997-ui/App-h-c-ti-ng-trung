"""Hán Ngữ App — ứng dụng độc lập học tiếng Trung (Kivy).

Chạy native trên desktop (Windows/Linux/macOS) và Android (qua Buildozer),
KHÔNG cần trình duyệt web. Tái dùng trực tiếp backend Python trong package
``app/`` (SQLite, SRS, Qwen client, diff, ...).

Cách chạy desktop::
    pip install kivy httpx
    python kivy_app/main.py
"""

import os
import sys
import threading
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Đường dẫn dữ liệu: ưu tiên bộ nhớ riêng của app trên Android
# ---------------------------------------------------------------------------
def _setup_data_dir() -> None:
    if "HANNGU_DATA_DIR" in os.environ:
        return
    try:  # Android (python-for-android)
        from android.storage import app_storage_path  # type: ignore

        os.environ["HANNGU_DATA_DIR"] = app_storage_path()
        return
    except Exception:
        pass
    # Desktop: thư mục data cạnh file này (portable)
    base = os.path.dirname(os.path.abspath(__file__))
    os.environ["HANNGU_DATA_DIR"] = os.path.join(base, "data")


_setup_data_dir()

# Cho phép import package ``app/`` từ repo (kivy_app nằm trong repo).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import paths  # noqa: E402
from app.startup import run_startup  # noqa: E402
from app.db.database import get_conn  # noqa: E402
from app.dashboard.stats import get_summary  # noqa: E402
from app.vocab.srs import schedule_review  # noqa: E402
from app.dictation.diff import char_diff  # noqa: E402
from app.qwen.client import get_qwen_client, QwenError  # noqa: E402

# ---------------------------------------------------------------------------
# Kivy UI
# ---------------------------------------------------------------------------
from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.screenmanager import ScreenManager, Screen  # noqa: E402
from kivy.uix.scrollview import ScrollView  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402
from kivy.uix.togglebutton import ToggleButton  # noqa: E402

TABS = [
    ("home", "🏠 Hôm nay"),
    ("vocab", "🈶 Từ vựng"),
    ("video", "🎬 Video"),
    ("shadow", "🎙️ Shadowing"),
    ("dictation", "👂 Nghe chép"),
    ("translate", "🔁 Dịch"),
    ("pronun", "🗣️ Phát âm"),
    ("history", "🕘 Lịch sử"),
    ("settings", "⚙️ Cài đặt"),
]

QWEN_OFFLINE = "Máy AI hiện không kết nối được. Vui lòng kiểm tra máy Qwen."


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def card(title: str, body: str) -> BoxLayout:
    box = BoxLayout(orientation="vertical", size_hint_y=None, padding=10, spacing=4)
    box.bind(minimum_height=box.setter("height"))
    box.add_widget(Label(text=f"[b]{title}[/b]", markup=True, size_hint_y=None, height=30, halign="left"))
    box.add_widget(Label(text=body, size_hint_y=None, halign="left", valign="top"))
    return box


class HomeScreen(Screen):
    def on_pre_enter(self):
        self.refresh()

    def refresh(self):
        self.clear_widgets()
        layout = BoxLayout(orientation="vertical", padding=12, spacing=8)
        layout.add_widget(Label(text="[b][size=24]Hôm nay của bạn[/size][/b]", markup=True, size_hint_y=None, height=44))
        try:
            with get_conn() as conn:
                s = get_summary(conn)
            body = (
                f"Chuỗi ngày học: {s.get('chuoi_ngay', 0)} ngày\n"
                f"Phút học hôm nay: {s.get('phut_hom_nay', 0)}\n"
                f"Từ mới: {s.get('tu_moi', 0)} | Cần ôn: {s.get('can_on', 0)}\n"
                f"Shadowing: {s.get('shadowing', 0)} câu | Nghe chép: {s.get('dictation', 0)} bài"
            )
        except Exception as e:
            body = f"Chưa có dữ liệu ({e})"
        layout.add_widget(card("Tổng quan", body))
        btn = Button(text="Ghi nhận buổi học (20 phút)", size_hint_y=None, height=48)
        btn.bind(on_press=self._log)
        layout.add_widget(btn)
        self._msg = Label(text="", size_hint_y=None, height=30)
        layout.add_widget(self._msg)
        self.add_widget(layout)

    def _log(self, _):
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO study_events (ngay, so_phut, hoat_dong, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (date.today().isoformat(), 20, "hoc", _now()),
                )
            self._msg.text = "Đã ghi nhận!"
        except Exception as e:
            self._msg.text = f"Lỗi: {e}"
        self.refresh()


class VocabScreen(Screen):
    che_do_the = False
    the_hien_tai = None

    def on_pre_enter(self):
        self.hien_danh_sach()

    # -- danh sách + thêm từ -------------------------------------------
    def hien_danh_sach(self):
        self.che_do_the = False
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=10, spacing=6)
        root.add_widget(Label(text="[b][size=22]Từ vựng[/b][/size]", markup=True, size_hint_y=None, height=40))
        form = BoxLayout(orientation="vertical", size_hint_y=None, height=210, spacing=4)
        self.in_hanzi = TextInput(hint_text="Chữ Hán (ví dụ: 你好)", size_hint_y=None, height=40, multiline=False)
        self.in_pinyin = TextInput(hint_text="Pinyin (ví dụ: nǐ hǎo)", size_hint_y=None, height=40, multiline=False)
        self.in_nghia = TextInput(hint_text="Nghĩa tiếng Việt", size_hint_y=None, height=40, multiline=False)
        for w in (self.in_hanzi, self.in_pinyin, self.in_nghia):
            form.add_widget(w)
        row = BoxLayout(size_hint_y=None, height=44, spacing=6)
        b_add = Button(text="➕ Thêm từ")
        b_add.bind(on_press=self._them_tu)
        b_flash = Button(text="🃏 Ôn flashcard")
        b_flash.bind(on_press=lambda _: self.hien_flashcard())
        row.add_widget(b_add)
        row.add_widget(b_flash)
        form.add_widget(row)
        root.add_widget(form)
        self._msg = Label(text="", size_hint_y=None, height=28)
        root.add_widget(self._msg)
        scroll = ScrollView()
        ds = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        ds.bind(minimum_height=ds.setter("height"))
        try:
            with get_conn() as conn:
                rows = conn.execute("SELECT id, hanzi, pinyin, nghia_vi FROM vocab ORDER BY id DESC LIMIT 50").fetchall()
            for r in rows:
                ds.add_widget(Label(text=f"{r['hanzi']}  {r['pinyin'] or ''}  —  {r['nghia_vi'] or ''}",
                                    size_hint_y=None, height=32, halign="left"))
        except Exception as e:
            ds.add_widget(Label(text=f"Lỗi tải: {e}", size_hint_y=None, height=32))
        scroll.add_widget(ds)
        root.add_widget(scroll)
        self.add_widget(root)

    def _them_tu(self, _):
        hanzi = self.in_hanzi.text.strip()
        if not hanzi:
            self._msg.text = "Hãy nhập chữ Hán."
            return
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO vocab (hanzi, pinyin, nghia_vi, trang_thai, created_at)"
                    " VALUES (?, ?, ?, 'moi', ?)",
                    (hanzi, self.in_pinyin.text.strip() or None, self.in_nghia.text.strip() or None, _now()),
                )
            self._msg.text = "Đã thêm!"
            self.in_hanzi.text = self.in_pinyin.text = self.in_nghia.text = ""
        except Exception as e:
            self._msg.text = f"Lỗi: {e}"
        self.hien_danh_sach()

    # -- flashcard -------------------------------------------------------
    def hien_flashcard(self):
        self.che_do_the = True
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT * FROM vocab WHERE ngay_can_on IS NULL OR ngay_can_on <= ?"
                    " ORDER BY ngay_can_on LIMIT 1",
                    (date.today().isoformat(),),
                ).fetchall()
                if not rows:
                    rows = conn.execute("SELECT * FROM vocab ORDER BY RANDOM() LIMIT 1").fetchall()
            self.the_hien_tai = dict(rows[0]) if rows else None
        except Exception:
            self.the_hien_tai = None
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=16, spacing=10)
        root.add_widget(Label(text="[b][size=22]Flashcard[/b][/size]", markup=True, size_hint_y=None, height=40))
        self.the_label = Label(text="", font_size=64, size_hint_y=None, height=140)
        self.phien_am = Label(text="", font_size=28, size_hint_y=None, height=50)
        self.nghia = Label(text="", font_size=22, size_hint_y=None, height=50)
        root.add_widget(self.the_label)
        root.add_widget(self.phien_am)
        root.add_widget(self.nghia)
        self._mat_truoc = True
        self._ve_mat_truoc()
        b_lat = Button(text="🔄 Lật thẻ", size_hint_y=None, height=48)
        b_lat.bind(on_press=self._lat_the)
        root.add_widget(b_lat)
        row = BoxLayout(size_hint_y=None, height=48, spacing=6)
        for muc, txt in ((0, "😕 Quên"), (1, "😐 Nhớ mờ"), (2, "😊 Nhớ rõ")):
            b = Button(text=txt)
            b.bind(on_press=lambda _, m=muc: self._danh_gia(m))
            row.add_widget(b)
        root.add_widget(row)
        b_back = Button(text="← Danh sách", size_hint_y=None, height=44)
        b_back.bind(on_press=lambda _: self.hien_danh_sach())
        root.add_widget(b_back)
        self.add_widget(root)

    def _ve_mat_truoc(self):
        t = self.the_hien_tai
        if not t:
            self.the_label.text = "Hết thẻ!"
            return
        self.the_label.text = t["hanzi"]
        self.phien_am.text = ""
        self.nghia.text = ""

    def _lat_the(self, _):
        t = self.the_hien_tai
        if not t:
            return
        if self._mat_truoc:
            self.phien_am.text = t.get("pinyin") or ""
            self.nghia.text = t.get("nghia_vi") or ""
        else:
            self._ve_mat_truoc()
        self._mat_truoc = not self._mat_truoc

    def _danh_gia(self, muc):
        t = self.the_hien_tai
        if t:
            try:
                with get_conn() as conn:
                    schedule_review(conn, t["id"], muc)
            except Exception:
                pass
        self.hien_flashcard()


class VideoScreen(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Video học tập[/b][/size]", markup=True, size_hint_y=None, height=40))
        scroll = ScrollView()
        ds = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
        ds.bind(minimum_height=ds.setter("height"))
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, tieu_de, trang_thai, tien_do FROM video_lessons ORDER BY id DESC LIMIT 30"
                ).fetchall() if self._co_bang("video_lessons") else []
            if not rows:
                ds.add_widget(Label(text="Chưa có video nào.\nImport video trên bản desktop/server.",
                                    size_hint_y=None, height=80, halign="center"))
            for r in rows:
                ds.add_widget(Label(text=f"🎬 {r['tieu_de']} — {r['trang_thai']} ({r['tien_do']}%)",
                                    size_hint_y=None, height=36, halign="left"))
        except Exception as e:
            ds.add_widget(Label(text=f"Lỗi: {e}", size_hint_y=None, height=36))
        scroll.add_widget(ds)
        root.add_widget(scroll)
        root.add_widget(Label(text="Xem chi tiết từng câu trên bản desktop.",
                              size_hint_y=None, height=30))
        self.add_widget(root)

    @staticmethod
    def _co_bang(ten):
        with get_conn() as conn:
            return bool(conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (ten,)).fetchone())


class ShadowScreen(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Shadowing[/b][/size]", markup=True, size_hint_y=None, height=40))
        root.add_widget(Label(text="Câu mẫu:", size_hint_y=None, height=28, halign="left"))
        self.cau = TextInput(text="我今天要去公司开会。", size_hint_y=None, height=60)
        root.add_widget(self.cau)
        row = BoxLayout(size_hint_y=None, height=48, spacing=6)
        b_nghe = Button(text="▶ Nghe câu chuẩn")
        b_nghe.bind(on_press=lambda _: self._tb("Bản mobile: dùng audio có sẵn trong thư mục media."))
        b_thu = Button(text="⏺ Thu âm")
        b_thu.bind(on_press=self._thu_am)
        row.add_widget(b_nghe)
        row.add_widget(b_thu)
        root.add_widget(row)
        b_luu = Button(text="💾 Lưu buổi shadowing", size_hint_y=None, height=48)
        b_luu.bind(on_press=self._luu)
        root.add_widget(b_luu)
        self._msg = Label(text="", size_hint_y=None, height=30)
        root.add_widget(self._msg)
        self.add_widget(root)

    def _tb(self, msg):
        self._msg.text = msg

    def _thu_am(self, _):
        # Ghi âm native cần quyền micro; giữ đơn giản và trung thực.
        self._msg.text = "Thu âm cần cấp quyền micro trên Android (sẽ bổ sung)."

    def _luu(self, _):
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO shadowing_sessions (cau_mau, created_at) VALUES (?, ?)",
                    (self.cau.text.strip(), _now()),
                )
            self._msg.text = "Đã lưu!"
        except Exception as e:
            self._msg.text = f"Lỗi: {e}"


class DictationScreen(Screen):
    cau_dung = "你好吗？"

    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Nghe chép[/b][/size]", markup=True, size_hint_y=None, height=40))
        b_nghe = Button(text="▶ Nghe câu", size_hint_y=None, height=48)
        b_nghe.bind(on_press=self._nghe_mau)
        root.add_widget(b_nghe)
        root.add_widget(Label(text="Gõ lại câu bạn nghe được:", size_hint_y=None, height=28, halign="left"))
        self.nhap = TextInput(size_hint_y=None, height=60, multiline=False)
        root.add_widget(self.nhap)
        b_nop = Button(text="Chấm bài", size_hint_y=None, height=48)
        b_nop.bind(on_press=self._cham)
        root.add_widget(b_nop)
        self._msg = Label(text="", size_hint_y=None, height=30)
        root.add_widget(self._msg)
        scroll = ScrollView()
        self.kq = Label(text="", size_hint_y=None, halign="left", valign="top")
        self.kq.bind(texture_size=self.kq.setter("size"))
        scroll.add_widget(self.kq)
        root.add_widget(scroll)
        self.add_widget(root)

    def _nghe_mau(self, _):
        self._msg.text = "Bản mobile: dùng audio có sẵn."

    def _cham(self, _):
        try:
            diff = char_diff(self.cau_dung, self.nhap.text.strip())
            dung = sum(1 for d in diff if d["loai"] == "dung")
            tong = len(diff)
            chi_tiet = " ".join(
                f"[color=00aa00]{d['ky_tu']}[/color]" if d["loai"] == "dung"
                else f"[color=cc0000]{d['ky_tu'] or '∅'}[/color]"
                for d in diff)
            self.kq.text = f"Đúng {dung}/{tong} ký tự.\nĐáp án: {self.cau_dung}\n{chi_tiet}"
            self.kq.markup = True
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO dictation_attempts (cau_dung, cau_nguoi_dung, so_ky_tu_dung, tong_ky_tu, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (self.cau_dung, self.nhap.text.strip(), dung, tong, _now()),
                )
        except Exception as e:
            self._msg.text = f"Lỗi: {e}"


class TranslateScreen(Screen):
    che_do = "viet_trung"

    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Dịch với AI[/b][/size]", markup=True, size_hint_y=None, height=40))
        row = BoxLayout(size_hint_y=None, height=44, spacing=6)
        self.tb_vt = ToggleButton(text="Việt → Trung", group="chedo", state="down")
        self.tb_tv = ToggleButton(text="Trung → Việt", group="chedo")
        self.tb_vt.bind(on_press=lambda _: setattr(self, "che_do", "viet_trung"))
        self.tb_tv.bind(on_press=lambda _: setattr(self, "che_do", "trung_viet"))
        row.add_widget(self.tb_vt)
        row.add_widget(self.tb_tv)
        root.add_widget(row)
        self.nhap = TextInput(hint_text="Nhập câu của bạn...", size_hint_y=None, height=70)
        root.add_widget(self.nhap)
        b_goi = Button(text="🤖 Nhờ AI phân tích", size_hint_y=None, height=48)
        b_goi.bind(on_press=self._goi_ai)
        root.add_widget(b_goi)
        scroll = ScrollView()
        self.kq = Label(text="Kết quả sẽ hiện ở đây.", halign="left", valign="top")
        self.kq.bind(texture_size=self.kq.setter("size"))
        scroll.add_widget(self.kq)
        root.add_widget(scroll)
        self.add_widget(root)

    def _goi_ai(self, _):
        self.kq.text = "Đang hỏi AI..."
        threading.Thread(target=self._goi_ai_nen, daemon=True).start()

    def _goi_ai_nen(self):
        cau = self.nhap.text.strip()
        if not cau:
            Clock.schedule_once(lambda dt: setattr(self.kq, "text", "Hãy nhập câu trước."))
            return
        try:
            client = get_qwen_client()
            if self.che_do == "viet_trung":
                system = ("Bạn là giáo viên tiếng Trung. Học viên đưa câu tiếng Việt và câu tiếng Trung họ tự viết, "
                          "hãy phân tích lỗi và trả về JSON: {correct, cau_hoc_vien, cau_de_xuat, loi_tu_vung, "
                          "loi_ngu_phap, giai_thich_vi, pinyin, vi_du}. Giải thích bằng tiếng Việt.")
                user = f"Câu tiếng Việt: {cau}\nHãy cho tôi khung phân tích."
            else:
                system = ("Bạn là giáo viên tiếng Trung. Dịch câu tiếng Trung sang tiếng Việt tự nhiên, có dấu. "
                          "Trả về JSON: {cau_goc, ban_dich, pinyin, giai_thich_vi}.")
                user = f"Câu tiếng Trung: {cau}"
            kq = client.chat_json(system, user, timeout=90)
            Clock.schedule_once(lambda dt: self._hien_kq(kq))
        except QwenError:
            Clock.schedule_once(lambda dt: setattr(self.kq, "text", QWEN_OFFLINE))
        except Exception as e:
            Clock.schedule_once(lambda dt: setattr(self.kq, "text", f"Lỗi: {e}"))

    def _hien_kq(self, kq):
        import json
        if isinstance(kq, dict):
            dong = []
            for k, v in kq.items():
                dong.append(f"{k}: {v}")
            self.kq.text = "\n".join(dong)
        else:
            self.kq.text = str(kq)


class PronunScreen(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Phát âm[/b][/size]", markup=True, size_hint_y=None, height=40))
        root.add_widget(Label(text="Câu mục tiêu:", size_hint_y=None, height=28, halign="left"))
        self.cau = TextInput(text="你好", size_hint_y=None, height=60, multiline=False)
        root.add_widget(self.cau)
        b_pt = Button(text="🎙 Thu & phân tích", size_hint_y=None, height=48)
        b_pt.bind(on_press=self._phan_tich)
        root.add_widget(b_pt)
        self.kq = Label(text="", halign="left", valign="top")
        root.add_widget(self.kq)
        self.add_widget(root)

    def _phan_tich(self, _):
        # Trung thực: chưa có engine chấm điểm -> metric null, chỉ lưu bản ghi.
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT INTO pronunciation_results (cau_muc_tieu, created_at) VALUES (?, ?)",
                    (self.cau.text.strip(), _now()),
                )
            self.kq.text = ("Đã lưu bản ghi.\n"
                            "Điểm phát âm: chưa có (null) — engine chấm điểm sẽ bổ sung sau.\n"
                            "Không bịa điểm số.")
        except Exception as e:
            self.kq.text = f"Lỗi: {e}"


class HistoryScreen(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Lịch sử học[/b][/size]", markup=True, size_hint_y=None, height=40))
        scroll = ScrollView()
        ds = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        ds.bind(minimum_height=ds.setter("height"))
        try:
            with get_conn() as conn:
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='study_events'").fetchone():
                    rows = conn.execute(
                        "SELECT ngay, so_phut, hoat_dong FROM study_events ORDER BY id DESC LIMIT 30").fetchall()
                    for r in rows:
                        ds.add_widget(Label(text=f"{r['ngay']}: {r['hoat_dong']} — {r['so_phut']} phút",
                                            size_hint_y=None, height=32, halign="left"))
                else:
                    ds.add_widget(Label(text="Chưa có lịch sử.", size_hint_y=None, height=32))
        except Exception as e:
            ds.add_widget(Label(text=f"Lỗi: {e}", size_hint_y=None, height=32))
        scroll.add_widget(ds)
        root.add_widget(scroll)
        self.add_widget(root)


class SettingsScreen(Screen):
    def on_pre_enter(self):
        self.clear_widgets()
        from app import config as cfg
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        root.add_widget(Label(text="[b][size=22]Cài đặt[/b][/size]", markup=True, size_hint_y=None, height=40))
        root.add_widget(Label(text="Máy Qwen (Ollama):", size_hint_y=None, height=28, halign="left"))
        self.qwen_url = TextInput(text=cfg.get_settings().qwen_base_url, size_hint_y=None, height=44, multiline=False)
        root.add_widget(self.qwen_url)
        root.add_widget(Label(text="Model:", size_hint_y=None, height=28, halign="left"))
        self.qwen_model = TextInput(text=cfg.get_settings().qwen_model, size_hint_y=None, height=44, multiline=False)
        root.add_widget(self.qwen_model)
        b_test = Button(text="🔌 Kiểm tra kết nối Qwen", size_hint_y=None, height=48)
        b_test.bind(on_press=self._test)
        root.add_widget(b_test)
        b_luu = Button(text="💾 Lưu", size_hint_y=None, height=48)
        b_luu.bind(on_press=self._luu)
        root.add_widget(b_luu)
        self._msg = Label(text="", size_hint_y=None, height=60, halign="left", valign="top")
        root.add_widget(self._msg)
        root.add_widget(Label(text=f"Thư mục dữ liệu:\n{paths.DATA_DIR}", size_hint_y=None, height=60,
                              halign="left", valign="top"))
        self.add_widget(root)

    def _luu(self, _):
        try:
            from app import config as cfg
            cfg.update_settings(qwen_base_url=self.qwen_url.text.strip(),
                                qwen_model=self.qwen_model.text.strip())
            get_qwen_client().refresh_settings()
            self._msg.text = "Đã lưu cấu hình."
        except Exception as e:
            self._msg.text = f"Lỗi: {e}"

    def _test(self, _):
        self._msg.text = "Đang kiểm tra..."
        threading.Thread(target=self._test_nen, daemon=True).start()

    def _test_nen(self):
        try:
            client = get_qwen_client()
            client.refresh_settings()
            kq = client.check(timeout=8)
            msg = "Kết nối OK!" if kq.get("ok") else f"Không kết nối được: {kq}"
        except QwenError:
            msg = QWEN_OFFLINE
        except Exception as e:
            msg = f"Lỗi: {e}"
        Clock.schedule_once(lambda dt: setattr(self._msg, "text", msg))


class HanNguApp(App):
    title = "Hán Ngữ"

    def build(self):
        run_startup()
        sm = ScreenManager()
        for name, _ in TABS:
            cls = {"home": HomeScreen, "vocab": VocabScreen, "video": VideoScreen,
                   "shadow": ShadowScreen, "dictation": DictationScreen, "translate": TranslateScreen,
                   "pronun": PronunScreen, "history": HistoryScreen, "settings": SettingsScreen}[name]
            sm.add_widget(cls(name=name))
        root = BoxLayout(orientation="vertical")
        root.add_widget(sm)
        nav = BoxLayout(size_hint_y=None, height=56, spacing=2)
        for name, label in TABS:
            b = Button(text=label, font_size=11)
            b.bind(on_press=lambda _, n=name: setattr(sm, "current", n))
            nav.add_widget(b)
        root.add_widget(nav)
        return root


if __name__ == "__main__":
    HanNguApp().run()
