/* Hán Ngữ Server — app.js (vanilla JS, API tương đối /api/...) */
(function () {
"use strict";

/* ---------- Helpers ---------- */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let toastTimer = null;
function toast(msg, ms) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, ms || 5000);
}

/** Gọi API theo quy ước {"ok": true, "data"} / {"ok": false, "error_vi"}.
 *  Trả về data nếu ok, ném Error(error_vi) nếu không. */
async function api(path, opts) {
  const o = Object.assign({}, opts);
  o.headers = Object.assign({}, o.headers);
  let body = o.body;
  if (body && !(body instanceof FormData) && typeof body === "object") {
    o.headers["Content-Type"] = "application/json";
    body = JSON.stringify(body);
  }
  o.body = body;
  let res;
  try {
    res = await fetch(path, o);
  } catch (e) {
    throw new Error("Không kết nối được tới server. Hãy chắc chắn app đang chạy (START_APP.bat).");
  }
  let json = null;
  try { json = await res.json(); } catch (e) { /* không phải JSON */ }
  if (!json || typeof json.ok === "undefined") {
    throw new Error("Server trả về dữ liệu không đúng định dạng (HTTP " + res.status + ").");
  }
  if (!json.ok) throw new Error(json.error_vi || "Đã có lỗi xảy ra, vui lòng thử lại.");
  return json.data;
}

function showErr(e) {
  console.error(e);
  toast(e.message || "Đã có lỗi xảy ra, vui lòng thử lại.");
}

