"""
cancel_helper.py
Batalkan semua proses aktif user — dipanggil dari /start dan /reset.
"""
from handlers.merge import _user_buffers as merge_buffers, _user_timers as merge_timers, _user_locks as merge_locks
from handlers.vcftotxt import _user_buffers as vcf2txt_buffers, _user_timers as vcf2txt_timers
from handlers.txttovcf import _user_buffers as ttv_buffers, _user_timers as ttv_timers


def cancel_all(user_id: int):
    """Batalkan semua proses aktif dan bersihkan RAM user."""

    # Cancel semua timer debounce
    for timers in [merge_timers, vcf2txt_timers, ttv_timers]:
        timer = timers.pop(user_id, None)
        if timer:
            timer.cancel()

    # Hapus semua buffer RAM
    for buffers in [merge_buffers, vcf2txt_buffers, ttv_buffers]:
        buffers.pop(user_id, None)

    # Hapus lock merge
    merge_locks.pop(user_id, None)