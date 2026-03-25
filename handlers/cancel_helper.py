"""
cancel_helper.py
Batalkan semua proses aktif user — dipanggil dari /start dan /reset.
"""
from handlers.merge import _user_timers as merge_timers, _user_locks as merge_locks, _clear_buffers as merge_clear
from handlers.vcftotxt import _user_timers as vcf2txt_timers, _user_locks as vcf2txt_locks, _clear_buffers as vcf2txt_clear
from handlers.txttovcf import _user_timers as ttv_timers, _user_locks as ttv_locks, _clear_buffers as ttv_clear


def cancel_all(user_id: int):
    """Batalkan semua proses aktif dan bersihkan memori/disk user."""

    # Cancel semua timer debounce
    for timers in [merge_timers, vcf2txt_timers, ttv_timers]:
        timer = timers.pop(user_id, None)
        if timer:
            timer.cancel()

    # Hapus semua buffer disk
    for clear_func in [merge_clear, vcf2txt_clear, ttv_clear]:
        clear_func(user_id)

    # Hapus lock
    for locks in [merge_locks, vcf2txt_locks, ttv_locks]:
        locks.pop(user_id, None)