/* ---------- Điều hướng tab ---------- */
document.querySelectorAll("#tabs .tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#tabs .tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll("main .panel").forEach((p) => p.classList.remove("active"));
    $("tab-" + btn.dataset.tab).classList.add("active");
    const init = TAB_INIT[btn.dataset.tab];
    if (init) { try { init(); } catch (e) { showErr(e); } }
  });
});
document.querySelectorAll(".subnav").forEach((nav) => {
  nav.querySelectorAll(".subtab").forEach((btn) => {
    btn.addEventListener("click", () => {
      nav.querySelectorAll(".subtab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      SUBTAB_FN[btn.dataset.sub] && SUBTAB_FN[btn.dataset.sub]();
    });
  });
});
const SUBTAB_FN = {};

/* =============================================================
   1. HÔM NAY — Dashboard
   ============================================================= */
async function loadDashboard() {
  const box = $("dash-summary");
  box.innerHTML = '<p class="muted">Đang tải...</p>';
  try {
    const d = await api("/api/dashboard/summary");
    box.innerHTML =
      stat((d.minutes_today != null ? d.minutes_today : 0), "phút hôm nay") +
      stat(d.streak != null ? d.streak : 0, "ngày streak 🔥") +
      stat(d.new_words != null ? d.new_words : 0, "từ mới") +
      stat(d.due_words != null ? d.due_words : 0, "từ cần ôn");
    if (d.lesson_today) {
      box.innerHTML += '<div class="card" style="grid-column:1/-1"><h3>Bài học hôm nay</h3><p>' +
        esc(d.lesson_today) + "</p></div>";
    }
  } catch (e) { box.innerHTML = '<p class="muted">Chưa tải được dữ liệu. ' + esc(e.message) + "</p>"; }
}
function stat(num, label) {
  return '<div class="stat"><div class="num">' + esc(num) + '</div><div class="lbl">' + esc(label) + "</div></div>";
}
$("btn-log-session").addEventListener("click", async () => {
  const minutes = parseInt($("sess-minutes").value, 10) || 0;
  try {
    await api("/api/dashboard/log", { method: "POST", body: { so_phut: minutes, hoat_dong: "hoc_tu_do" } });
    toast("Đã ghi nhận buổi học " + minutes + " phút. Cố lên! 💪", 3000);
    loadDashboard();
  } catch (e) { showErr(e); }
});

/* =============================================================
   2. TỪ VỰNG
   ============================================================= */
SUBTAB_FN.list = () => { $("vocab-list").hidden = false; $("vocab-flash").hidden = true; loadVocab(); };
SUBTAB_FN.flash = () => { $("vocab-list").hidden = true; $("vocab-flash").hidden = false; newFlashcard(); };

async function loadVocab(q) {
  const tb = $("vocab-tbody");
  tb.innerHTML = '<tr><td colspan="5" class="muted">Đang tải...</td></tr>';
  try {
    let path = "/api/vocab";
    if (q) path += "?q=" + encodeURIComponent(q);
    const list = await api(path);
    if (!list || !list.length) { tb.innerHTML = '<tr><td colspan="5" class="muted">Chưa có từ nào. Hãy thêm từ mới!</td></tr>'; return; }
    tb.innerHTML = list.map((w) =>
      "<tr><td><b>" + esc(w.hanzi) + "</b></td><td>" + esc(w.pinyin) + "</td><td>" + esc(w.vi) +
      "</td><td>" + esc(w.hsk || "—") + "</td><td>" +
      '<button class="btn v-edit" data-id="' + w.id + '">✏️</button> ' +
      '<button class="btn danger v-del" data-id="' + w.id + '">🗑️</button></td></tr>').join("");
    tb.querySelectorAll(".v-edit").forEach((b) => b.addEventListener("click", () => openEditModal(list, b.dataset.id)));
    tb.querySelectorAll(".v-del").forEach((b) => b.addEventListener("click", () => delVocab(b.dataset.id)));
  } catch (e) { tb.innerHTML = '<tr><td colspan="5" class="muted">' + esc(e.message) + "</td></tr>"; }
}
$("btn-v-add").addEventListener("click", async () => {
  const payload = {
    hanzi: $("v-hanzi").value.trim(),
    pinyin: $("v-pinyin").value.trim(),
    vi: $("v-vi").value.trim(),
    hsk: $("v-hsk").value ? parseInt($("v-hsk").value, 10) : null
  };
  if (!payload.hanzi || !payload.vi) { toast("Vui lòng nhập chữ Hán và nghĩa tiếng Việt.", 3000); return; }
  try {
    await api("/api/vocab", { method: "POST", body: payload });
    $("v-hanzi").value = $("v-pinyin").value = $("v-vi").value = $("v-hsk").value = "";
    toast("Đã thêm từ mới. 🎉", 2500);
    loadVocab();
  } catch (e) { showErr(e); }
});
$("btn-v-search").addEventListener("click", () => loadVocab($("v-search").value.trim()));

let editId = null;
function openEditModal(list, id) {
  const w = list.find((x) => String(x.id) === String(id));
  if (!w) return;
  editId = id;
  $("m-hanzi").value = w.hanzi || "";
  $("m-pinyin").value = w.pinyin || "";
  $("m-vi").value = w.vi || "";
  $("m-hsk").value = w.hsk || "";
  $("modal").hidden = false;
}
$("btn-modal-cancel").addEventListener("click", () => { $("modal").hidden = true; });
$("btn-modal-save").addEventListener("click", async () => {
  const payload = {
    hanzi: $("m-hanzi").value.trim(), pinyin: $("m-pinyin").value.trim(),
    vi: $("m-vi").value.trim(),
    hsk: $("m-hsk").value ? parseInt($("m-hsk").value, 10) : null
  };
  try {
    await api("/api/vocab/" + editId, { method: "PUT", body: payload });
    $("modal").hidden = true;
    toast("Đã lưu thay đổi.", 2500);
    loadVocab();
  } catch (e) { showErr(e); }
});
async function delVocab(id) {
  if (!confirm("Xóa từ này?")) return;
  try {
    await api("/api/vocab/" + id, { method: "DELETE" });
    toast("Đã xóa từ.", 2500);
    loadVocab();
  } catch (e) { showErr(e); }
}

/* Flashcard: Hanzi → Pinyin → Nghĩa, đánh giá 0-5 */
let flashCard = null, flashStage = 0;
$("btn-flash-new").addEventListener("click", newFlashcard);
$("flash-card").addEventListener("click", flipCard);
$("flash-card").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flipCard(); } });
async function newFlashcard() {
  flashStage = 0;
  try {
    flashCard = await api("/api/vocab/flashcards");
    $("flash-rate").hidden = true;
    renderFlash();
  } catch (e) { $("flash-front").textContent = e.message; $("flash-back").hidden = true; }
}
function renderFlash() {
  if (!flashCard) { $("flash-front").textContent = "Hết thẻ hôm nay. Làm tốt lắm! 🎉"; $("flash-back").hidden = true; return; }
  $("flash-back").hidden = false;
  if (flashStage === 0) {
    $("flash-front").textContent = flashCard.hanzi || "—";
    $("flash-back").hidden = true;
  } else if (flashStage === 1) {
    $("flash-front").textContent = flashCard.hanzi || "—";
    $("flash-back").hidden = false;
    $("flash-back").textContent = flashCard.pinyin || "(chưa có pinyin)";
  } else {
    $("flash-front").textContent = flashCard.hanzi || "—";
    $("flash-back").hidden = false;
    $("flash-back").textContent = (flashCard.pinyin ? flashCard.pinyin + " — " : "") + (flashCard.vi || "(chưa có nghĩa)");
    $("flash-rate").hidden = false;
  }
}
function flipCard() {
  if (!flashCard) return;
  if (flashStage < 2) { flashStage++; renderFlash(); }
  else { flashStage = 0; renderFlash(); }
}
$("flash-grade-btns").querySelectorAll(".grade").forEach((b) => {
  b.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    if (!flashCard) return;
    try {
      await api("/api/vocab/" + flashCard.id + "/review", { method: "POST", body: { muc_do: parseInt(b.dataset.g, 10) } });
      newFlashcard();
    } catch (e) { showErr(e); }
  });
});

