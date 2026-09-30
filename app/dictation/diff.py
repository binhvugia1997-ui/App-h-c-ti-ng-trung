"""So sánh câu đúng và câu người dùng gõ, ở mức từng ký tự.

Mỗi phần tử trả về: {"char": ký_tự, "status": ...} với status là một trong:
  - "dung":  ký tự đúng vị trí và đúng nội dung
  - "sai":   sai ký tự ở vị trí này (char = ký tự đúng cần có)
  - "thieu": thiếu ký tự này so với đáp án (char = ký tự còn thiếu)
  - "thua":  thừa ký tự này (char = ký tự thừa mà người dùng đã gõ)

Frontend dùng status để highlight: xanh (dung), đỏ (sai), gạch chân (thieu),
gạch bỏ (thua).
"""

import difflib


def char_diff(dung: str, sai: str) -> list:
    """So sánh hai câu theo từng ký tự, trả về danh sách {char, status}."""
    dung = dung or ""
    sai = sai or ""
    sm = difflib.SequenceMatcher(None, dung, sai, autojunk=False)
    ket_qua = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for ch in dung[i1:i2]:
                ket_qua.append({"char": ch, "status": "dung"})
        elif tag == "replace":
            doan_dung = dung[i1:i2]
            doan_sai = sai[j1:j2]
            chung = min(len(doan_dung), len(doan_sai))
            for k in range(chung):
                ket_qua.append({"char": doan_dung[k], "status": "sai"})
            for ch in doan_dung[chung:]:
                ket_qua.append({"char": ch, "status": "thieu"})
            for ch in doan_sai[chung:]:
                ket_qua.append({"char": ch, "status": "thua"})
        elif tag == "delete":
            for ch in dung[i1:i2]:
                ket_qua.append({"char": ch, "status": "thieu"})
        elif tag == "insert":
            for ch in sai[j1:j2]:
                ket_qua.append({"char": ch, "status": "thua"})
    return ket_qua
