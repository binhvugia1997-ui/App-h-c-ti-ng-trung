"""Module VIDEO LEARNING: biến video tiếng Trung thành bài học (local-first).

Pipeline: import -> trích audio (ffmpeg) -> speech-to-text -> chia đoạn ->
dịch (Qwen) -> sinh bài học. Logic xử lý video nặng nằm ở file độc lập
``process_video.py`` (bản FINAL do user cập nhật); module này chỉ giao tiếp
với nó QUA :mod:`app.video.adapter_process_video`, tuyệt đối không đoán
implementation bên trong.
"""