/* =============================================================
   3. VIDEO
   ============================================================= */
let videoJobsTimer = null;
$("btn-video-upload").addEventListener("click", async () => {
  const f = $("video-file").files[0];
  if (!f) { toast("Vui lòng chọn file video trước.", 3000); return; }
  const fd = new FormData();
  fd.append("file", f);
  try {
    toast("Đang tải lên... ⏳", 2500);
    const up = await api("/api/video/upload", { method: "POST", body: fd });
    if (!up || !up.video_id) throw new Error("Upload xong nhưng không nhận được video_id.");
    const job = await api("/api/video/jobs", { method: "POST", body: { video_id: up.video_id } });
    toast("Đã tạo job xử lý (id: " + esc(job && (job.job_id || job.id) != null ? (job.job_id || job.id) : "?") + ").", 3000);
    loadVideoJobs();
  } catch (e) { showErr(e); }
});
async function loadVideoJobs() {
  try {
    const jobs = await api("/api/video/jobs");
    if (!jobs || !jobs.length) { $("video-jobs").innerHTML = '<p class="muted">Chưa có job nào.</p>'; return; }
    $("video-jobs").innerHTML = jobs.map((j) => {
      const pct = j.progress != null ? Math.round(Number(j.progress) || 0) : 0;
      return '<div class="job"><b>#' + esc(j.id) + "</b> " + esc(j.video_name || j.video_id || "") +
        " — " + esc(j.status || "đang chờ") + (j.stage ? " (" + esc(j.stage) + ")" : "") +
        (j.error_vi ? ' <span class="diff-bad">' + esc(j.error_vi) + "</span>" : "") +
        '<div class="progress"><div style="width:' + Math.min(100, Math.max(0, pct)) + '%"></div></div></div>';
    }).join("");
    const pending = jobs.some((j) => ["queued", "running", "processing"].indexOf(String(j.status)) >= 0);
    clearInterval(videoJobsTimer);
    if (pending) videoJobsTimer = setInterval(loadVideoJobs, 3000);
    else { loadVideoLessons(); }
  } catch (e) { $("video-jobs").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}
async function loadVideoLessons() {
  const box = $("video-lessons");
  box.innerHTML = '<p class="muted">Đang tải...</p>';
  try {
    const lessons = await api("/api/video/lessons");
    if (!lessons || !lessons.length) { box.innerHTML = '<p class="muted">Chưa có bài học video nào.</p>'; return; }
    box.innerHTML = lessons.map((l) =>
      '<div class="segment" data-lid="' + l.id + '"><b>' + esc(l.title || ("Bài học #" + l.id)) + "</b>" +
      (l.segment_count != null ? ' <span class="muted">(' + esc(l.segment_count) + " câu)</span>" : "") + "</div>").join("");
    box.querySelectorAll(".segment").forEach((el) =>
      el.addEventListener("click", () => openLesson(el.dataset.lid)));
  } catch (e) { box.innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}
async function openLesson(lid) {
  lastLesson = lid;
  try {
    const lesson = await api("/api/video/lessons/" + lid);
    $("video-player-card").hidden = false;
    $("video-title").textContent = lesson.title || ("Bài học #" + lid);
    const player = $("video-player");
    if (lesson.video_url) { player.src = lesson.video_url; player.style.display = ""; }
    else { player.removeAttribute("src"); player.style.display = "none"; }
    renderSegments(lesson.segments || []);
    $("video-player-card").scrollIntoView({ behavior: "smooth" });
  } catch (e) { showErr(e); }
}
function renderSegments(segs) {
  const box = $("video-segments");
  const showPy = $("opt-pinyin").checked, showVi = $("opt-viet").checked;
  box.innerHTML = segs.map((s) =>
    '<div class="segment" data-start="' + esc(s.start != null ? s.start : 0) + '">' +
    '<div class="hanzi">' + esc(s.hanzi || s.text || "") + "</div>" +
    (showPy ? '<div class="pinyin">' + esc(s.pinyin || "") + "</div>" : "") +
    (showVi ? '<div class="vi">' + esc(s.vi || s.translation || "") + "</div>" : "") +
    "</div>").join("") || '<p class="muted">Bài học chưa có câu nào.</p>';
  box.querySelectorAll(".segment").forEach((el) =>
    el.addEventListener("click", () => {
      box.querySelectorAll(".segment").forEach((x) => x.classList.remove("sel"));
      el.classList.add("sel");
      const player = $("video-player");
      const t = parseFloat(el.dataset.start);
      if (player.src && !isNaN(t)) { player.currentTime = t; player.play().catch(() => {}); }
    }));
}
$("opt-pinyin").addEventListener("change", () => openLessonRefresh());
$("opt-viet").addEventListener("change", () => openLessonRefresh());
let lastLesson = null;
async function openLessonRefresh() {
  if (!lastLesson) return;
  try {
    const lesson = await api("/api/video/lessons/" + lastLesson);
    renderSegments(lesson.segments || []);
  } catch (e) { showErr(e); }
}

/* =============================================================
   4. SHADOWING
   ============================================================= */
let shadowSession = null, recChunks = [], recStream = null, recMedia = null, recBlob = null;
$("btn-shadow-new").addEventListener("click", async () => {
  const text = $("shadow-text").value.trim();
  if (!text) { toast("Nhập câu tiếng Trung cần nhại trước nhé.", 3000); return; }
  try {
    shadowSession = await api("/api/shadowing/sessions", { method: "POST", body: { cau_chuan: text } });
    $("shadow-target").textContent = text;
    $("shadow-target").classList.remove("muted");
    toast("Đã tạo phiên shadowing. Hãy thu âm giọng của bạn.", 3000);
    loadShadowRecordings();
  } catch (e) { showErr(e); }
});
$("btn-rec-start").addEventListener("click", async () => {
  try {
    recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recChunks = [];
    recMedia = new MediaRecorder(recStream);
    recMedia.ondataavailable = (e) => { if (e.data.size) recChunks.push(e.data); };
    recMedia.onstop = () => {
      recBlob = new Blob(recChunks, { type: recMedia.mimeType || "audio/webm" });
      $("rec-preview").src = URL.createObjectURL(recBlob);
      $("rec-preview").hidden = false;
      $("btn-rec-upload").disabled = false;
      recStream.getTracks().forEach((t) => t.stop());
    };
    recMedia.start();
    $("btn-rec-start").disabled = true;
    $("btn-rec-stop").disabled = false;
    $("rec-status").textContent = "Đang thu âm... 🎤";
  } catch (e) {
    toast("Không truy cập được micro. Hãy cho phép trình duyệt dùng micro.", 4000);
  }
});
$("btn-rec-stop").addEventListener("click", () => {
  if (recMedia && recMedia.state !== "inactive") recMedia.stop();
  $("btn-rec-start").disabled = false;
  $("btn-rec-stop").disabled = true;
  $("rec-status").textContent = "Đã dừng. Nghe lại rồi bấm Gửi bản thu.";
});
$("btn-rec-upload").addEventListener("click", async () => {
  if (!recBlob) return;
  const fd = new FormData();
  fd.append("file", recBlob, "recording.webm");
  try {
    if (!shadowSession || !shadowSession.id) { toast("Hãy tạo phiên shadowing trước.", 3000); return; }
    await api("/api/shadowing/sessions/" + shadowSession.id + "/recording", { method: "POST", body: fd });
    $("btn-rec-upload").disabled = true;
    $("rec-status").textContent = "Đã gửi bản thu. 🎉";
    loadShadowRecordings();
  } catch (e) { showErr(e); }
});
async function loadShadowRecordings() {
  try {
    const list = await api("/api/shadowing/sessions?limit=50");
    const items = (list || []).filter((s) => s.recording_path);
    if (!items.length) { $("shadow-recordings").innerHTML = '<p class="muted">Chưa có bản thu nào.</p>'; return; }
    $("shadow-recordings").innerHTML = items.map((r) => {
      const fname = String(r.recording_path || "").split("/").pop().split("\\").pop();
      return "<p><b>" + esc(r.created_at || "") + "</b> " + esc(r.cau_chuan || "") +
        (fname ? '<br><audio controls src="/api/shadowing/recordings/' + esc(fname) + '"></audio>' : "") + "</p>";
    }).join("");
  } catch (e) { $("shadow-recordings").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}

/* =============================================================
   5. NGHE CHÉP
   ============================================================= */
let dictExercise = null;
$("btn-dict-new").addEventListener("click", async () => {
  try {
    dictExercise = await api("/api/dictation/exercise");
    $("dict-exercise").hidden = false;
    $("dict-input").value = "";
    $("dict-result").innerHTML = "";
    const aud = $("dict-audio");
    if (dictExercise && dictExercise.audio_url) {
      aud.src = dictExercise.audio_url;
      aud.hidden = false;
    } else { aud.removeAttribute("src"); aud.hidden = true; }
    $("btn-dict-play").disabled = !(dictExercise && dictExercise.audio_url);
  } catch (e) { showErr(e); }
});
$("btn-dict-play").addEventListener("click", () => $("dict-audio").play().catch(() => {}));
$("btn-dict-submit").addEventListener("click", async () => {
  if (!dictExercise) return;
  const answer = $("dict-input").value.trim();
  if (!answer) { toast("Hãy nhập câu bạn nghe được trước khi chấm.", 3000); return; }
  try {
    const res = await api("/api/dictation/submit", {
      method: "POST", body: { source_id: dictExercise.source_id || null, vocab_id: dictExercise.vocab_id || null, cau_nguoi_dung: answer }
    });
    renderDictResult(res);
  } catch (e) { showErr(e); }
});
function renderDictResult(res) {
  res = res || {};
  const box = $("dict-result");
  const correct = res.cau_dung || "";
  const diff = res.diff || [];
  let html = "<h4>Kết quả</h4>";
  if (res.dung_hoan_toan === true) html += '<p>✅ <b>Chính xác!</b> Tuyệt vời.</p>';
  else if (res.dung_hoan_toan === false) html += '<p>❌ <b>Chưa đúng.</b> Đối chiếu bên dưới.</p>';
  html += '<p class="muted">Câu đúng: ' + esc(correct) + "</p>";
  if (diff.length) {
    html += "<p>" + diff.map((t) => {
      const cls = t.status === "dung" ? "diff-ok" : t.status === "thieu" ? "diff-miss" : "diff-bad";
      const extra = t.status === "thua" ? " (thừa)" : "";
      return '<span class="' + cls + '">' + esc(t.char) + "</span>" + (extra ? '<span class="diff-bad">' + esc(extra) + "</span>" : "");
    }).join("") + "</p>";
  }
  if (res.pinyin) html += '<p class="muted">Pinyin: ' + esc(res.pinyin) + "</p>";
  if (res.nghia_vi) html += '<p class="muted">Nghĩa: ' + esc(res.nghia_vi) + "</p>";
  if (res.so_lan_thu != null) html += '<p class="muted">Số lần thử: ' + esc(res.so_lan_thu) + "</p>";
  box.innerHTML = html;
}

/* =============================================================
   6. DỊCH
   ============================================================= */
SUBTAB_FN.vt = () => { $("tr-vt").hidden = false; $("tr-tv").hidden = true; };
SUBTAB_FN.tv = () => { $("tr-vt").hidden = true; $("tr-tv").hidden = false; };

$("btn-tr-vt").addEventListener("click", async () => {
  const text = $("tr-vt-input").value.trim();
  if (!text) { toast("Nhập câu tiếng Việt trước nhé.", 3000); return; }
  try {
    const res = await api("/api/exercises/viet-trung", {
      method: "POST", body: { cau_vi: text, cau_trung_cua_ban: $("tr-vt-answer").value.trim() || "" }
    });
    renderTranslate(res);
  } catch (e) { showErr(e); }
});
$("btn-tr-tv").addEventListener("click", async () => {
  const text = $("tr-tv-input").value.trim();
  if (!text) { toast("Nhập câu tiếng Trung trước nhé.", 3000); return; }
  try {
    const res = await api("/api/exercises/trung-viet", {
      method: "POST", body: { cau_trung: text, cau_vi_cua_ban: $("tr-tv-answer").value.trim() || null }
    });
    renderTranslate(res);
  } catch (e) { showErr(e); }
});
function renderTranslate(res) {
  res = res || {};
  const box = $("tr-result");
  let html = "<h4>Kết quả</h4>";
  if (res.correct === true) html += '<p>✅ <b>Dịch đúng!</b> Làm tốt lắm.</p>';
  else if (res.correct === false) html += '<p>❌ <b>Chưa đúng.</b> Xem gợi ý bên dưới.</p>';
  if (res.corrected) html += "<p><b>Câu đề xuất:</b> " + esc(res.corrected) + "</p>";
  if (res.pinyin) html += '<p class="muted">Pinyin: ' + esc(res.pinyin) + "</p>";
  if (res.translation) html += "<p><b>Dịch nghĩa:</b> " + esc(res.translation) + "</p>";
  const loiChung = []
    .concat(res.errors || [], res.grammar || [], res.vocabulary || [])
    .filter(Boolean);
  if (loiChung.length)
    html += "<p><b>Lỗi cần chú ý:</b></p><ul>" + loiChung.map((e) => "<li>" + esc(typeof e === "string" ? e : JSON.stringify(e)) + "</li>").join("") + "</ul>";
  if (res.explanation_vi) html += "<p><b>Giải thích:</b> " + esc(res.explanation_vi) + "</p>";
  if (res.alternatives && res.alternatives.length)
    html += "<p><b>Câu tương tự:</b></p><ul>" + res.alternatives.map((a) => "<li>" + esc(a) + "</li>").join("") + "</ul>";
  if (typeof res.score === "number") html += "<p>Điểm: <b>" + esc(res.score) + "</b></p>";
  if (!res.corrected && !loiChung.length && !res.explanation_vi && res.correct == null)
    html += '<p class="muted">Chưa có dữ liệu đánh giá.</p>';
  box.innerHTML = html;
}

/* =============================================================
   7. PHÁT ÂM
   ============================================================= */
let pronStream = null, pronMedia = null, pronChunks = [], pronBlob = null;
$("btn-pron-start").addEventListener("click", async () => {
  try {
    pronStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    pronChunks = [];
    pronMedia = new MediaRecorder(pronStream);
    pronMedia.ondataavailable = (e) => { if (e.data.size) pronChunks.push(e.data); };
    pronMedia.onstop = () => {
      pronBlob = new Blob(pronChunks, { type: pronMedia.mimeType || "audio/webm" });
      $("pron-preview").src = URL.createObjectURL(pronBlob);
      $("pron-preview").hidden = false;
      $("btn-pron-analyze").disabled = false;
      pronStream.getTracks().forEach((t) => t.stop());
    };
    pronMedia.start();
    $("btn-pron-start").disabled = true;
    $("btn-pron-stop").disabled = false;
  } catch (e) {
    toast("Không truy cập được micro. Hãy cho phép trình duyệt dùng micro.", 4000);
  }
});
$("btn-pron-stop").addEventListener("click", () => {
  if (pronMedia && pronMedia.state !== "inactive") pronMedia.stop();
  $("btn-pron-start").disabled = false;
  $("btn-pron-stop").disabled = true;
});
$("btn-pron-analyze").addEventListener("click", async () => {
  const text = $("pron-text").value.trim();
  if (!text) { toast("Nhập câu cần luyện trước nhé.", 3000); return; }
  if (!pronBlob) { toast("Hãy thu âm trước khi phân tích.", 3000); return; }
  const fd = new FormData();
  fd.append("recording", pronBlob, "pron.webm");
  fd.append("target_sentence", text);
  try {
    $("pron-result").innerHTML = '<p class="muted">Đang phân tích... ⏳</p>';
    const res = await api("/api/pronunciation/analyze", { method: "POST", body: fd });
    renderPronResult(res);
  } catch (e) { $("pron-result").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
});
function renderPronResult(res) {
  const box = $("pron-result");
  let html = "";
  const metrics = res.metrics || res;
  const rows = [];
  ["accuracy", "fluency", "tone", "overall"].forEach((k) => {
    const v = metrics[k];
    rows.push("<tr><td>" + esc({accuracy:"Độ chính xác",fluency:"Độ trôi chảy",tone:"Ngữ điệu",overall:"Tổng điểm"}[k]) +
      "</td><td>" + (v == null ? '<span class="muted">chưa có dữ liệu</span>' : "<b>" + esc(v) + "</b>") + "</td></tr>");
  });
  html += '<table class="tbl"><tbody>' + rows.join("") + "</tbody></table>";
  if (res.feedback) html += "<p><b>Nhận xét:</b> " + esc(res.feedback) + "</p>";
  if (res.issues && res.issues.length)
    html += "<p><b>Cần cải thiện:</b></p><ul>" + res.issues.map((i) => "<li>" + esc(i) + "</li>").join("") + "</ul>";
  box.innerHTML = html;
}

/* =============================================================
   8. LỊCH SỬ
   ============================================================= */
SUBTAB_FN.ex = () => { showHist("ex"); loadHistExercises(); };
SUBTAB_FN.dic = () => { showHist("dic"); loadHistDict(); };
SUBTAB_FN.job = () => { showHist("job"); loadHistJobs(); };
function showHist(which) {
  ["ex", "dic", "job"].forEach((k) => { $("hist-" + k).hidden = k !== which; });
}
async function loadHistExercises() {
  try {
    const list = await api("/api/exercises/history");
    $("hist-ex").innerHTML = histTable(list, ["created_at", "type", "score", "detail"]);
  } catch (e) { $("hist-ex").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}
async function loadHistDict() {
  try {
    const list = await api("/api/dictation/attempts");
    $("hist-dic").innerHTML = histTable(list, ["created_at", "score", "correct_text"]);
  } catch (e) { $("hist-dic").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}
async function loadHistJobs() {
  try {
    const list = await api("/api/video/jobs");
    $("hist-job").innerHTML = histTable(list, ["id", "video_name", "status", "progress"]);
  } catch (e) { $("hist-job").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}
function histTable(list, cols) {
  if (!list || !list.length) return '<p class="muted">Chưa có lịch sử.</p>';
  return '<table class="tbl"><thead><tr>' + cols.map((c) => "<th>" + esc(c) + "</th>").join("") +
    "</tr></thead><tbody>" + list.map((r) =>
    "<tr>" + cols.map((c) => "<td>" + esc(r[c] != null ? r[c] : "—") + "</td>").join("") + "</tr>").join("") +
    "</tbody></table>";
}

/* =============================================================
   9. CÀI ĐẶT
   ============================================================= */
async function loadSettings() {
  try {
    const s = await api("/api/settings");
    $("set-qwen-url").value = s.qwen_base_url || "";
    $("set-qwen-model").value = s.qwen_model || "";
    $("set-host").value = s.host || "";
    $("set-port").value = s.port != null ? s.port : "";
  } catch (e) { showErr(e); }
}
$("btn-settings-save").addEventListener("click", async () => {
  const payload = {
    qwen_base_url: $("set-qwen-url").value.trim(),
    qwen_model: $("set-qwen-model").value.trim(),
    host: $("set-host").value.trim(),
    port: $("set-port").value ? parseInt($("set-port").value, 10) : null
  };
  try {
    await api("/api/settings", { method: "PUT", body: payload });
    toast("Đã lưu cài đặt. ✅", 3000);
  } catch (e) { showErr(e); }
});
async function loadHealth() {
  const box = $("health-box");
  box.innerHTML = '<p class="muted">Đang kiểm tra...</p>';
  try {
    const h = await api("/api/health");
    const core = (h.core || []).map((c) => statusLine(c)).join("");
    const ext = (h.external || []).map((c) => statusLine(c)).join("");
    box.innerHTML = "<h4>Core (nội bộ)</h4>" + (core || '<p class="muted">Không có thông tin.</p>') +
      "<h4>Dịch vụ ngoài</h4>" + (ext || '<p class="muted">Không có thông tin.</p>');
  } catch (e) { box.innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
}
function statusLine(c) {
  const ok = c.ok === true;
  return "<p>" + (ok ? "✅" : "❌") + " <b>" + esc(c.name || "") + "</b> — " + esc(c.message_vi || c.message || "") + "</p>";
}
$("btn-health").addEventListener("click", loadHealth);
$("btn-backup").addEventListener("click", async () => {
  try {
    $("backup-result").innerHTML = '<p class="muted">Đang sao lưu...</p>';
    const res = await api("/api/backup", { method: "POST" });
    $("backup-result").innerHTML = "<p>✅ Sao lưu xong: <b>" + esc(res.path || res.file || "ok") + "</b></p>";
  } catch (e) { $("backup-result").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
});
$("btn-verify").addEventListener("click", async () => {
  try {
    $("backup-result").innerHTML = '<p class="muted">Đang kiểm tra...</p>';
    const res = await api("/api/migration/verify");
    $("backup-result").innerHTML = "<p>" + ((res.ok === false) ? "❌" : "✅") + " " +
      esc(res.message_vi || res.summary || "Xong.") + "</p>";
  } catch (e) { $("backup-result").innerHTML = '<p class="muted">' + esc(e.message) + "</p>"; }
});

/* ---------- Khởi tạo ---------- */
const TAB_INIT = {
  home: loadDashboard,
  vocab: function () { $("vocab-list").hidden = false; $("vocab-flash").hidden = true; loadVocab(); },
  video: function () { loadVideoJobs(); loadVideoLessons(); },
  shadow: loadShadowRecordings,
  dictation: function () {},
  translate: function () {},
  pronun: function () {},
  history: loadHistExercises,
  settings: function () { loadSettings(); loadHealth(); }
};
loadDashboard();

})();
