"""
cancel_helper.py
Batalkan semua proses aktif user — dipanggil dari /start dan /reset.
"""
from handlers.merge import _user_bg_tasks as merge_tasks, _user_locks as merge_locks, _clear_buffers as merge_clear
from handlers.vcftotxt import _user_bg_tasks as vcf2txt_tasks, _user_locks as vcf2txt_locks, _clear_buffers as vcf2txt_clear
from handlers.txttovcf import _user_bg_tasks as ttv_tasks, _user_locks as ttv_locks, _clear_buffers as ttv_clear

def cancel_all(user_id: int):
    """Batalkan semua proses aktif dan bersihkan memori/disk user."""

    # Cancel semua background tasks
    for tasks_dict in [merge_tasks, vcf2txt_tasks, ttv_tasks]:
        tasks = tasks_dict.pop(user_id, set())
        for t in tasks:
            try: t.cancel()
            except: pass

    # Hapus semua buffer disk
    for clear_func in [merge_clear, vcf2txt_clear, ttv_clear]:
        try: clear_func(user_id)
        except: pass

    # Hapus lock
    for locks in [merge_locks, vcf2txt_locks, ttv_locks]:
        locks.pop(user_id, None)